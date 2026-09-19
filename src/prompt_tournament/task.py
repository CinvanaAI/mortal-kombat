"""Validate a portable task before writing results or making any provider call."""
from __future__ import annotations
import copy
import datetime
import hashlib
import json
import math
import re
from urllib.parse import urlsplit


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be nonempty text.')
    return value


def _keys(value, allowed, name):
    if not isinstance(value, dict):
        raise ValueError(f'{name} must be an object.')
    unknown = set(value)-set(allowed)
    if unknown:
        raise ValueError(f'{name} contains unsupported fields: {", ".join(sorted(unknown))}.')


def validate_task(raw: dict, *, mode: str = 'tournament') -> dict:
    if mode not in ('single', 'batch', 'battle', 'tournament'):
        raise ValueError('Execution mode must be single, batch, battle or tournament.')
    compare = mode in ('battle','tournament')
    task = copy.deepcopy(raw)
    _keys(task, ('schema','id','instructions','artifacts','models','providers','rubric','judge','max_calls'), 'task')
    if task.get('schema') != 'mortal-kombat.task.v1':
        raise ValueError('schema must be mortal-kombat.task.v1.')
    for field in ('id','instructions'):
        _text(task.get(field),field)
    artifacts=task.get('artifacts')
    if not isinstance(artifacts,list) or not artifacts:
        raise ValueError('Supply at least one artifact.')
    artifact_ids=[]
    for artifact in artifacts:
        _keys(artifact,('id','text','expected'),'artifact')
        artifact_ids.append(_text(artifact.get('id'),'artifact.id'))
        _text(artifact.get('text'),'artifact.text')
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError('Artifact IDs must be unique.')
    providers=task.setdefault('providers',{})
    if not isinstance(providers,dict):
        raise ValueError('providers must be an object.')
    for name,provider in providers.items():
        _text(name,'provider name')
        _keys(provider,('kind','base_url','api_key_env','timeout_seconds','endpoint'),'provider')
        if provider.get('kind') not in ('openai','ollama'):
            raise ValueError('Provider kind must be openai or ollama.')
        endpoints = ('responses', 'chat-completions') if provider['kind']=='openai' else ('chat',)
        if provider.get('endpoint', endpoints[0]) not in endpoints:
            raise ValueError('Provider endpoint is not supported for its kind.')
        url=urlsplit(_text(provider.get('base_url'),'provider.base_url'))
        if url.username or url.password or url.query or url.fragment or not url.hostname:
            raise ValueError('Provider URL must have a host and no credentials, query or fragment.')
        if url.scheme!='https' and not(url.scheme=='http' and url.hostname in ('127.0.0.1','localhost','::1')):
            raise ValueError('Provider URL requires HTTPS, except loopback HTTP.')
        if provider.get('kind')=='openai' and not provider.get('api_key_env'):
            raise ValueError('OpenAI providers require api_key_env, never a key in the file.')
        if provider.get('api_key_env') and not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',provider['api_key_env']):
            raise ValueError('api_key_env must be an environment variable name.')
        timeout=provider.get('timeout_seconds',90)
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 1<=timeout<=600:
            raise ValueError('timeout_seconds must be between 1 and 600.')
    models=task.get('models')
    minimum = 2 if mode in ('battle','tournament') else 1
    if not isinstance(models,list) or len(models)<minimum:
        raise ValueError(f'Supply at least {minimum} candidate models for {mode}.')
    if mode=='single' and len(models)!=1:
        raise ValueError('Single mode requires exactly one candidate.')
    if mode=='battle' and len(models)!=2:
        raise ValueError('Battle mode requires exactly two candidates.')
    judge=task.get('judge') if compare else task.setdefault('judge',{'kind':'none'})
    _keys(judge,('kind','model'),'judge')
    if judge.get('kind') not in (('rules','provider') if compare else ('rules','provider','none')):
        raise ValueError('judge.kind must be rules or provider.')
    rubric=task.get('rubric') if compare else task.setdefault('rubric',{'kind':'pairwise','description':'Capture responses without judging.'})
    _keys(rubric,('kind','description','fields'),'rubric')
    _text(rubric.get('description'),'rubric.description')
    if compare and judge['kind']=='rules':
        if rubric.get('kind')!='exact_fields' or not isinstance(rubric.get('fields'),list) or not rubric['fields']:
            raise ValueError('Rules judging requires an exact_fields rubric with fields.')
        if any(not isinstance(x,str) or not x for x in rubric['fields']) or len(set(rubric['fields']))!=len(rubric['fields']):
            raise ValueError('Rubric fields must be unique nonempty strings.')
        for artifact in artifacts:
            expected=artifact.get('expected')
            if not isinstance(expected,dict) or set(expected)!=set(rubric['fields']) or any(not isinstance(x,str) for x in expected.values()):
                raise ValueError('Each rules artifact needs exact expected string values for all rubric fields.')
    elif rubric.get('kind') not in ('pairwise','exact_fields'):
        raise ValueError('Provider rubric kind must be pairwise or exact_fields.')
    all_models=list(models)
    if judge['kind']=='provider' and (compare or judge.get('model') is not None):
        all_models.append(judge.get('model'))
    ids=[]
    for model in all_models:
        _keys(model,('id','provider','model','fixture_outputs','max_output_tokens','rates'),'model')
        ids.append(_text(model.get('id'),'model.id'))
        provider=model.get('provider')
        if provider=='fixture':
            if model is judge.get('model'):
                raise ValueError('A provider judge cannot use fixture outputs.')
            outputs=model.get('fixture_outputs')
            if not isinstance(outputs,dict) or set(outputs)!=set(artifact_ids) or any(not isinstance(x,str) or not x.strip() for x in outputs.values()):
                raise ValueError('Fixture outputs must supply nonempty text for every artifact ID.')
            if model.get('rates'):
                raise ValueError('Fixture responses have no billable usage; omit rates.')
        else:
            if provider not in providers:
                raise ValueError(f'Unknown provider reference for {model["id"]}.')
            _text(model.get('model'),'model.model')
            maximum=model.get('max_output_tokens',1024)
            if isinstance(maximum,bool) or not isinstance(maximum,int) or not 1<=maximum<=100000:
                raise ValueError('max_output_tokens must be an integer from 1 to 100000.')
        if 'rates' in model:
            rates=model['rates']
            _keys(rates,('input_per_million','output_per_million','cached_input_per_million','currency','source','as_of'),'rates')
            for field in ('input_per_million','output_per_million'):
                if field not in rates: raise ValueError(f'rates.{field} is required.')
            for field in ('input_per_million','output_per_million','cached_input_per_million'):
                if field in rates and (isinstance(rates[field],bool) or not isinstance(rates[field],(int,float)) or not math.isfinite(rates[field]) or rates[field]<0):
                    raise ValueError('Rates must be finite nonnegative numbers.')
            for field in ('currency','source','as_of'): _text(rates.get(field),f'rates.{field}')
            datetime.date.fromisoformat(rates['as_of'])
    if len(set(ids))!=len(ids):
        raise ValueError('Candidate and judge IDs must be unique.')
    max_calls=task.setdefault('max_calls',100)
    if isinstance(max_calls,bool) or not isinstance(max_calls,int) or not 1<=max_calls<=10000:
        raise ValueError('max_calls must be an integer from 1 to 10000.')
    return task


def fingerprint(task: dict) -> str:
    return hashlib.sha256(json.dumps(task,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def plan_task(task: dict, *, mode: str = 'tournament') -> dict:
    task = validate_task(task, mode=mode)
    live_candidates=sum(model['provider']!='fixture' for model in task['models'])
    n=len(task['models'])
    judge_calls=n*(n-1)//2 if task['judge']['kind']=='provider' and mode in ('battle','tournament') else 0
    return {'execution_mode':mode,'task_id':task['id'],'candidate_count':n,'artifact_count':len(task['artifacts']),'judge':task['judge']['kind'],'network_required':bool(live_candidates or judge_calls),'maximum_candidate_calls':live_candidates*len(task['artifacts']),'maximum_judge_calls':judge_calls,'configured_call_limit':task['max_calls'],'task_sha256':fingerprint(task)}
