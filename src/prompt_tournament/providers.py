"""Explicit OpenAI/Ollama execution with injectable transport and usage evidence.

Adapted from CinvanaAI's Model Provider Compatibility Lab and the provider
normalization in Transcript Model Evaluator. No model discovery or calls occur
on import. Network requests happen only through an explicitly invoked adapter.
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from typing import Any, Callable

Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class ProviderFailure(RuntimeError):
    """A bounded public error; never includes headers or raw error bodies."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderFailure(f"Provider redirect refused (HTTP {code}). Check the configured base URL.")


def http_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
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


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalize_response(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    if kind == 'openai':
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
        completed = body.get('done', True) is True
    return {'text': text if isinstance(text, str) else '', 'usage': usage, 'usage_raw': raw, 'returned_model': body.get('model'), 'response_id': body.get('id'), 'complete': completed}


def call_provider(provider: dict[str, Any], model: dict[str, Any], prompt: str, transport: Transport = http_transport) -> dict[str, Any]:
    kind = provider['kind']
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    if provider.get('api_key_env'):
        key = os.environ.get(provider['api_key_env'], '').strip()
        if not key:
            raise ProviderFailure(f"Required environment variable {provider['api_key_env']} is unset.")
        headers['Authorization'] = f'Bearer {key}'
    if kind == 'openai':
        path = '/responses'
        payload = {'model': model['model'], 'input': prompt, 'store': False, 'max_output_tokens': model.get('max_output_tokens', 1024)}
    else:
        path = '/api/chat'
        payload = {'model': model['model'], 'messages': [{'role': 'user', 'content': prompt}], 'stream': False, 'options': {'num_predict': model.get('max_output_tokens', 1024)}}
    body = transport(provider['base_url'].rstrip('/') + path, headers, payload, provider.get('timeout_seconds', 90))
    if not isinstance(body, dict):
        raise ProviderFailure('Provider transport returned a non-object response.')
    return normalize_response(kind, body)


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
