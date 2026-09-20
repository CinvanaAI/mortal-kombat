"""Strict decision fields with tolerance for a single JSON object in prose."""
from __future__ import annotations

import json
import math

from .engine import JudgeDecision, WINNERS
from .providers import ProviderFailure

JUDGE_PROTOCOL = 'blind-pair-v1'


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key.')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite JSON number.')


def parse_provider_decision(text: str) -> JudgeDecision:
    """Accept one decision object, including fences/prose, without field coercion."""
    def decode(value):
        return json.loads(value, object_pairs_hook=_unique_object, parse_constant=_reject_constant)

    try:
        try:
            payload = decode(text)
        except json.JSONDecodeError:
            # Like the retained parser, accept a single object inside text. Do
            # not select among several objects or unwrap a JSON array/string.
            start, end = text.find('{'), text.rfind('}')
            if start < 0 or end <= start:
                raise ValueError('No object.')
            if any(char in text[:start] + text[end + 1:] for char in '[]'):
                raise ValueError('Array wrapper.')
            payload = decode(text[start:end + 1])
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProviderFailure('Judge must return one unambiguous JSON decision object.') from exc
    if not isinstance(payload, dict):
        raise ProviderFailure('Judge must return a JSON decision object.')
    winner = payload.get('winner')
    if not isinstance(winner, str) or winner.strip() not in WINNERS:
        raise ProviderFailure('Judge winner must be one of the documented outcomes.')
    reason = payload.get('short_reason')
    if not isinstance(reason, str) or not reason.strip():
        raise ProviderFailure('Judge short_reason must be a nonempty string.')
    confidence = payload.get('confidence')
    if confidence is not None and (
        isinstance(confidence, bool) or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1 or not math.isfinite(confidence)
    ):
        raise ProviderFailure('Judge confidence must be null or a finite number from 0 to 1.')
    return JudgeDecision(winner.strip(), reason.strip(), confidence)


def remap_winner(winner: str, *, swapped: bool) -> str:
    """Translate displayed A/B back to caller A/B, including disqualification."""
    if not swapped:
        return winner
    return {
        'model_a_better': 'model_b_better',
        'model_b_better': 'model_a_better',
        'model_a_disqualified': 'model_b_disqualified',
        'model_b_disqualified': 'model_a_disqualified',
        'both_disqualified': 'both_disqualified',
    }[winner]
