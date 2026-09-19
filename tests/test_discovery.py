"""Offline contracts for discovery, explicit endpoints and greeting probes."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
from unittest.mock import patch

import pytest

from prompt_tournament.providers import (
    ProviderFailure, _NoRedirect, call_provider, http_get_transport,
    http_transport, list_models, normalize_response, probe_model,
)


def connection(kind='openai', **extra):
    value = {'kind': kind, 'base_url': 'https://synthetic.invalid/v1' if kind == 'openai' else 'http://127.0.0.1:11434'}
    if kind == 'openai':
        value['api_key_env'] = 'MK_DISCOVERY_TEST_KEY'
    return {**value, **extra}


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv('MK_DISCOVERY_TEST_KEY', 'synthetic-test-value')


@pytest.mark.parametrize('kind,body,path,expected', [
    ('openai', {'data': [{'id': 'z-model'}, {'id': 'a-model'}, {'id': 'z-model'}]}, '/v1/models', ['a-model', 'z-model']),
    ('ollama', {'models': [{'name': 'z:27b'}, {'model': 'a:4b'}, {'name': 'z:27b'}]}, '/api/tags', ['a:4b', 'z:27b']),
    ('openai', {'data': []}, '/v1/models', []),
    ('ollama', {'models': []}, '/api/tags', []),
])
def test_explicit_discovery_sorts_deduplicates_and_uses_get_contract(kind, body, path, expected):
    seen = []
    def get(url, headers, timeout):
        seen.append(url)
        assert url.endswith(path) and timeout == 12
        assert headers.get('Authorization') == ('Bearer synthetic-test-value' if kind == 'openai' else None)
        return body
    assert list_models(connection(kind, timeout_seconds=12), get) == expected
    assert len(seen) == 1


@pytest.mark.parametrize('kind,body', [
    ('openai', []), ('openai', {}), ('openai', {'data': {}}),
    ('openai', {'data': [None]}), ('openai', {'data': [{'id': ''}]}),
    ('openai', {'data': [{'id': True}]}), ('openai', {'data': [{'id': 'good'}, {'id': 'bad\nID'}]}),
    ('ollama', {'models': 'not-a-list'}), ('ollama', {'models': [{}]}),
    ('ollama', {'models': [{'name': None, 'model': 'fallback'}]}),
])
def test_malformed_model_lists_fail_as_a_whole_without_echoing_payload(kind, body):
    with pytest.raises(ProviderFailure):
        list_models(connection(kind), lambda *_: body)


@pytest.mark.parametrize('changes', [
    {'base_url': 'http://remote.invalid'},
    {'base_url': 'https://name:secret@synthetic.invalid'},
    {'base_url': 'https://synthetic.invalid?key=secret'},
    {'base_url': 'https://synthetic.invalid/#fragment'},
    {'base_url': 'https://synthetic.invalid:invalid'},
    {'kind': 'unknown'}, {'endpoint': 'unknown'}, {'api_key': 'secret'},
    {'api_key_env': 'not a name'}, {'timeout_seconds': float('nan')},
])
def test_connection_validation_fails_before_transport(changes):
    def forbidden(*_):
        pytest.fail('Invalid settings reached transport')
    with pytest.raises(ProviderFailure) as error:
        list_models(connection(**changes), forbidden)
    assert 'secret' not in str(error.value)


def test_missing_key_and_ollama_endpoint_rejected_before_discovery(monkeypatch):
    monkeypatch.delenv('MK_DISCOVERY_TEST_KEY')
    with pytest.raises(ProviderFailure, match='unset'):
        list_models(connection(), lambda *_: pytest.fail('No key'))
    with pytest.raises(ProviderFailure, match='endpoint'):
        list_models(connection('ollama', endpoint='responses'), lambda *_: pytest.fail('Bad endpoint'))


class Response(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.read_limit = None

    def read(self, size=-1):
        self.read_limit = size
        return super().read(size)


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_http_transports_share_bounded_json_reader(method):
    response = Response(b'{"data":[]}')
    class Opener:
        def open(self, request, timeout):
            assert request.get_method() == method and timeout == 5
            assert (request.data is None) == (method == 'GET')
            return response
    def build(*handlers):
        assert _NoRedirect in handlers
        return Opener()
    with patch('urllib.request.build_opener', build):
        if method == 'GET':
            result = http_get_transport('https://synthetic.invalid/models', {}, 5)
        else:
            result = http_transport('https://synthetic.invalid/responses', {}, {'input': 'hi'}, 5)
    assert result == {'data': []} and response.read_limit == 8_000_001


@pytest.mark.parametrize('raw,message', [(b'x'*8_000_001, '8 MB'), (b'{bad-json', 'invalid JSON'), (b'[]', 'non-object')], ids=['oversize', 'malformed-json', 'nonobject-json'])
def test_http_reader_rejects_oversize_invalid_and_nonobject_bodies(raw, message):
    class Opener:
        def open(self, *_args, **_kwargs): return Response(raw)
    with patch('urllib.request.build_opener', return_value=Opener()):
        with pytest.raises(ProviderFailure, match=message):
            http_get_transport('https://synthetic.invalid/models', {}, 5)


@pytest.mark.parametrize('exception', [
    urllib.error.HTTPError('https://synthetic.invalid', 401, 'private-body-marker', {}, io.BytesIO(b'private-body-marker')),
    urllib.error.URLError('private-body-marker'), TimeoutError('private-body-marker'),
])
def test_transport_failures_do_not_expose_error_bodies(exception):
    class Opener:
        def open(self, *_args, **_kwargs): raise exception
    with patch('urllib.request.build_opener', return_value=Opener()):
        with pytest.raises(ProviderFailure) as error:
            http_get_transport('https://synthetic.invalid/models', {}, 5)
    assert 'private-body-marker' not in str(error.value)


def test_redirect_refused_without_forwarding_authorization():
    with pytest.raises(ProviderFailure, match='redirect refused'):
        _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid')


def chat(text='hi', finish='stop'):
    return {'model': 'returned-model', 'choices': [{'message': {'content': text}, 'finish_reason': finish}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12,
                      'prompt_tokens_details': {'cached_tokens': 0}}}


def test_explicit_chat_endpoint_uses_correct_payload_and_normalizes_usage():
    seen = []
    def send(url, headers, payload, timeout):
        assert url == 'https://synthetic.invalid/v1/chat/completions'
        assert payload == {'model': 'requested-model', 'messages': [{'role': 'user', 'content': 'task'}], 'store': False, 'max_completion_tokens': 55}
        seen.append(payload)
        return chat()
    result = call_provider(connection(endpoint='chat-completions'), {'model': 'requested-model', 'max_output_tokens': 55}, 'task', send)
    assert len(seen) == 1 and result['text'] == 'hi' and result['complete']
    assert result['usage'] == {'input_tokens': 10, 'output_tokens': 2, 'cached_input_tokens': 0, 'cache_write_tokens': None}
    assert result['returned_model'] == 'returned-model' and result['finish_reason'] == 'stop'


@pytest.mark.parametrize('finish', ['length', 'content_filter', 'tool_calls', None])
def test_chat_nonstop_completion_keeps_evidence_but_is_incomplete(finish):
    result = normalize_response('openai', chat('partial', finish), 'chat-completions')
    assert result['text'] == 'partial' and result['usage']['output_tokens'] == 2
    assert result['complete'] is False


def test_malformed_chat_is_not_a_successful_text_response():
    for body in [{}, {'choices': None}, {'choices': []}, {'choices': [None]}, {'choices': [{}, {}]}]:
        assert not normalize_response('openai', body, 'chat-completions')['complete']


def test_responses_remains_the_default_endpoint():
    def send(url, _headers, payload, _timeout):
        assert url.endswith('/responses')
        assert payload == {'model': 'chosen', 'input': 'task', 'store': False, 'max_output_tokens': 1024}
        return {'status': 'completed', 'output_text': 'answer'}
    assert call_provider(connection(), {'model': 'chosen'}, 'task', send)['text'] == 'answer'


def test_ollama_length_is_incomplete_even_when_done_is_true():
    body = {'message': {'content': 'partial'}, 'done': True, 'done_reason': 'length', 'prompt_eval_count': 10, 'eval_count': 32}
    result = normalize_response('ollama', body)
    assert not result['complete'] and result['finish_reason'] == 'length'
    assert result['text'] == 'partial' and result['usage']['output_tokens'] == 32


@pytest.mark.parametrize('kind', ['openai', 'ollama'])
def test_truncated_answers_fail_workflow_and_retain_usage(kind):
    from prompt_tournament.workflow import run_task
    from prompt_tournament.workflow_cli import demo_task
    task = demo_task()
    task['providers'] = {'test': connection(kind, endpoint='chat-completions' if kind == 'openai' else 'chat')}
    task['models'] = [{'id': 'candidate', 'provider': 'test', 'model': 'chosen'}]
    body = chat('partial', 'length') if kind == 'openai' else {'message': {'content': 'partial'}, 'done': True, 'done_reason': 'length', 'prompt_eval_count': 10, 'eval_count': 32}
    result = run_task(task, allow_network=True, mode='batch', transport=lambda *_: body)
    assert result['status'] == 'failed' and len(result['calls']) == len(task['artifacts'])
    assert all(row['status'] == 'failed' and row['text'] == 'partial' and row['usage']['input_tokens'] == 10 for row in result['calls'])
    assert all('incomplete' in row['error']['message'] for row in result['calls'])


@pytest.mark.parametrize('body,status', [(chat(), 'text-response'), (chat(''), 'empty'), (chat('partial', 'length'), 'incomplete')])
def test_probe_is_one_explicit_bounded_greeting(body, status):
    seen = []
    def send(_url, _headers, payload, _timeout):
        assert payload['max_completion_tokens'] == 32
        assert payload['messages'] == [{'role': 'user', 'content': 'Reply with exactly: hi'}]
        seen.append(payload)
        return body
    result = probe_model(connection(endpoint='chat-completions'), {'model': 'chosen', 'max_output_tokens': 500}, send)
    assert result['status'] == status and len(seen) == 1
    assert 'response_id' not in result and 'Authorization' not in json.dumps(result)


def test_probe_failure_is_sanitized_and_oversize_capture_is_marked():
    def fail(*_): raise RuntimeError('private-body-marker')
    failure = probe_model(connection(), {'model': 'chosen'}, fail)
    assert failure['status'] == 'failed' and 'private-body-marker' not in json.dumps(failure)
    result = probe_model(connection(endpoint='chat-completions'), {'model': 'chosen'}, lambda *_: chat('x'*5000))
    assert result['text'] == 'x'*4096 and result['capture_truncated']
    assert result['original_text_characters'] == 5000


def test_ollama_probe_uses_chat_num_predict_without_discovery():
    seen = []
    def send(url, _headers, payload, _timeout):
        seen.append(url)
        assert url.endswith('/api/chat') and payload['options'] == {'num_predict': 32}
        assert payload['messages'] == [{'role': 'user', 'content': 'Reply with exactly: hi'}]
        return {'model': 'chosen', 'message': {'content': 'hi'}, 'done': True, 'done_reason': 'stop', 'prompt_eval_count': 12, 'eval_count': 1}
    result = probe_model(connection('ollama'), {'model': 'chosen'}, send)
    assert result['status'] == 'text-response' and len(seen) == 1
    assert result['usage']['input_tokens'] == 12 and result['usage']['output_tokens'] == 1


def test_import_does_not_discover_or_probe():
    code = "from unittest.mock import patch\nwith patch('urllib.request.build_opener', side_effect=AssertionError('network on import')):\n import prompt_tournament.providers\n"
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    completed = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=environment)
    assert completed.returncode == 0, completed.stderr
