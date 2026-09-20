"""Strict recovered judgments, blinded assignment, and saved evidence joins."""
from __future__ import annotations

import copy
from html import escape, unescape
import json
import re

import pytest

from prompt_tournament import workflow
from prompt_tournament.engine import parse_judge_output
from prompt_tournament.judging import JUDGE_PROTOCOL, parse_provider_decision
from prompt_tournament.providers import ProviderFailure
from prompt_tournament.report import render_report
from prompt_tournament.workflow_cli import demo_task


VALID = {'winner': 'model_a_better', 'short_reason': 'A preserves both requested fields.', 'confidence': 0.82}
OUTCOMES = ('model_a_better', 'model_b_better', 'model_a_disqualified', 'model_b_disqualified', 'both_disqualified')
ALPHA = 'alpha-candidate-id'
ZETA = 'zeta-candidate-id'


@pytest.mark.parametrize('wrapper', [
    '{}', '  {}\n', '```json\n{}\n```', '```JSON\r\n{}\r\n```',
    '```\n{}\n```', 'Final decision:\n{}', '{}\nThat is my judgment.',
    'Here is the verdict:\n```json\n{}\n```\nEnd of judgment.',
])
def test_one_valid_decision_is_recovered_without_altering_fields(wrapper):
    raw = wrapper.format(json.dumps(VALID))
    decision = parse_provider_decision(raw)
    assert (decision.winner, decision.short_reason, decision.confidence) == (
        VALID['winner'], VALID['short_reason'], VALID['confidence'])


def test_quoted_delimiters_and_escaped_quotes_inside_reason_are_data():
    value = {**VALID, 'short_reason': 'A retained {owner}, [action], café and "quoted text".'}
    decision = parse_provider_decision('Result:\n```json\n' + json.dumps(value, ensure_ascii=False) + '\n```')
    assert decision.short_reason == value['short_reason']


@pytest.mark.parametrize('confidence', [None, 0, 1, 0.25])
def test_confidence_optional_and_closed_interval_endpoints(confidence):
    assert parse_provider_decision(json.dumps({**VALID, 'confidence': confidence})).confidence == confidence
    no_confidence = {key: value for key, value in VALID.items() if key != 'confidence'}
    assert parse_provider_decision(json.dumps(no_confidence)).confidence is None


@pytest.mark.parametrize('raw', [
    '', 'A was better.', 'null', '[]', '[' + json.dumps(VALID) + ']',
    'Result: [' + json.dumps(VALID) + ']', json.dumps(json.dumps(VALID)),
    json.dumps({'decision': VALID}), '{"decision":' + json.dumps(VALID),
    json.dumps(VALID)[:-1], str(VALID), json.dumps(VALID)[:-1] + ',}',
    json.dumps(VALID) + '\n' + json.dumps({**VALID, 'winner': 'model_b_better'}),
    '```json\n' + json.dumps(VALID) + '\n```\n```json\n' + json.dumps(VALID) + '\n```',
    '{"winner":"model_b_better","winner":"model_a_better","short_reason":"duplicate"}',
    '```json\n{"winner":"model_a_better","short_reason":null,"short_reason":"duplicate"}\n```',
])
def test_malformed_or_ambiguous_objects_are_not_repaired_or_selected(raw):
    with pytest.raises(ProviderFailure):
        parse_provider_decision(raw)


@pytest.mark.parametrize(('field', 'value'), [
    ('winner', 'tie'), ('winner', True), ('winner', None),
    ('short_reason', None), ('short_reason', 42), ('short_reason', {}), ('short_reason', ' '),
    ('confidence', True), ('confidence', False), ('confidence', '0.82'),
    ('confidence', float('nan')), ('confidence', float('inf')),
    ('confidence', -0.1), ('confidence', 1.1),
    pytest.param('confidence', 10**400, id='confidence-huge-integer'),
])
def test_wrapping_never_bypasses_strict_decision_fields(field, value):
    raw = '```json\n' + json.dumps({**VALID, field: value}) + '\n```'
    with pytest.raises(ProviderFailure):
        parse_provider_decision(raw)


def test_legacy_parser_keeps_its_existing_clamping_contract():
    raw = '```json\n' + json.dumps({**VALID, 'confidence': 3}) + '\n```'
    assert parse_judge_output(raw).confidence == 1.0
    with pytest.raises(ProviderFailure):
        parse_provider_decision(raw)


def task_with_fixture_candidates():
    task = demo_task()
    task['models'] = task['models'][:2]
    for model, identity in zip(task['models'], (ALPHA, ZETA)):
        model['id'] = identity
    task['providers'] = {'synthetic': {'kind': 'ollama', 'base_url': 'http://127.0.0.1:1'}}
    task['judge'] = {'kind': 'provider', 'model': {'id': 'judge', 'provider': 'synthetic', 'model': 'synthetic-judge'}}
    return task


def run_judged(monkeypatch, *, swap=False, winner='model_a_better', failure=None, task=None):
    """Fixture candidates and one injected response per pair: never HTTP."""
    monkeypatch.setattr(workflow, '_random_swap', lambda: swap)
    task = task or task_with_fixture_candidates()
    requests = []
    raw = 'Final judgment:\n```json\n' + json.dumps({**VALID, 'winner': winner}) + '\n```'
    if failure == 'parse':
        raw = json.dumps(VALID) + '\n' + json.dumps({**VALID, 'winner': 'model_b_better'})
    elif failure == 'huge-confidence':
        raw = json.dumps({**VALID, 'confidence': 10**400})

    def transport(url, headers, payload, timeout):
        assert url == 'http://127.0.0.1:1/api/chat'
        assert payload['model'] == 'synthetic-judge'
        requests.append(copy.deepcopy(payload))
        if failure == 'transport':
            raise RuntimeError('synthetic transport failure; not an actual connection')
        return {'message': {'content': raw}, 'done': failure != 'incomplete',
                'done_reason': 'length' if failure == 'incomplete' else 'stop',
                'model': 'synthetic-judge', 'prompt_eval_count': 123, 'eval_count': 17}

    result = workflow.run_task(task, mode='battle', allow_network=True, transport=transport)
    return result, requests, raw


def comparison_html(result, index=1):
    original = copy.deepcopy(result)
    html = render_report(result)
    assert result == original, 'Rendering must leave recorded evidence unchanged.'
    marker = '<article id="comparison-' + str(index) + '">'
    assert marker in html
    return html.partition(marker)[2].partition('</article>')[0]


def visible_text(html):
    return unescape(re.sub('<[^>]*>', '', html))


@pytest.mark.parametrize('swap', [False, True], ids=['canonical-order', 'reversed-order'])
@pytest.mark.parametrize('winner', OUTCOMES)
def test_blinded_decision_maps_every_outcome_to_real_candidates(monkeypatch, swap, winner):
    result, requests, raw = run_judged(monkeypatch, swap=swap, winner=winner)
    assert len(requests) == result['provider_calls_attempted'] == 1
    assert len(result['candidate_outputs']) == 4
    assert len(result['calls']) == 5
    decision = result['decisions'][0]
    call = result['calls'][-1]
    # The insertion challenger is ZETA; ALPHA is the seeded incumbent.
    assert (decision['model_a'], decision['model_b']) == (ZETA, ALPHA)
    shown_a, shown_b = (ALPHA, ZETA) if swap else (ZETA, ALPHA)
    assignment = {'model_a': shown_a, 'model_b': shown_b}
    assert decision['judge_assignment'] == call['judge_assignment'] == assignment
    assert decision['judge_protocol'] == call['judge_protocol'] == JUDGE_PROTOCOL
    assert decision['judge_call_sequence'] == call['sequence'] == 5
    assert decision['judge_winner'] == winner
    swapped_outcomes = {'model_a_better': 'model_b_better', 'model_b_better': 'model_a_better',
                        'model_a_disqualified': 'model_b_disqualified', 'model_b_disqualified': 'model_a_disqualified',
                        'both_disqualified': 'both_disqualified'}
    assert decision['winner'] == (swapped_outcomes[winner] if swap else winner)
    assert decision['reason'] == VALID['short_reason']
    assert call['text'] == raw and call['status'] == 'completed'
    request = requests[0]['messages'][0]['content']
    evidence = json.loads(request.partition('\n\n')[2])
    assert set(evidence) == {'task', 'rubric', 'artifacts'}
    assert ALPHA not in request and ZETA not in request
    assert 'lexically smaller' not in request and 'tie-break' in request
    outputs = {(item['candidate_id'], item['artifact_id']): item['text'] for item in result['candidate_outputs']}
    for item, artifact in zip(evidence['artifacts'], result['task']['artifacts']):
        assert item['source'] == artifact['text']
        assert item['model_a_output'] == outputs[shown_a, artifact['id']]
        assert item['model_b_output'] == outputs[shown_b, artifact['id']]
    ranking = result['tournament']['current_ranking']
    ranked = [item['model_id'] for item in ranking if item['status'] == 'Ranked']
    disqualified = {item['model_id'] for item in ranking if item['status'] == 'Disqualified'}
    expected = {
        'model_a_better': ([shown_a, shown_b], set()),
        'model_b_better': ([shown_b, shown_a], set()),
        'model_a_disqualified': ([shown_b], {shown_a}),
        'model_b_disqualified': ([shown_a], {shown_b}),
        'both_disqualified': ([], {shown_a, shown_b}),
    }
    assert (ranked, disqualified) == expected[winner]
    assert result['status'] == ('completed' if ranked else 'no-ranked-candidates')
    result['calls'].reverse()  # A report must join records by evidence, not position.
    article = comparison_html(result)
    text = visible_text(article)
    assert 'A = ' + shown_a + '; B = ' + shown_b in text
    assert 'A/B references in the explanation use the order shown to the judge.' in text
    assert 'Inspect matching provider-judge request and response' in text
    assert escape(raw) in article and escape(request) in article
    if winner.endswith('_better'):
        assert 'Winner: ' + ranked[0] in text
    elif winner == 'both_disqualified':
        assert 'Both candidates disqualified; no winner.' in text
    else:
        assert 'Disqualified: ' + next(iter(disqualified)) in text


@pytest.mark.parametrize('swap', [False, True])
@pytest.mark.parametrize('failure', ['transport', 'incomplete', 'parse', 'huge-confidence'])
def test_failed_judgment_keeps_the_assignment_before_or_after_response(monkeypatch, swap, failure):
    result, requests, raw = run_judged(monkeypatch, swap=swap, failure=failure)
    assert result['status'] == 'failed' and result['tournament'] is None and result['decisions'] == []
    assert len(requests) == 1 and len(result['candidate_outputs']) == 4
    call = result['calls'][-1]
    assert call['judge_protocol'] == JUDGE_PROTOCOL
    assert call['judge_assignment'] == ({'model_a': ALPHA, 'model_b': ZETA} if swap else {'model_a': ZETA, 'model_b': ALPHA})
    assert call['status'] == ('completed' if failure in ('parse', 'huge-confidence') else 'failed')
    if failure != 'transport':
        assert call['text'] == raw
        assert call['usage']['input_tokens'] == 123 and call['usage']['output_tokens'] == 17
    html = render_report(result)
    assert 'Judge calls without a matched decision' in html
    assert 'Inspect matching provider-judge request and response' not in html
    assert 'No comparison decision was recorded.' in html


@pytest.mark.parametrize('tamper', [
    'assignment', 'sequence', 'boolean-sequence', 'protocol', 'normalized-winner',
    'presented-winner', 'reason', 'confidence', 'call-status', 'request-identity',
])
def test_report_refuses_inconsistent_blind_evidence(monkeypatch, tamper):
    result, _, _ = run_judged(monkeypatch, swap=True)
    decision, call = result['decisions'][0], result['calls'][-1]
    if tamper == 'assignment':
        call['judge_assignment'] = {'model_a': ZETA, 'model_b': ALPHA}
    elif tamper == 'sequence':
        decision['judge_call_sequence'] = 123
    elif tamper == 'boolean-sequence':
        decision['judge_call_sequence'] = True
    elif tamper == 'protocol':
        call['judge_protocol'] = 'unknown-protocol'
    elif tamper == 'normalized-winner':
        decision['winner'] = 'model_a_better'
    elif tamper == 'presented-winner':
        decision['judge_winner'] = 'model_b_better'
    elif tamper == 'reason':
        decision['reason'] = 'An unrelated reason.'
    elif tamper == 'confidence':
        decision['confidence'] = 0.1
    elif tamper == 'call-status':
        call['status'] = 'failed'
    else:
        preface, _, body = call['request_text'].partition('\n\n')
        evidence = json.loads(body)
        evidence['model_a'] = ALPHA
        call['request_text'] = preface + '\n\n' + json.dumps(evidence)
    article = comparison_html(result)
    assert 'No request has been assigned to this decision.' in article
    assert 'Inspect matching provider-judge request and response' not in article
    assert 'Order shown to the judge:' not in article
    assert 'Judge calls without a matched decision' in render_report(result)


def test_report_refuses_two_indistinguishable_matching_call_records(monkeypatch):
    result, _, _ = run_judged(monkeypatch)
    result['calls'].append(copy.deepcopy(result['calls'][-1]))
    article = comparison_html(result)
    assert 'A unique matching provider-judge call could not be established' in article
    assert 'Inspect matching provider-judge request and response' not in article
    assert render_report(result).count('Inspect unmatched judge call 5') == 2
