"""Explicit OpenAI/Ollama execution with injectable transport and usage evidence.

Adapted from CinvanaAI's Model Provider Compatibility Lab and the provider
normalization in Transcript Model Evaluator. No model discovery or calls occur
on import. Network requests happen only through an explicitly invoked adapter.
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any, Callable

Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]
GetTransport = Callable[[str, dict[str, str], float], dict[str, Any]]


class ProviderFailure(RuntimeError):
    """A bounded public error; never includes headers or raw error bodies."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderFailure(f"Provider redirect refused (HTTP {code}). Check the configured base URL.")


def _read_response(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(8_000_001)
    except urllib.error.HTTPError as exc:
        raise ProviderFailure(f"Provider returned HTTP {exc.code}; check model, credentials and account limits.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderFailure("Provider connection failed or timed out.") from None
    if len(raw) > 8_000_000:
        raise ProviderFailure('Provider response exceeded the 8 MB limit.')
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ProviderFailure('Provider returned invalid JSON.') from None
    if not isinstance(body, dict):
        raise ProviderFailure('Provider returned a non-object JSON response.')
    return body


def http_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    return _read_response(request, timeout)


def http_get_transport(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    """Read model discovery JSON, with the same limits as execution requests."""
    return _read_response(urllib.request.Request(url, headers=headers, method='GET'), timeout)


def _connection(provider: dict[str, Any]) -> tuple[str, str, str, dict[str, str], float]:
    """Validate discovery independently, because it can run before task setup."""
    if not isinstance(provider, dict) or set(provider) - {'kind', 'base_url', 'api_key_env', 'timeout_seconds', 'endpoint'}:
        raise ProviderFailure('Provider settings contain unsupported fields.')
    kind = provider.get('kind')
    if kind not in ('openai', 'ollama'):
        raise ProviderFailure('Provider kind must be openai or ollama.')
    endpoints = ('responses', 'chat-completions') if kind == 'openai' else ('chat',)
    endpoint = provider.get('endpoint', endpoints[0])
    if endpoint not in endpoints:
        raise ProviderFailure('Provider endpoint is not supported for its kind.')
    base = provider.get('base_url')
    try:
        if not isinstance(base, str) or not base or any(c.isspace() or not c.isprintable() for c in base):
            raise ValueError
        url = urlsplit(base)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError
        _ = url.port
    except ValueError:
        raise ProviderFailure('Provider URL requires HTTPS (or loopback HTTP), a valid host, and no embedded credentials, query or fragment.') from None
    timeout = provider.get('timeout_seconds', 90)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
        raise ProviderFailure('Provider timeout must be between 1 and 600 seconds.')
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    env_name = provider.get('api_key_env')
    if kind == 'openai' and not env_name:
        raise ProviderFailure('OpenAI providers require an API key environment variable name.')
    if env_name is not None:
        if not isinstance(env_name, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', env_name):
            raise ProviderFailure('API key setting must be an environment variable name.')
        key = os.environ.get(env_name, '').strip()
        if not key:
            raise ProviderFailure(f'Required environment variable {env_name} is unset.')
        if '\r' in key or '\n' in key:
            raise ProviderFailure('API key environment variable contains invalid header characters.')
        headers['Authorization'] = f'Bearer {key}'
    return kind, endpoint, base.rstrip('/'), headers, timeout


def list_models(provider: dict[str, Any], transport: GetTransport = http_get_transport) -> list[str]:
    """Return sorted unique visible IDs, not a guarantee of task compatibility.

    Explicit invocation performs one GET. Keys are read only from the named
    environment variable; no credential files, generation or retries are used.
    """
    kind, _, base, headers, timeout = _connection(provider)
    body = transport(base + ('/models' if kind == 'openai' else '/api/tags'), headers, timeout)
    if not isinstance(body, dict):
        raise ProviderFailure('Model discovery returned a non-object response.')
    rows = body.get('data' if kind == 'openai' else 'models')
    if not isinstance(rows, list):
        raise ProviderFailure('Model discovery returned an invalid model list.')
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ProviderFailure('Model discovery returned an invalid model entry.')
        model_id = row.get('id') if kind == 'openai' else row.get('name', row.get('model'))
        if not isinstance(model_id, str) or not model_id or any(c.isspace() or not c.isprintable() for c in model_id):
            raise ProviderFailure('Model discovery returned an invalid model identifier.')
        ids.add(model_id)
    return sorted(ids)


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalize_response(kind: str, body: dict[str, Any], endpoint: str | None = None) -> dict[str, Any]:
    finish_reason = None
    if kind == 'openai' and endpoint == 'chat-completions':
        choices = body.get('choices')
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict) else {}
        message = choice.get('message') if isinstance(choice.get('message'), dict) else {}
        text = message.get('content')
        finish_reason = choice.get('finish_reason')
        raw = body.get('usage') if isinstance(body.get('usage'), dict) else {}
        details = raw.get('prompt_tokens_details') if isinstance(raw.get('prompt_tokens_details'), dict) else {}
        usage = {'input_tokens': _count(raw.get('prompt_tokens')), 'output_tokens': _count(raw.get('completion_tokens')), 'cached_input_tokens': _count(details.get('cached_tokens')), 'cache_write_tokens': _count(details.get('cache_write_tokens'))}
        completed = finish_reason == 'stop' and isinstance(text, str) and not message.get('refusal')
    elif kind == 'openai':
        text = body.get('output_text')
        if not isinstance(text, str):
            parts = []
            for item in body.get('output', []) if isinstance(body.get('output'), list) else []:
                if not isinstance(item, dict):
                    continue
                for part in item.get('content', []) if isinstance(item.get('content'), list) else []:
                    if isinstance(part, dict) and part.get('type') == 'output_text' and isinstance(part.get('text'), str):
                        parts.append(part['text'])
            text = '\n'.join(parts)
        raw = body.get('usage') if isinstance(body.get('usage'), dict) else {}
        details = raw.get('input_tokens_details') if isinstance(raw.get('input_tokens_details'), dict) else {}
        usage = {'input_tokens': _count(raw.get('input_tokens')), 'output_tokens': _count(raw.get('output_tokens')), 'cached_input_tokens': _count(details.get('cached_tokens')), 'cache_write_tokens': _count(details.get('cache_write_tokens'))}
        completed = body.get('status', 'completed') == 'completed'
    else:
        message = body.get('message') if isinstance(body.get('message'), dict) else {}
        text = message.get('content')
        usage = {'input_tokens': _count(body.get('prompt_eval_count')), 'output_tokens': _count(body.get('eval_count')), 'cached_input_tokens': _count(body.get('prompt_eval_cached_count')), 'cache_write_tokens': None}
        raw = {key: body.get(key) for key in ('prompt_eval_count', 'eval_count', 'prompt_eval_cached_count')}
        finish_reason = body.get('done_reason')
        completed = body.get('done', True) is True and finish_reason in (None, 'stop')
    return {'text': text if isinstance(text, str) else '', 'usage': usage, 'usage_raw': raw, 'returned_model': body.get('model'), 'response_id': body.get('id'), 'finish_reason': finish_reason, 'complete': completed}


def call_provider(provider: dict[str, Any], model: dict[str, Any], prompt: str, transport: Transport = http_transport) -> dict[str, Any]:
    kind, endpoint, base, headers, timeout = _connection(provider)
    if kind == 'openai' and endpoint == 'chat-completions':
        path = '/chat/completions'
        payload = {'model': model['model'], 'messages': [{'role': 'user', 'content': prompt}], 'store': False, 'max_completion_tokens': model.get('max_output_tokens', 1024)}
    elif kind == 'openai':
        path = '/responses'
        payload = {'model': model['model'], 'input': prompt, 'store': False, 'max_output_tokens': model.get('max_output_tokens', 1024)}
    else:
        path = '/api/chat'
        payload = {'model': model['model'], 'messages': [{'role': 'user', 'content': prompt}], 'stream': False, 'options': {'num_predict': model.get('max_output_tokens', 1024)}}
    body = transport(base + path, headers, payload, timeout)
    if not isinstance(body, dict):
        raise ProviderFailure('Provider transport returned a non-object response.')
    return normalize_response(kind, body, endpoint)


def probe_model(provider: dict[str, Any], model: dict[str, Any], transport: Transport = http_transport) -> dict[str, Any]:
    """Explicitly request a short greeting; visibility alone never triggers it.

    A text response establishes only that this request returned text. It does
    not certify model capabilities, task quality, or future availability.
    The recorded text is an exact prefix, capped at 4096 characters and marked
    if truncated. Errors never include transport exceptions or provider bodies.
    """
    try:
        result = call_provider(provider, {**model, 'max_output_tokens': 32}, 'Reply with exactly: hi', transport)
    except Exception:
        return {'status': 'failed', 'text': '', 'usage': None, 'returned_model': None,
                'finish_reason': None, 'error': 'The greeting request failed. Check the connection, selected endpoint, model and key environment variable.',
                'capture_truncated': False, 'original_text_characters': 0}
    text = result['text']
    if not result['complete']:
        status = 'incomplete'
    elif not text.strip():
        status = 'empty'
    else:
        status = 'text-response'
    return {'status': status, 'text': text[:4096], 'usage': result['usage'],
            'returned_model': result['returned_model'], 'finish_reason': result['finish_reason'],
            'error': None, 'capture_truncated': len(text) > 4096, 'original_text_characters': len(text)}


def estimate_cost(usage: dict[str, Any] | None, rates: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {'status': 'unavailable', 'amount': None, 'currency': rates.get('currency') if rates else None, 'basis': 'Returned token usage and user-configured rates; estimate, not an invoice.'}
    if not rates:
        return {**result, 'reason': 'No rates configured.'}
    if not usage or usage.get('input_tokens') is None or usage.get('output_tokens') is None:
        return {**result, 'reason': 'Provider did not return complete input/output usage.'}
    if usage.get('cache_write_tokens'):
        return {**result, 'reason': 'Cache-write tokens were reported; this estimator does not price cache writes.'}
    cached = usage.get('cached_input_tokens')
    input_tokens = usage['input_tokens']
    if cached is not None and cached > input_tokens:
        return {**result, 'reason': 'Cached token count exceeds total input tokens.'}
    if rates.get('cached_input_per_million') is not None and cached is None:
        return {**result, 'reason': 'Cached-input rate supplied but provider did not report cache usage.'}
    if cached and rates.get('cached_input_per_million') is None:
        return {**result, 'reason': 'Cached tokens reported without a configured cached-input rate.'}
    cached = cached or 0
    amount = ((input_tokens-cached)*rates['input_per_million'] + cached*rates.get('cached_input_per_million', 0) + usage['output_tokens']*rates['output_per_million']) / 1_000_000
    if not math.isfinite(amount):
        return {**result, 'reason': 'Estimate is non-finite.'}
    return {**result, 'status': 'estimated', 'amount': amount, 'rate_source': rates['source'], 'rates_as_of': rates['as_of']}
