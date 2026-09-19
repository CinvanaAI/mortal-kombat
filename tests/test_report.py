"""Visitor-facing evidence associations and inert local report rendering."""
from __future__ import annotations

import copy
from html.parser import HTMLParser
import json

import pytest

from prompt_tournament.report import render_report, save_report
from prompt_tournament.workflow import run_task
from prompt_tournament.workflow_cli import demo_task


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        return ''.join(child if isinstance(child, str) else child.text() for child in self.children)

    def find(self, tag=None, **attrs):
        found = []
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and all(child.attrs.get(key) == value for key, value in attrs.items()):
                    found.append(child)
                found.extend(child.find(tag, **attrs))
        return found


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('meta', 'link', 'br', 'hr', 'img', 'input'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        assert self.stack[-1].tag == tag, f'Unbalanced HTML: {tag}'
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def rendered(result):
    original = copy.deepcopy(result)
    document = Document(render_report(result))
    assert result == original, 'Rendering must not mutate evidence.'
    assert len(document.stack) == 1
    return document.root


def provider_task():
    task = demo_task()
    task['providers'] = {'mock': {'kind': 'ollama', 'base_url': 'http://127.0.0.1:1'}}
    task['models'] = [{'id': name, 'provider': 'mock', 'model': name} for name in ('alpha', 'beta', 'gamma')]
    task['judge'] = {'kind': 'provider', 'model': {'id': 'judge', 'provider': 'mock', 'model': 'judge'}}
    task['rubric'] = {'kind': 'pairwise', 'description': 'Retain the source details.'}
    return task


def provider_transport(*, fail_judge_at=None, incomplete=False, reason=None):
    judge_calls = 0

    def transport(url, headers, payload, timeout):
        nonlocal judge_calls
        if payload['model'] == 'judge':
            judge_calls += 1
            pair = json.loads(payload['messages'][0]['content'].partition('\n\n')[2])
            text = json.dumps({'winner': 'model_a_better', 'short_reason': reason or 'Prefer ' + pair['model_a'], 'confidence': 0.0})
            if judge_calls == fail_judge_at:
                text = 'not a valid decision'
        else:
            text = payload['model'] + ': retained text'
        return {'done': not incomplete, 'message': {'content': text}, 'model': payload['model'], 'prompt_eval_count': 12, 'eval_count': 4}

    return transport


def test_all_free_text_is_escaped_and_document_has_only_local_navigation():
    attack = '</pre><script>alert("x")</script><img src=x onerror=alert(1)>&'
    task = demo_task()
    task['id'] = attack
    task['instructions'] = attack
    task['artifacts'][0]['text'] = attack
    task['rubric']['description'] = attack
    task['models'][0]['id'] = attack
    task['models'][0]['fixture_outputs']['review'] = json.dumps({'owner': attack, 'action': attack})
    result = run_task(task)
    result['cost_summary']['note'] = attack
    document = rendered(result)
    assert not document.find('script') and not document.find('img')
    assert attack in [node.text() for node in document.find('pre')]
    assert attack in document.find('section', id='task')[0].text()
    assert attack in document.find('section', id='examples')[0].text()
    for node in document.find():
        assert not any(key.startswith('on') or key == 'src' for key in node.attrs)
        if 'href' in node.attrs:
            assert node.attrs['href'] == 'result.json' or node.attrs['href'].startswith('#')
    assert 'url(' not in document.find('style')[0].text()


def test_sources_outputs_expected_fields_and_checks_stay_with_their_example():
    result = run_task(demo_task())
    result['candidate_outputs'].reverse()
    result['calls'].reverse()
    document = rendered(result)
    for index, artifact in enumerate(result['task']['artifacts'], 1):
        example = document.find('section', id=f'example-{index}')[0]
        assert example.find('div', **{'class': 'source'})[0].find('pre')[0].text() == artifact['text']
        expected = example.find('details')[0]
        assert json.loads(expected.find('pre')[0].text()) == artifact['expected']
        cards = example.find('article', **{'class': 'response'})
        assert len(cards) == len(result['task']['models'])
        for card, model in zip(cards, result['task']['models']):
            assert card.find('h4')[0].text() == model['id']
            outputs = [item for item in result['candidate_outputs'] if item['artifact_id'] == artifact['id'] and item['candidate_id'] == model['id']]
            for output in outputs:
                assert card.find('pre')[0].text() == output['text']
                assert f'{output["assessment"]["score"]} / {output["assessment"]["maximum"]} exact fields' in card.text()
    assert '(field absent)' in document.find('section', id='examples')[0].text()


def test_disqualified_ordinals_are_not_quality_ranks_and_skipped_examples_are_visible():
    result = run_task(demo_task())
    dq = next(row for row in result['tournament']['current_ranking'] if row['status'] == 'Disqualified')
    dq['rank'] = 98765
    document = rendered(result)
    outcome = document.find('section', id='outcome')[0]
    table = outcome.find('table')[0]
    assert dq['model_id'] not in table.text()
    assert '98765' not in outcome.text()
    assert dq['model_id'] in outcome.text() and dq['reason'] in outcome.text()
    skipped = document.find('section', id='example-2')[0].find('article')[-1]
    assert 'Skipped after an earlier evaluation failure.' in skipped.text()
    assert not skipped.find('pre')


def test_failed_partial_responses_are_visible_even_when_no_candidate_output_was_accepted():
    result = run_task(provider_task(), allow_network=True, transport=provider_transport(incomplete=True))
    assert result['candidate_outputs'] == [] and result['status'] == 'no-ranked-candidates'
    document = rendered(result)
    assert not document.find('section', id='outcome')[0].find('table')
    assert 'No candidate received a quality rank.' in document.text()
    first = document.find('section', id='example-1')[0]
    for card, model in zip(first.find('article'), result['task']['models']):
        assert 'Call status: failed' in card.text()
        assert 'Retained failed response' in card.text()
        assert model['id'] + ': retained text' == card.find('pre')[0].text()
    assert 'Skipped after an earlier evaluation failure.' in document.find('section', id='example-2')[0].text()


@pytest.mark.parametrize('response', [None, ''], ids=['no-text', 'empty-text'])
def test_failed_call_distinguishes_no_response_from_empty_response(response):
    result = run_task(provider_task(), allow_network=True, transport=provider_transport(incomplete=True))
    result['calls'][0]['text'] = response
    card = rendered(result).find('section', id='example-1')[0].find('article')[0]
    expected = 'No response text was captured' if response is None else 'recorded response text was empty'
    assert expected in card.text()


def test_missing_record_is_not_invented_as_success_or_skipped_failure():
    result = run_task(demo_task(), mode='batch')
    target = result['task']['models'][0]['id'], result['task']['artifacts'][1]['id']
    result['calls'] = [call for call in result['calls'] if (call['candidate_id'], call['artifact_id']) != target]
    result['candidate_outputs'] = [item for item in result['candidate_outputs'] if (item['candidate_id'], item['artifact_id']) != target]
    card = rendered(result).find('section', id='example-2')[0].find('article')[0]
    assert 'Missing record.' in card.text()
    assert 'Skipped' not in card.text() and 'Output captured' not in card.text()


def test_provider_decisions_match_exact_pair_request_and_response_not_call_position():
    attack = '</pre><script>judge_text()</script>'
    result = run_task(provider_task(), allow_network=True, transport=provider_transport(reason=attack))
    judge_calls = [call for call in result['calls'] if call['phase'] == 'judge']
    assert len(judge_calls) >= 2
    result['calls'].reverse()
    document = rendered(result)
    assert not document.find('script')
    for index, decision in enumerate(result['decisions'], 1):
        comparison = document.find('article', id=f'comparison-{index}')[0]
        assert 'Winner: ' + decision['model_a'] in comparison.text()
        assert 'Recorded confidence: 0.0' in comparison.text()
        detail = comparison.find('details')[0]
        exact_texts = [node.text() for node in detail.find('pre')]
        matching = next(call for call in judge_calls if json.loads(call['request_text'].partition('\n\n')[2])['model_a'] == decision['model_a'])
        assert matching['request_text'] in exact_texts and matching['text'] in exact_texts
        assert all(call is matching or call['request_text'] not in exact_texts for call in judge_calls)
        assert attack in comparison.find('pre')[0].text()
    assert 'whole example bundle' in document.text()
    assert 'confidence is not a rubric score' in document.text()


@pytest.mark.parametrize('damage', ['missing', 'ambiguous'])
def test_unverifiable_judge_request_is_never_assigned_by_guess(damage):
    result = run_task(provider_task(), allow_network=True, transport=provider_transport())
    call = next(call for call in result['calls'] if call['phase'] == 'judge')
    if damage == 'missing':
        call['request_text'] = 'request unavailable'
    else:
        result['calls'].append(copy.deepcopy(call))
    comparison = rendered(result).find('article', id='comparison-1')[0]
    assert 'No request has been assigned' in comparison.text()
    assert not comparison.find('details')


def test_failed_tournament_retains_completed_decision_and_unparsed_judge_call():
    result = run_task(provider_task(), allow_network=True, transport=provider_transport(fail_judge_at=2))
    assert result['status'] == 'failed' and len(result['decisions']) == 1
    document = rendered(result)
    outcome = document.find('section', id='outcome')[0].text()
    assert 'failed before a final ranking was produced' in outcome
    assert 'capture mode' not in outcome and 'captured without a ranking' not in outcome
    assert len(document.find('article', id='comparison-1')[0].find('details')) == 1
    comparisons = document.find('section', id='comparisons')[0]
    assert 'Judge calls without a matched decision' in comparisons.text()
    assert 'not a valid decision' in [node.text() for node in comparisons.find('pre')]
    assert not document.find('article', id='comparison-2')


@pytest.mark.parametrize('mode', ['single', 'batch'])
def test_capture_reports_do_not_claim_judging_even_when_calls_fail(mode):
    task = provider_task()
    if mode == 'single':
        task['models'] = task['models'][:1]
    result = run_task(task, mode=mode, allow_network=True, transport=provider_transport(incomplete=True))
    assert result['status'] == 'failed'
    document = rendered(result)
    assert 'No judging or ranking was requested' in document.find('section', id='outcome')[0].text()
    assert 'Capture did not complete successfully' in document.text()
    assert 'This capture mode did not apply the rubric' in document.text()
    assert 'failed before a final ranking' not in document.text()
    assert 'Skipped after' not in document.text()


def test_rules_decision_has_no_invented_provider_request_and_save_api_preserves_json(tmp_path):
    result = run_task(demo_task())
    save_report(result, tmp_path)
    assert json.loads((tmp_path / 'result.json').read_text(encoding='utf-8')) == result
    document = Document((tmp_path / 'report.html').read_text(encoding='utf-8')).root
    comparison = document.find('article', id='comparison-1')[0]
    assert 'Deterministic rules decision' in comparison.text()
    assert 'Recorded confidence: not supplied' in comparison.text()
    assert not comparison.find('details')
    assert document.find('h1')[0].text() == 'Rubric Rumble'
