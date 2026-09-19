"""Offline consumer tests for researched facts and source provenance."""
import copy
import hashlib
import json

import pytest

from prompt_tournament.model_research import research_model
from prompt_tournament.providers import ProviderFailure

SOURCE = ('Model: specimen-text-1\nContext window: 8192 tokens.\n'
          'Maximum output: 1024 tokens.\nInput modalities: text and image.\n'
          'Output modality: text.\n')
PROVIDER = {'kind': 'ollama', 'base_url': 'http://127.0.0.1:11434'}
MODEL = {'model': 'research-fixture', 'max_output_tokens': 2048}
FACTS = {
    'model_identification': {'model_id': 'specimen-text-1', 'quote': 'Model: specimen-text-1'},
    'context_window_tokens': {'value': 8192, 'quote': 'Context window: 8192 tokens.'},
    'max_output_tokens': {'value': 1024, 'quote': 'Maximum output: 1024 tokens.'},
    'input_modalities': {'value': ['text', 'image'], 'quote': 'Input modalities: text and image.'},
    'output_modalities': {'value': ['text'], 'quote': 'Output modality: text.'},
}


def invoke(facts=None, *, source=SOURCE, target='specimen-text-1', provider=None, model=None, raw=None, complete=True):
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append((url, headers, payload, timeout))
        return {'done': complete, 'done_reason': 'stop' if complete else 'length',
                'model': 'research-fixture-snapshot', 'prompt_eval_count': 101, 'eval_count': 203,
                'message': {'content': raw if raw is not None else json.dumps(FACTS if facts is None else facts)}}

    result = research_model(target, source, 'https://docs.example.org/models/specimen-text-1',
                            PROVIDER if provider is None else provider,
                            MODEL if model is None else model, transport=transport)
    return result, calls


def test_one_call_returns_full_fact_and_source_receipt_without_target_execution():
    result, calls = invoke()
    assert len(calls) == 1
    assert calls[0][0] == 'http://127.0.0.1:11434/api/chat'
    assert calls[0][2]['model'] == 'research-fixture'
    assert calls[0][2]['options']['num_predict'] == 2048
    assert 'specimen-text-1' in calls[0][2]['messages'][0]['content']
    assert result['schema'] == 'mortal-kombat.model-research.v1'
    assert result['status'] == 'completed'
    assert result['source']['text'] == SOURCE
    assert result['source']['sha256'] == hashlib.sha256(SOURCE.encode()).hexdigest()
    assert result['source']['recorded_at'].endswith('+00:00')
    assert result['catalog']['context_window_tokens'] == 8192
    assert result['evidence']['context_window_tokens']['quote'] == 'Context window: 8192 tokens.'
    assert result['model_identification']['exact_identifier_in_quote'] is True
    assert result['researcher']['returned_model'] == 'research-fixture-snapshot'
    assert result['researcher']['usage']['input_tokens'] == 101
    assert result['unknowns'] == []


def test_missing_documentation_stays_unknown_with_no_inferred_modalities():
    facts = copy.deepcopy(FACTS)
    for key in ['max_output_tokens', 'output_modalities']:
        facts[key] = {'value': None, 'quote': None}
    result, _ = invoke(facts)
    assert result['catalog']['output_modalities'] is None
    assert result['catalog']['input_modalities'] == ['text', 'image']
    assert result['unknowns'] == ['max_output_tokens', 'output_modalities']


@pytest.mark.parametrize('field', ['model_identification', 'context_window_tokens', 'max_output_tokens', 'input_modalities', 'output_modalities'])
def test_every_known_fact_requires_a_verbatim_source_quote(field):
    facts = copy.deepcopy(FACTS)
    facts[field]['quote'] = 'Invented documentation that does not appear in the source'
    with pytest.raises(ValueError, match='verbatim'):
        invoke(facts)


def test_source_identity_mismatch_cannot_be_silently_reassigned():
    facts = copy.deepcopy(FACTS)
    facts['model_identification']['model_id'] = 'another-model'
    with pytest.raises(ValueError, match='different target'):
        invoke(facts)


def test_alias_association_is_visible_and_does_not_rename_the_target():
    facts = copy.deepcopy(FACTS)
    facts['model_identification']['model_id'] = 'specimen:1'
    result, _ = invoke(facts, target='specimen:1')
    assert result['target_model_id'] == 'specimen:1'
    assert result['model_identification']['quote'] == 'Model: specimen-text-1'
    assert result['model_identification']['exact_identifier_in_quote'] is False


def test_identifier_prefix_is_not_an_exact_identifier_match():
    facts = copy.deepcopy(FACTS)
    facts['model_identification']['model_id'] = 'specimen-text'
    result, _ = invoke(facts, target='specimen-text')
    assert result['model_identification']['exact_identifier_in_quote'] is False


@pytest.mark.parametrize('field,value', [
    ('context_window_tokens', True), ('context_window_tokens', -1),
    ('context_window_tokens', 8192.0), ('max_output_tokens', '1024'),
    ('input_modalities', []), ('input_modalities', ['text', 'text']),
    ('output_modalities', ['guessed-mode']), ('input_modalities', 'text'),
])
def test_invalid_fact_types_are_rejected(field, value):
    facts = copy.deepcopy(FACTS); facts[field]['value'] = value
    with pytest.raises(ValueError):
        invoke(facts)


def test_unknown_fact_cannot_keep_a_spurious_supporting_quote():
    facts = copy.deepcopy(FACTS); facts['max_output_tokens']['value'] = None
    with pytest.raises(ValueError, match='null quote'):
        invoke(facts)


@pytest.mark.parametrize('raw', [
    '```json\n{}\n```', '[]',
    '{"model_identification":{},"model_identification":{}}',
    '{"model_identification":{"model_id":"x","model_id":"y"}}',
    '{"x":NaN}',
])
def test_strict_json_and_duplicate_members_are_enforced(raw):
    with pytest.raises(ValueError):
        invoke(raw=raw)


def test_extra_fact_is_rejected_instead_of_saved_as_unchecked_metadata():
    facts = copy.deepcopy(FACTS); facts['cost'] = 0.001
    with pytest.raises(ValueError, match='exactly'):
        invoke(facts)


def test_excessive_json_nesting_has_a_controlled_validation_error():
    with pytest.raises(ValueError):
        invoke(raw='[' * 2000 + '0' + ']' * 2000)


def test_incomplete_or_empty_response_does_not_produce_catalog():
    with pytest.raises(ProviderFailure, match='incomplete'):
        invoke(complete=False)
    with pytest.raises(ProviderFailure, match='no text'):
        invoke(raw='')


@pytest.mark.parametrize('changes', [
    {'source_text': ''}, {'source_text': 'x' * 400001},
    {'source_url': 'http://docs.example.org/model'},
    {'source_url': 'https://username:secret@docs.example.org/model'},
    {'target_model_id': 'bad\nmodel'},
    {'research_model': {'model': 'researcher', 'max_output_tokens': True}},
    {'research_model': {'model': 'researcher', 'api_key': 'must-not-be-used'}},
    {'provider': {'kind': 'ollama', 'base_url': 'https://user:secret@example.org'}},
])
def test_invalid_inputs_fail_before_any_transport_call(changes):
    called = []
    args = dict(target_model_id='specimen-text-1', source_text=SOURCE,
                source_url='https://docs.example.org/model', provider=PROVIDER,
                research_model=MODEL, transport=lambda *a: called.append(a))
    args.update(changes)
    with pytest.raises((ValueError, ProviderFailure)):
        research_model(**args)
    assert called == []


def test_unexpected_transport_error_is_sanitized():
    def transport(*args):
        raise RuntimeError('private diagnostic sk-not-real-secret')
    with pytest.raises(ProviderFailure) as raised:
        research_model('specimen-text-1', SOURCE, 'https://docs.example.org/model', PROVIDER, MODEL, transport)
    assert 'sk-not-real-secret' not in str(raised.value)


def test_credentials_only_reach_adapter_headers_not_source_or_saved_receipt(monkeypatch):
    monkeypatch.setenv('MK_RESEARCH_TEST_KEY', 'not-a-real-provider-key')
    calls = []
    def transport(url, headers, payload, timeout):
        calls.append((headers, payload))
        return {'status': 'completed', 'model': 'returned-researcher', 'output_text': json.dumps(FACTS),
                'usage': {'input_tokens': 100, 'output_tokens': 200}}
    result = research_model('specimen-text-1', SOURCE, 'https://docs.example.org/model',
                            {'kind': 'openai', 'base_url': 'https://example.invalid/v1', 'api_key_env': 'MK_RESEARCH_TEST_KEY'},
                            MODEL, transport)
    assert calls[0][0]['Authorization'] == 'Bearer not-a-real-provider-key'
    assert 'not-a-real-provider-key' not in json.dumps(calls[0][1])
    assert 'not-a-real-provider-key' not in json.dumps(result)
    assert result['researcher']['endpoint'] == 'responses'
