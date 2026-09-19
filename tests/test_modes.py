import copy
import json
import pytest
from prompt_tournament.workflow_cli import demo_task, main
from prompt_tournament.task import validate_task, plan_task
from prompt_tournament.workflow import run_task


def test_batch_never_judges_and_retains_every_requested_output(monkeypatch):
    task=demo_task()
    task['providers']={'unused':{'kind':'openai','base_url':'https://example.invalid/v1','api_key_env':'MK_UNUSED_JUDGE'}}
    task['judge']={'kind':'provider','model':{'id':'judge','provider':'unused','model':'unused'}}
    monkeypatch.delenv('MK_UNUSED_JUDGE',raising=False)
    def forbid(*a,**kw): raise AssertionError('Batch called a judge')
    result=run_task(task,mode='batch',transport=forbid)
    assert len(result['calls'])==6
    assert result['tournament'] is None and result['decisions']==[]
    assert result['status']=='completed' and result['provider_calls_attempted']==0
    assert plan_task(task,mode='batch')['maximum_judge_calls']==0
    assert not plan_task(task,mode='batch')['network_required']


def test_single_runs_one_candidate_on_all_examples():
    task=demo_task();task['models']=task['models'][:1]
    result=run_task(task,mode='single')
    assert result['status']=='completed' and len(result['candidate_outputs'])==2
    assert result['decisions']==[] and result['tournament'] is None


def test_battle_runs_one_pair_on_complete_example_bundle():
    task=demo_task();task['models']=task['models'][:2]
    result=run_task(task,mode='battle')
    assert len(result['calls'])==4 and len(result['decisions'])==1
    assert result['tournament']['current_ranking'][0]['model_id']=='complete-fixture'


@pytest.mark.parametrize('mode,count',[('single',2),('battle',1),('battle',3),('tournament',1),('batch',0)])
def test_invalid_selection_is_rejected(mode,count):
    task=demo_task();task['models']=task['models'][:count]
    with pytest.raises(ValueError):validate_task(task,mode=mode)


def test_batch_records_failure_and_continues_other_examples(monkeypatch):
    task=demo_task();task['models']=task['models'][:1]
    task['models'][0]={'id':'live','provider':'test','model':'test'}
    task['providers']={'test':{'kind':'ollama','base_url':'http://127.0.0.1:11434'}}
    calls=[]
    def transport(url,headers,payload,timeout):
        calls.append(payload)
        if len(calls)==1:raise RuntimeError('private provider diagnostic')
        return {'done':True,'message':{'content':'{"owner":"Riley","action":"check the release notes"}'}}
    result=run_task(task,mode='batch',allow_network=True,transport=transport)
    assert len(calls)==2 and result['status']=='partial'
    assert len(result['candidate_outputs'])==1 and result['tournament'] is None
    assert 'private provider diagnostic' not in str(result)


def test_batch_live_call_limit_is_enforced():
    task=demo_task();task['models']=[{'id':'live','provider':'test','model':'test'}]
    task['providers']={'test':{'kind':'ollama','base_url':'http://127.0.0.1:11434'}}
    task['max_calls']=1
    calls=[]
    def transport(*args):
        calls.append(args)
        return {'done':True,'message':{'content':'{"owner":"Morgan","action":"review the fixture"}'}}
    result=run_task(task,mode='single',allow_network=True,transport=transport)
    assert len(calls)==1 and result['provider_calls_attempted']==1
    assert result['calls'][1]['status']=='failed' and result['status']=='partial'


def test_endpoint_kind_validation():
    task=demo_task();task['providers']={'test':{'kind':'ollama','base_url':'http://localhost:11434','endpoint':'responses'}}
    with pytest.raises(ValueError,match='endpoint'):validate_task(task)


@pytest.mark.parametrize('judge',[None,{'kind':'provider'},{'kind':'rules'},{'kind':'none'}])
def test_capture_modes_need_no_unused_judge_or_expected_answers(judge):
    task=demo_task();task['models']=task['models'][:1]
    for artifact in task['artifacts']:artifact.pop('expected')
    task.pop('rubric');task.pop('judge')
    if judge is not None:task['judge']=judge
    result=run_task(task,mode='single')
    assert result['status']=='completed' and len(result['candidate_outputs'])==2
    assert all(o['assessment'] is None for o in result['candidate_outputs'])
    assert result['decisions']==[]


def test_probe_cli_defaults_to_plan_and_preserves_existing_results(tmp_path,monkeypatch):
    task=demo_task();task['models']=[{'id':'test','provider':'test','model':'text-model'}]
    task['providers']={'test':{'kind':'ollama','base_url':'http://127.0.0.1:11434'}}
    source=tmp_path/'task.json';source.write_text(json.dumps(task))
    calls=[]
    def probe(provider,model):
        calls.append((provider,model));return {'status':'text-response','text':'hi','usage':None}
    monkeypatch.setattr('prompt_tournament.providers.probe_model',probe)
    out=tmp_path/'observations'
    argv=['probe',str(source),'--candidate','test','--out',str(out)]
    assert main(argv)==0 and calls==[] and not out.exists()
    assert main(argv+['--execute'])==0 and len(calls)==1
    evidence=(out/'probes.json').read_bytes()
    records=json.loads(evidence)['records']
    assert records[0]['model']=='text-model' and records[0]['text']=='hi'
    assert records[0]['endpoint']=='chat' and records[0]['observed_at']
    assert main(argv+['--execute'])==2 and len(calls)==1
    assert (out/'probes.json').read_bytes()==evidence


def test_probe_cli_checks_all_keys_before_any_request(tmp_path,monkeypatch):
    task=demo_task();task['models']=[{'id':'one','provider':'local','model':'one'},{'id':'two','provider':'remote','model':'two'}]
    task['providers']={'local':{'kind':'ollama','base_url':'http://localhost:11434'},'remote':{'kind':'openai','base_url':'https://example.invalid/v1','api_key_env':'MK_ABSENT_KEY'}}
    source=tmp_path/'task.json';source.write_text(json.dumps(task))
    monkeypatch.delenv('MK_ABSENT_KEY',raising=False)
    def forbid(*a):raise AssertionError('Probe ran before complete preflight')
    monkeypatch.setattr('prompt_tournament.providers.probe_model',forbid)
    out=tmp_path/'never-created'
    assert main(['probe',str(source),'--candidate','one','--candidate','two','--execute','--out',str(out)])==2
    assert not out.exists()
