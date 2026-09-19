"""Local, escaped HTML evidence report with no remote dependencies."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path


def _esc(value) -> str:
    return escape(str(value))


def _pre(value) -> str:
    return '<pre>' + _esc(value) + '</pre>'


def _json(value) -> str:
    return _pre(json.dumps(value, indent=2, ensure_ascii=False))


def _details(label: str, content: str) -> str:
    return '<details><summary>' + _esc(label) + '</summary>' + content + '</details>'


def _outcome(result: dict) -> str:
    mode = result.get('execution_mode', 'tournament')
    entries = (result.get('tournament') or {}).get('current_ranking', [])
    ranked = [entry for entry in entries if entry.get('status') == 'Ranked']
    disqualified = [entry for entry in entries if entry.get('status') == 'Disqualified']
    content = '<section id="outcome"><h2>Run outcome</h2>'
    if mode in ('single', 'batch'):
        content += '<p>No judging or ranking was requested in this capture mode.</p>'
        if result['status'] != 'completed':
            content += '<p>Capture did not complete successfully for every requested response. Inspect the individual records below.</p>'
    elif result['status'] == 'failed':
        content += '<p>The ' + _esc(mode) + ' failed before a final ranking was produced. Recorded responses and completed comparisons are retained below.</p>'
    elif not ranked:
        content += '<p>No candidate received a quality rank. Inspect disqualifications and response records below.</p>'
    if ranked and mode not in ('single', 'batch') and result['status'] != 'failed':
        rows = ''.join(
            '<tr><td data-label="Rank">' + _esc(entry['rank'])
            + '</td><th scope="row" data-label="Candidate">' + _esc(entry['model_id'])
            + '</th></tr>' for entry in ranked
        )
        content += '<table class="rankings"><caption>Final ranking of eligible candidates</caption><thead><tr><th scope="col">Rank</th><th scope="col">Candidate</th></tr></thead><tbody>' + rows + '</tbody></table>'
        if not result.get('decisions'):
            content += '<p>No pairwise comparison was recorded; placement alone is not evidence of superiority.</p>'
    if disqualified:
        content += '<h3>Disqualified candidates</h3><p>These candidates have no quality rank. Their order here is not a performance comparison.</p><ul>'
        content += ''.join('<li><strong>' + _esc(entry['model_id']) + '</strong>: ' + _esc(entry.get('reason', 'No reason recorded.')) + '</li>' for entry in disqualified)
        content += '</ul>'
    return content + '</section>'


def _checks(assessment: dict | None) -> str:
    if assessment is None:
        return ''
    content = '<div class="checks"><h4>Exact-field checks</h4><p><strong>' + _esc(assessment['score']) + ' / ' + _esc(assessment['maximum']) + ' exact fields</strong> · ' + _esc(assessment['reason']) + '</p><ul>'
    for check in assessment['checks']:
        actual = json.dumps(check['actual'], ensure_ascii=False) if check.get('present', True) else '(field absent)'
        content += '<li><strong>' + ('Pass' if check['passed'] else 'Fail') + '</strong> — ' + _esc(check['field']) + ': expected ' + _esc(json.dumps(check['expected'], ensure_ascii=False)) + '; received ' + _esc(actual) + '</li>'
    return content + '</ul></div>'


def _call_evidence(call: dict) -> str:
    content = '<p>Call ' + _esc(call.get('sequence', '?')) + ' · ' + _esc(call.get('provider', 'unknown provider')) + ' · status: ' + _esc(call.get('status', 'unknown')) + '</p>'
    content += '<h5>Exact request</h5>' + (_pre(call['request_text']) if isinstance(call.get('request_text'), str) else '<p>No request text was recorded.</p>')
    if call.get('error'):
        content += '<h5>Recorded error</h5>' + _json(call['error'])
    content += '<h5>Complete call record</h5>' + _json(call)
    return content


def _examples(result: dict) -> str:
    task = result['task']
    outputs = result.get('candidate_outputs', [])
    calls = [call for call in result.get('calls', []) if call.get('phase') == 'candidate']
    compare = result.get('execution_mode', 'tournament') in ('battle', 'tournament')
    content = '<section id="examples"><h2>Examples and responses</h2><p>Each source below is paired with its captured candidate responses. Exact-field checks, when present, are deterministic checks; pairwise judgments appear in the comparisons section.</p>'
    prior_artifacts = set()
    for index, artifact in enumerate(task['artifacts'], 1):
        artifact_id = artifact['id']
        content += '<section class="example" id="example-' + str(index) + '"><h3>Example ' + str(index) + ': ' + _esc(artifact_id) + '</h3><div class="source"><h4>Original source</h4>' + _pre(artifact['text']) + '</div>'
        if artifact.get('expected') is not None:
            content += _details('Configured expected fields', _json(artifact['expected']))
        content += '<div class="grid">'
        for model in task['models']:
            candidate_id = model['id']
            captured = [output for output in outputs if output['candidate_id'] == candidate_id and output['artifact_id'] == artifact_id]
            attempts = [call for call in calls if call['candidate_id'] == candidate_id and call.get('artifact_id') == artifact_id]
            content += '<article class="response"><h4>' + _esc(candidate_id) + '</h4>'
            content += '<p class="metadata">Provider: ' + _esc(model['provider'])
            if model.get('model'):
                content += ' · Requested model: ' + _esc(model['model'])
            content += '</p>'
            if captured:
                for output in captured:
                    content += '<p><strong>Output captured</strong></p>' + _pre(output['text']) + _checks(output.get('assessment'))
            elif attempts:
                content += '<p><strong>No successful candidate output was recorded.</strong></p>'
            else:
                stopped_earlier = compare and (
                    any(call['candidate_id'] == candidate_id and call.get('artifact_id') in prior_artifacts and call.get('status') == 'failed' for call in calls)
                    or any(output['candidate_id'] == candidate_id and output['artifact_id'] in prior_artifacts and output.get('assessment') is not None and not output['assessment']['valid_json_object'] for output in outputs)
                )
                content += '<p><strong>' + ('Skipped after an earlier evaluation failure.' if stopped_earlier else 'Missing record.') + '</strong> No call or output was recorded for this candidate and example.</p>'
            for call in attempts:
                content += '<p>Call status: <strong>' + _esc(call.get('status', 'unknown')) + '</strong></p>'
                if call.get('status') == 'failed':
                    if isinstance(call.get('text'), str):
                        content += '<h5>Retained failed response</h5>' + (_pre(call['text']) if call['text'] else '<p>The recorded response text was empty.</p>')
                    else:
                        content += '<p>No response text was captured for this failed call.</p>'
                    if call.get('error'):
                        content += '<p>' + _esc(call['error'].get('message', 'Call failed.')) + '</p>'
                elif not captured and isinstance(call.get('text'), str):
                    content += '<h5>Retained call response</h5>' + _pre(call['text'])
                content += _details('Inspect request and call evidence', _call_evidence(call))
            content += '</article>'
        content += '</div></section>'
        prior_artifacts.add(artifact_id)
    return content + '</section>'


def _matches_judge_call(call: dict, decision: dict) -> bool:
    """Match this workflow's saved pair and parsed ruling, never list offsets."""
    if call.get('status') != 'completed':
        return False
    try:
        # build_judge_request writes an instruction paragraph, then JSON evidence.
        evidence = json.loads(call['request_text'].partition('\n\n')[2])
        ruling = json.loads(call['text'])
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        return False
    return (isinstance(evidence, dict) and isinstance(ruling, dict)
            and evidence.get('model_a') == decision['model_a']
            and evidence.get('model_b') == decision['model_b']
            and isinstance(ruling.get('winner'), str)
            and ruling['winner'].strip() == decision['winner']
            and isinstance(ruling.get('short_reason'), str)
            and ruling['short_reason'].strip() == decision['reason']
            and ruling.get('confidence') == decision.get('confidence'))


def _comparisons(result: dict) -> str:
    decisions = result.get('decisions', [])
    calls = [call for call in result.get('calls', []) if call.get('phase') == 'judge']
    provider_judge = result['task'].get('judge', {}).get('kind') == 'provider'
    content = '<section id="comparisons"><h2>Recorded comparisons</h2>'
    if decisions:
        content += '<p>Each decision compares the two candidates across the whole example bundle. It is not a separate judgment of each example, and confidence is not a rubric score.</p>'
    else:
        content += '<p>No comparison decision was recorded.</p>'
    used = set()
    for index, decision in enumerate(decisions, 1):
        a, b, winner = decision['model_a'], decision['model_b'], decision['winner']
        outcome = {
            'model_a_better': 'Winner: ' + a,
            'model_b_better': 'Winner: ' + b,
            'model_a_disqualified': 'Disqualified: ' + a + '. Remaining candidate: ' + b + '.',
            'model_b_disqualified': 'Disqualified: ' + b + '. Remaining candidate: ' + a + '.',
            'both_disqualified': 'Both candidates disqualified; no winner.',
        }.get(winner, 'Recorded outcome: ' + winner)
        content += '<article id="comparison-' + str(index) + '"><h3>Comparison ' + str(index) + ': ' + _esc(a) + ' vs ' + _esc(b) + '</h3><p><strong>' + _esc(outcome) + '</strong></p><p>Decision code: <code>' + _esc(winner) + '</code></p><h4>Reason</h4>' + _pre(decision['reason'])
        confidence = decision.get('confidence')
        content += '<p>Recorded confidence: ' + ('not supplied' if confidence is None else _esc(confidence)) + '</p>'
        if provider_judge:
            matches = [i for i, call in enumerate(calls) if i not in used and _matches_judge_call(call, decision)]
            if len(matches) == 1:
                matched = matches[0]
                used.add(matched)
                call = calls[matched]
                content += _details('Inspect matching provider-judge request and response', _call_evidence(call) + '<h5>Exact judge response</h5>' + _pre(call['text']))
            else:
                content += '<p>A unique matching provider-judge call could not be established from the saved records. No request has been assigned to this decision.</p>'
        else:
            content += '<p>Deterministic rules decision; no provider-judge request was made.</p>'
        content += '</article>'
    unmatched = [call for index, call in enumerate(calls) if index not in used]
    if unmatched:
        content += '<h3>Judge calls without a matched decision</h3><p>A captured response can fail decision parsing even when its provider call completed. These records are not additional judgments.</p>'
        for call in unmatched:
            evidence = _call_evidence(call)
            if isinstance(call.get('text'), str):
                evidence += '<h5>Exact judge response</h5>' + _pre(call['text'])
            content += _details('Inspect unmatched judge call ' + str(call.get('sequence', '?')), evidence)
    return content + '</section>'


_STYLE = '''
:root{color-scheme:light dark}*{box-sizing:border-box}body{font:16px/1.6 system-ui,sans-serif;margin:0;background:light-dark(#f5f3ec,#151d19);color:light-dark(#21352f,#e8ecdf);overflow-wrap:anywhere}main{max-width:1100px;padding:42px 24px;margin:auto}h1{font:clamp(2.6rem,7vw,4rem)/1.1 Georgia,serif;margin:15px 0}h2{font-size:1.5rem;margin-top:36px}h3{font-size:1.2rem}h4,h5{font-size:1rem;margin:12px 0 6px}a{color:inherit}p{max-width:85ch}.label,.metadata{font-size:.8rem}.label{text-transform:uppercase;letter-spacing:.1em}nav{display:flex;flex-wrap:wrap;gap:12px 22px;margin:24px 0}article,details,.example{border:1px solid #82908088;border-radius:8px;padding:18px;margin:15px 0}summary{cursor:pointer;font-weight:600}.example{padding:22px;margin:28px 0}.source{border-left:4px solid #829080;padding-left:15px}pre{white-space:pre-wrap;overflow-wrap:anywhere;tab-size:4;padding:14px;background:#82908015;font:13px/1.65 ui-monospace,monospace;margin:12px 0}table{border-collapse:collapse;width:100%;table-layout:fixed}caption{text-align:left;font-weight:700;padding:12px 0}th,td{text-align:left;border-bottom:1px solid #82908088;padding:10px;overflow-wrap:anywhere}.rankings th:first-child,.rankings td:first-child{width:90px}li{margin:8px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.response{min-width:0;margin:12px 0}.response details{padding:12px}a:focus-visible,summary:focus-visible{outline:3px solid #bc6f3c;outline-offset:4px}section{scroll-margin-top:20px}@media(max-width:700px){main{padding:25px 16px}.grid{grid-template-columns:1fr}.example{padding:14px}article,details{padding:14px}}@media print{body{background:white;color:black}main{max-width:none;padding:0}.grid{display:block}a{color:black}}
'''


def render_report(result: dict) -> str:
    """Render the existing result schema; all recorded text remains inert HTML."""
    task = result['task']
    mode = result.get('execution_mode', 'tournament')
    rubric = task.get('rubric', {})
    content = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Rubric Rumble — ' + _esc(task['id']) + '</title><style>' + _STYLE + '</style></head><body><main><header><div class="label">CinvanaAI / Task evaluation</div><h1>Rubric Rumble</h1><p>Task: <strong>' + _esc(task['id']) + '</strong></p><p>' + _esc(mode) + ' · ' + _esc(result['status']) + ' · ' + _esc(result['mode']) + ' · ' + _esc(result['provider_calls_attempted']) + ' provider calls attempted</p><p><a href="result.json">Open the complete JSON evidence</a></p></header><nav aria-label="Report sections"><a href="#outcome">Outcome</a><a href="#task">Task and rubric</a><a href="#examples">Examples and responses</a><a href="#comparisons">Comparisons</a><a href="#usage">Usage and cost</a></nav>'
    content += _outcome(result)
    content += '<section id="task"><h2>Task and rubric</h2><h3>Exact task instructions</h3>' + _pre(task['instructions']) + '<h3>Configured rubric</h3>' + _pre(rubric.get('description', 'No rubric description recorded.'))
    if mode in ('single', 'batch'):
        content += '<p>This capture mode did not apply the rubric or invoke the judge.</p>'
    content += _details('Inspect complete rubric and judge settings', _json({'rubric': rubric, 'judge': task.get('judge')})) + '</section>'
    content += _examples(result) + _comparisons(result)
    cost = result['cost_summary']
    costs = ''.join('<li>' + _esc(item['phase']) + ': ' + _esc(item['currency']) + ' ' + _esc(f'{item["amount"]:.8f}') + ' estimated</li>' for item in cost['estimated_subtotals']) or '<li>No monetary estimate is available for this run.</li>'
    content += '<section id="usage"><h2>Usage and estimated cost</h2><ul>' + costs + '</ul><p>' + _esc(cost['calls_without_cost_estimate']) + ' attempted provider calls lack a cost estimate. ' + _esc(cost['note']) + '</p><p>Usage is retained in individual call records. Estimated cost does not choose the winner.</p></section>'
    errors = ''.join('<li>' + _esc(call['candidate_id']) + ' / ' + _esc(call['phase']) + ': ' + _esc(call.get('error', {}).get('message', 'Call failed.')) + '</li>' for call in result.get('calls', []) if call.get('status') == 'failed')
    if result.get('error'):
        errors += '<li>' + _esc(result['error'].get('message', 'Run failed.')) + '</li>'
    if errors:
        content += '<section><h2>Run errors</h2><ul>' + errors + '</ul></section>'
    content += _details('Inspect complete run evidence and settings', _json(result)) + '<p class="label">Task fingerprint: ' + _esc(result['task_sha256']) + '</p><p>Each run is fresh. Any ranking depends on this task, rubric and the recorded pairwise comparisons.</p>'
    if result.get('mode') == 'synthetic-fixtures':
        content += '<p>Synthetic fixture results demonstrate the workflow; they are not measurements of real models.</p>'
    return content + '</main></body></html>'


def save_report(result: dict, directory: Path, *, renderer=render_report) -> None:
    (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (directory / 'report.html').write_text(renderer(result), encoding='utf-8')
