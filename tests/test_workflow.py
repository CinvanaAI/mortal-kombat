from __future__ import annotations
import copy
import json
import pytest
from prompt_tournament.providers import ProviderFailure,_NoRedirect,estimate_cost,normalize_response
from prompt_tournament.report import render_report
from prompt_tournament.task import fingerprint,validate_task
from prompt_tournament.workflow import assess_output,run_task
from prompt_tournament.workflow_cli import demo_task,main


def live_task(*,judge=False):
    task=demo_task()
    task['providers']={'test':{'kind':'openai','base_url':'https://synthetic.invalid/v1','api_key_env':'MK_TEST_KEY'}}
    task['models']=[{'id':'complete','provider':'test','model':'complete','rates':rates()},{'id':'partial','provider':'test','model':'partial','rates':rates()}]
    if judge:
        task['judge']={'kind':'provider','model':{'id':'judge','provider':'test','model':'judge','rates':rates()}}
    return task


def rates():
    return {'input_per_million':1.0,'output_per_million':2.0,'currency':'USD','source':'Synthetic test rates; not current provider prices','as_of':'2026-09-19'}


def fake_transport(seen):
    def send(url,headers,payload,timeout):
        assert url=='https://synthetic.invalid/v1/responses'
        assert payload['store'] is False and payload['max_output_tokens']==1024
        seen.append(payload)
        if payload['model']=='judge':
            assert 'model_a_output' in payload['input'] and 'model_b_output' in payload['input']
            text=json.dumps({'winner':'model_b_better','short_reason':'Synthetic judge prefers retained owner.','confidence':0.8})
        else:
            owner='Morgan' if 'Morgan' in payload['input'] else 'Riley'
            action='review the fixture' if owner=='Morgan' else 'check the release notes'
            answer={'owner':owner,'action':action} if payload['model']=='complete' else {'action':action}
            text=json.dumps(answer)
        return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}],'usage':{'input_tokens':100,'output_tokens':20,'input_tokens_details':{'cached_tokens':0}},'model':payload['model']}
    return send


def test_demo_is_complete_meaningful_and_network_free():
    def forbid(*args): raise AssertionError('Demo attempted a provider call')
    result=run_task(demo_task(),transport=forbid)
    assert result['status']=='completed' and result['provider_calls_attempted']==0
    assert [(x['model_id'],x['status']) for x in result['tournament']['current_ranking']]==[('complete-fixture','Ranked'),('missing-owner-fixture','Ranked'),('malformed-fixture','Disqualified')]
    assert {x['candidate_id']:x['assessment']['score'] for x in result['candidate_summaries']}=={'complete-fixture':4,'missing-owner-fixture':2,'malformed-fixture':0}
    assert result['cost_summary']['estimated_subtotals']==[]
    assert all(call['cost']['amount'] is None for call in result['calls'])


def test_cli_saves_actual_json_and_html_and_refuses_overwrite(tmp_path):
    out=tmp_path/'result'
    assert main(['demo','--out',str(out)])==0
    original=(out/'result.json').read_bytes()
    assert json.loads(original)['task_sha256'] in (out/'report.html').read_text()
    assert main(['demo','--out',str(out)])==2
    assert (out/'result.json').read_bytes()==original


def test_saved_example_contains_all_required_fixture_data(tmp_path):
    path=tmp_path/'task.json'
    assert main(['example',str(path)])==0
    task=validate_task(json.loads(path.read_text()))
    assert len(task['artifacts'])==2 and len(task['models'])==3
    assert main(['example',str(path)])==2


def test_run_defaults_to_plan_without_credentials_or_output(tmp_path,monkeypatch):
    monkeypatch.delenv('MK_TEST_KEY',raising=False)
    path=tmp_path/'task.json';path.write_text(json.dumps(live_task()))
    out=tmp_path/'never-created'
    assert main(['run',str(path),'--out',str(out)])==0
    assert not out.exists()


def test_live_routes_require_explicit_execution():
    with pytest.raises(ValueError,match='explicit execution'):
        run_task(live_task())


def test_missing_any_key_fails_before_first_call(monkeypatch):
    monkeypatch.delenv('MK_TEST_KEY',raising=False)
    seen=[]
    with pytest.raises(ValueError,match='MK_TEST_KEY'):
        run_task(live_task(),allow_network=True,transport=fake_transport(seen))
    assert seen==[]


def test_provider_rules_path_retains_usage_and_actual_cost_math(monkeypatch):
    monkeypatch.setenv('MK_TEST_KEY','PRIVATE_TEST_SENTINEL')
    seen=[];result=run_task(live_task(),allow_network=True,transport=fake_transport(seen))
    assert len(seen)==4 and result['provider_calls_attempted']==4
    assert result['tournament']['current_ranking'][0]['model_id']=='complete'
    assert result['cost_summary']['estimated_subtotals'][0]['amount']==pytest.approx(.00056)
    assert all(call['usage']['input_tokens']==100 for call in result['calls'])
    assert 'PRIVATE_TEST_SENTINEL' not in json.dumps(result)


def test_provider_judge_separates_judge_usage_from_candidates(monkeypatch):
    monkeypatch.setenv('MK_TEST_KEY','synthetic-unused')
    seen=[];result=run_task(live_task(judge=True),allow_network=True,transport=fake_transport(seen))
    assert result['status']=='completed' and len(seen)==5
    assert {x['phase'] for x in result['cost_summary']['estimated_subtotals']}=={'candidate','judge'}
    assert result['decisions'][0]['reason']=='Synthetic judge prefers retained owner.'


def test_failed_judge_retains_attempted_calls_and_no_invented_ranking(monkeypatch):
    monkeypatch.setenv('MK_TEST_KEY','synthetic-unused')
    seen=[];base=fake_transport(seen)
    def transport(url,headers,payload,timeout):
        body=base(url,headers,payload,timeout)
        if payload['model']=='judge': body['output']=[{'content':[{'type':'output_text','text':'not decision JSON'}]}]
        return body
    result=run_task(live_task(judge=True),allow_network=True,transport=transport)
    assert result['status']=='failed' and result['tournament'] is None
    assert len(result['calls'])==5 and result['calls'][-1]['text']=='not decision JSON'


def test_incomplete_provider_response_retains_usage_but_disqualifies(monkeypatch):
    monkeypatch.setenv('MK_TEST_KEY','synthetic-unused')
    def transport(*args):return {'status':'incomplete','output_text':'partial','usage':{'input_tokens':50,'output_tokens':10}}
    result=run_task(live_task(),allow_network=True,transport=transport)
    assert result['status']=='no-ranked-candidates'
    assert all(call['status']=='failed' and call['usage']['input_tokens']==50 for call in result['calls'])


def test_arbitrary_transport_errors_do_not_leak_headers(monkeypatch):
    monkeypatch.setenv('MK_TEST_KEY','DO_NOT_LEAK_SECRET')
    def fail(url,headers,*args):raise RuntimeError(str(headers))
    result=run_task(live_task(),allow_network=True,transport=fail)
    assert result['status']=='no-ranked-candidates'
    assert 'DO_NOT_LEAK_SECRET' not in json.dumps(result)


def test_call_limit_counts_only_attempted_provider_calls(monkeypatch):
    monkeypatch.setenv('MK_TEST_KEY','synthetic-unused')
    task=live_task();task['max_calls']=1
    seen=[];result=run_task(task,allow_network=True,transport=fake_transport(seen))
    assert len(seen)==1 and result['provider_calls_attempted']==1
    assert sum(call['provider_call_attempted'] for call in result['calls'])==1
    assert result['cost_summary']['calls_without_cost_estimate']==0


def test_malformed_candidate_is_disqualified_even_when_it_would_be_only_survivor():
    task=demo_task();task['models']=task['models'][-2:]
    task['models'][0]['fixture_outputs']={a['id']:'[]' for a in task['artifacts']}
    result=run_task(task)
    assert result['status']=='no-ranked-candidates'
    assert all(x['status']=='Disqualified' for x in result['tournament']['current_ranking'])


def test_equal_scores_have_explicit_tie_break():
    task=demo_task();task['models']=task['models'][:2]
    task['models'][1]['fixture_outputs']=copy.deepcopy(task['models'][0]['fixture_outputs'])
    result=run_task(task)
    assert 'tie-break' in result['decisions'][0]['reason']


@pytest.mark.parametrize('change',[lambda t:t.update(api_key='secret'),lambda t:t['artifacts'].append(copy.deepcopy(t['artifacts'][0])),lambda t:t['rubric'].update(fields=['owner','owner']),lambda t:t['artifacts'][0].pop('expected')])
def test_invalid_tasks_fail_before_execution(change):
    task=demo_task();change(task)
    with pytest.raises(ValueError): validate_task(task)


def test_secret_urls_and_remote_http_are_rejected():
    for url in ('https://user:password@example.com/v1','https://example.com/v1?key=secret','http://example.com/v1'):
        task=live_task();task['providers']['test']['base_url']=url
        with pytest.raises(ValueError):validate_task(task)


def test_redirect_is_refused():
    with pytest.raises(ProviderFailure,match='redirect refused'):
        _NoRedirect().redirect_request(None,None,302,'found',{},'https://elsewhere.invalid')


def test_ollama_usage_is_retained():
    result=normalize_response('ollama',{'message':{'content':'answer'},'done':True,'prompt_eval_count':60,'eval_count':15,'prompt_eval_cached_count':20})
    assert result['usage']=={'input_tokens':60,'output_tokens':15,'cached_input_tokens':20,'cache_write_tokens':None}


def test_unknown_cost_never_becomes_zero():
    assert estimate_cost(None,rates())['amount'] is None
    assert estimate_cost({'input_tokens':2,'output_tokens':None},rates())['amount'] is None
    assert estimate_cost({'input_tokens':2,'output_tokens':2},None)['amount'] is None


def test_cached_and_special_usage_require_matching_rates():
    usage={'input_tokens':100,'output_tokens':20,'cached_input_tokens':40,'cache_write_tokens':0}
    assert estimate_cost(usage,rates())['amount'] is None
    adjusted={**rates(),'cached_input_per_million':.5}
    assert estimate_cost(usage,adjusted)['amount']==pytest.approx(.00012)
    assert estimate_cost({**usage,'cache_write_tokens':10},adjusted)['amount'] is None


def test_configuration_change_changes_fingerprint():
    a=validate_task(demo_task());b=copy.deepcopy(a);b['instructions']+=' Different task.'
    assert fingerprint(a)!=fingerprint(b)


def test_html_escapes_candidate_and_task_text():
    task=demo_task();task['instructions']='<script>do_not_execute()</script>'
    task['models'][0]['fixture_outputs']['review']='<img src=x onerror=do_not_execute()>'
    html=render_report(run_task(task))
    assert '<script>do_not_execute()' not in html
    assert '<img src=x' not in html
    assert '&lt;script&gt;' in html and '&lt;img src=x' in html


def test_extra_fields_do_not_hide_missing_required_fields():
    result=assess_output('{"owner":"Morgan","unrelated":"x"}',{'owner':'Morgan','action':'review'})
    assert result['score']==1 and result['maximum']==2


def test_saved_report_does_not_execute(tmp_path,monkeypatch):
    result=run_task(demo_task())
    source=tmp_path/'evidence.json';source.write_text(json.dumps(result))
    def forbid(*args,**kwargs): raise AssertionError('Saved report ran a task')
    monkeypatch.setattr('prompt_tournament.workflow_cli.run_task',forbid)
    out=tmp_path/'rendered'
    assert main(['report',str(source),'--out',str(out)])==0
    assert json.loads((out/'result.json').read_text())==result
    assert 'complete-fixture' in (out/'report.html').read_text()
    assert main(['report',str(source),'--out',str(out)])==2


@pytest.mark.parametrize('field,value', [
    ('short_reason', None), ('short_reason', 42), ('short_reason', {}),
    ('short_reason', ''), ('short_reason', '  '),
    ('confidence', 'NaN'), ('confidence', '0.8'), ('confidence', True),
    ('confidence', float('nan')), ('confidence', float('inf')),
    ('confidence', -0.1), ('confidence', 1.1),
])
def test_provider_judge_rejects_malformed_fields_without_ranking(monkeypatch, field, value):
    monkeypatch.setenv('MK_TEST_KEY', 'synthetic-unused')
    seen=[];base=fake_transport(seen)
    decision={'winner':'model_a_better','short_reason':'Synthetic valid reason.','confidence':0.8}
    decision[field]=value
    raw=json.dumps(decision)
    def transport(url,headers,payload,timeout):
        body=base(url,headers,payload,timeout)
        if payload['model']=='judge':
            body['output']=[{'content':[{'type':'output_text','text':raw}]}]
        return body
    result=run_task(live_task(judge=True),allow_network=True,transport=transport)
    assert result['status']=='failed' and result['tournament'] is None
    assert result['decisions']==[] and result['calls'][-1]['text']==raw
    assert len(seen)==5
