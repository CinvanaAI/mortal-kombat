"""Local, escaped HTML evidence report with no remote dependencies."""
from __future__ import annotations
from html import escape
import json
from pathlib import Path


def render_report(result: dict) -> str:
    esc=lambda value:escape(str(value))
    tournament=result.get('tournament') or {}
    ranks=tournament.get('current_ranking',[])
    table=''.join(f'<tr><td data-label="Rank">{esc(r["rank"])}</td><th scope="row" data-label="Candidate">{esc(r["model_id"])}</th><td data-label="Status">{esc(r["status"])}</td><td data-label="Reason">{esc(r.get("reason",""))}</td></tr>' for r in ranks)
    ranking = '<h2>Final ranking</h2><table class="rankings"><thead><tr><th>Rank</th><th>Candidate</th><th>Status</th><th>Reason</th></tr></thead><tbody>'+table+'</tbody></table>' if result.get('tournament') is not None else '<h2>Run outcome</h2><p>Outputs were captured without a ranking.</p>'
    candidates=[]
    for output in result['candidate_outputs']:
        assessment=output['assessment']
        checks=''
        if assessment is not None:
            checks='<p><strong>'+esc(assessment['score'])+' / '+esc(assessment['maximum'])+' exact fields</strong> · '+esc(assessment['reason'])+'</p>'
            checks+='<ul>'+''.join('<li>'+('✓' if check['passed'] else '×')+' '+esc(check['field'])+': expected '+esc(check['expected'])+'; received '+esc(check['actual'])+'</li>' for check in assessment['checks'])+'</ul>'
        candidates.append('<article><div class="label">'+esc(output['artifact_id'])+'</div><h3>'+esc(output['candidate_id'])+'</h3><pre>'+esc(output['text'])+'</pre>'+checks+'</article>')
    decisions=''.join('<li><strong>'+esc(d['model_a'])+' vs '+esc(d['model_b'])+'</strong><p>'+esc(d['reason'])+'</p><code>'+esc(d['winner'])+'</code></li>' for d in result['decisions'])
    costs=''.join('<li>'+esc(x['phase'])+': '+esc(x['currency'])+' '+f'{x["amount"]:.8f}'+' estimated</li>' for x in result['cost_summary']['estimated_subtotals']) or '<li>No monetary estimate is available for this run.</li>'
    errors=''.join('<li>'+esc(c['candidate_id'])+' / '+esc(c['phase'])+': '+esc(c['error']['message'])+'</li>' for c in result['calls'] if c['status']=='failed')
    if result.get('error'): errors+='<li>'+esc(result['error']['message'])+'</li>'
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mortal Kombat — '+esc(result['task']['id'])+'</title><style>'+'''
    :root{color-scheme:light dark}*{box-sizing:border-box}body{font:16px/1.6 system-ui,sans-serif;margin:0;background:light-dark(#f5f3ec,#151d19);color:light-dark(#21352f,#e8ecdf)}main{max-width:1050px;padding:45px 25px;margin:auto}h1{font:60px/1 Georgia,serif;margin:15px 0}h2{font-size:23px;margin-top:35px}h3{margin:8px 0}a{color:inherit}p{max-width:80ch}.label{font:11px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.13em}article,details{border:1px solid #82908066;border-radius:8px;padding:20px;margin:15px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:15px;background:#82908015;font:13px/1.6 ui-monospace,monospace}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #82908066;padding:10px;overflow-wrap:anywhere}li{margin-bottom:12px}summary{cursor:pointer}a:focus-visible,summary:focus-visible{outline:3px solid #ac5b39;outline-offset:4px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:650px){h1{font-size:43px}.grid{grid-template-columns:1fr}main{padding:25px 18px}}body{overflow-wrap:anywhere}
    .rankings{table-layout:fixed}.rankings th:nth-child(1){width:70px}.rankings th:nth-child(2){width:28%}.rankings th:nth-child(3){width:140px}.rankings td:first-child{white-space:nowrap}
    @media(max-width:650px){.rankings,.rankings tbody,.rankings tr,.rankings td,.rankings th{display:block;width:100%!important}.rankings thead{position:absolute;width:1px;height:1px;clip-path:inset(50%);overflow:hidden;white-space:nowrap}.rankings tr{border:1px solid #82908066;border-radius:8px;padding:12px;margin:14px 0}.rankings td,.rankings th{border:0;padding:5px 0}.rankings [data-label]::before{content:attr(data-label);display:block;font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;opacity:.75}.rankings [data-label="Candidate"]{font-size:18px}}
    '''+'</style><main><div class="label">CinvanaAI / Task evaluation</div><h1>Mortal Kombat</h1><p>'+esc(result['task']['instructions'])+'</p><p><strong>'+esc(result['mode'])+'</strong> · '+esc(result['status'])+' · '+esc(result['provider_calls_attempted'])+' provider calls attempted · '+esc(result.get('execution_mode','tournament'))+'</p><p><a href="result.json">Open the complete JSON evidence</a></p>'+ranking+'<p>'+esc(result['task']['rubric']['description'])+'</p><h2>Captured outputs</h2><div class="grid">'+''.join(candidates)+'</div>'+('<h2>Recorded comparisons</h2><ol>'+decisions+'</ol>' if decisions else '')+'<h2>Usage and estimated cost</h2><ul>'+costs+'</ul><p>'+esc(result['cost_summary']['calls_without_cost_estimate'])+' attempted provider calls lack a cost estimate. '+esc(result['cost_summary']['note'])+'</p>'+('<h2>Run errors</h2><ul>'+errors+'</ul>' if errors else '')+'<details><summary>Inspect call evidence and settings</summary><pre>'+esc(json.dumps(result,indent=2,ensure_ascii=False))+'</pre></details><p class="label">Task fingerprint: '+esc(result['task_sha256'])+'</p><p>Each run is fresh. Rankings depend on the task, rubric and pairwise comparisons. Synthetic fixture results demonstrate the workflow; they are not measurements of real models.</p></main></html>'


def save_report(result: dict, directory: Path, *, renderer=render_report) -> None:
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (directory/'report.html').write_text(renderer(result),encoding='utf-8')
