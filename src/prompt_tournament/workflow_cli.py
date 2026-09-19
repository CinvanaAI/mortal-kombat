"""Installed CLI: meaningful offline first use and explicit configured execution."""
from __future__ import annotations
import argparse
import importlib.resources
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .report import save_report
from .task import plan_task,validate_task
from .workflow import run_task
from .providers import ProviderFailure


def demo_task() -> dict:
    return json.loads(importlib.resources.files('prompt_tournament').joinpath('fixtures/extraction.json').read_text(encoding='utf-8'))


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Compare candidate outputs on a concrete task and inspect the evidence.')
    commands=parser.add_subparsers(dest='command',required=True)
    demo=commands.add_parser('demo',help='Run the offline structured-extraction fixture.')
    demo.add_argument('--out',type=Path,required=True,help='New result directory; existing directories are never overwritten.')
    init=commands.add_parser('example',help='Write a complete editable offline task file.')
    init.add_argument('path',type=Path)
    run=commands.add_parser('run',help='Validate and preview a task; --execute permits configured provider calls.')
    run.add_argument('task',type=Path)
    run.add_argument('--out',type=Path)
    run.add_argument('--execute',action='store_true')
    run.add_argument('--mode',choices=('single','batch','battle','tournament'),default='tournament')
    gui=commands.add_parser('gui',help='Open the local desktop workbench (requires Python Tk support).')
    gui.add_argument('task',type=Path,nargs='?')
    discover=commands.add_parser('models',help='List model IDs from one configured connection; no generation calls.')
    discover.add_argument('task',type=Path)
    discover.add_argument('--provider',required=True)
    probe=commands.add_parser('probe',help='Preview or explicitly send a short greeting to selected candidates.')
    probe.add_argument('task',type=Path)
    probe.add_argument('--candidate',action='append',required=True,help='Candidate ID; repeat for several models.')
    probe.add_argument('--execute',action='store_true')
    probe.add_argument('--out',type=Path)
    report=commands.add_parser('report',help='Render a saved result without executing candidates or providers.')
    report.add_argument('result',type=Path)
    report.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='gui':
            from .workbench import launch_workbench
            launch_workbench(args.task)
            return 0
        if args.command=='models':
            from .providers import list_models
            task=validate_task(json.loads(args.task.read_text(encoding='utf-8-sig')),mode='batch')
            if args.provider not in task['providers']:
                raise ValueError('Choose a provider name present in the task file.')
            ids=list_models(task['providers'][args.provider])
            print(json.dumps({'provider':args.provider,'models':ids,'note':'Listed by the connection; text-task and endpoint compatibility must be checked when running.'},indent=2))
            return 0
        if args.command=='probe':
            from .providers import probe_model
            task=validate_task(json.loads(args.task.read_text(encoding='utf-8-sig')),mode='batch')
            candidates={m['id']:m for m in task['models']}
            if len(args.candidate)!=len(set(args.candidate)) or any(i not in candidates for i in args.candidate):
                raise ValueError('Choose unique candidate IDs present in the task.')
            selected=[candidates[i] for i in args.candidate]
            if any(m['provider']=='fixture' for m in selected):
                raise ValueError('Greeting probes require configured provider models, not fixtures.')
            if not args.execute:
                print(json.dumps({'mode':'probe-plan','candidates':args.candidate,'maximum_provider_calls':len(selected),'max_output_tokens_per_call':32},indent=2))
                return 0
            if args.out is None:
                raise ValueError('--out is required for execution.')
            for model in selected:
                name=task['providers'][model['provider']].get('api_key_env')
                if name and not os.environ.get(name,'').strip():
                    raise ValueError(f'Required environment variable {name} is unset.')
            args.out.mkdir(parents=True,exist_ok=False)
            records=[]
            for model in selected:
                provider=task['providers'][model['provider']]
                records.append({'candidate_id':model['id'],'model':model['model'],'provider':model['provider'],
                                'base_url':provider['base_url'],'endpoint':provider.get('endpoint','responses' if provider['kind']=='openai' else 'chat'),
                                'observed_at':datetime.now(timezone.utc).isoformat(),**probe_model(provider,model)})
                # Preserve each observation even if a later call is interrupted.
                (args.out/'probes.json').write_text(json.dumps({'schema':'mortal-kombat.probes.v1','prompt':'Reply with exactly: hi','records':records},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({'result':str(args.out/'probes.json'),'statuses':{r['candidate_id']:r['status'] for r in records}},indent=2))
            return 0 if all(r['status']=='text-response' for r in records) else 1
        if args.command=='report':
            result=json.loads(args.result.read_text(encoding='utf-8-sig'))
            if not isinstance(result,dict) or result.get('schema')!='mortal-kombat.result.v1':
                raise ValueError('Expected a mortal-kombat.result.v1 result.')
            from .report import render_report
            # Validate rendering before reserving output; this path never runs a task.
            rendered=render_report(result)
            args.out.mkdir(parents=True,exist_ok=False)
            save_report(result,args.out,renderer=lambda _:rendered)
            print(f'Rendered saved evidence: {args.out / "report.html"}')
            return 0
        if args.command=='example':
            with args.path.open('x',encoding='utf-8') as handle:
                json.dump(demo_task(),handle,indent=2,ensure_ascii=False);handle.write('\n')
            print(f'Wrote editable task: {args.path}')
            return 0
        mode=getattr(args,'mode','tournament')
        task=validate_task(demo_task() if args.command=='demo' else json.loads(args.task.read_text(encoding='utf-8-sig')),mode=mode)
        plan=plan_task(task,mode=mode)
        if args.command=='run' and not args.execute:
            print(json.dumps({'mode':'plan',**plan},indent=2))
            return 0
        if args.out is None:
            raise ValueError('--out is required for execution.')
        # Reserve a new directory before any call. Two processes cannot silently
        # write into one result set, and an existing run can never be replaced.
        args.out.mkdir(parents=True,exist_ok=False)
        result=run_task(task,allow_network=args.command=='run' and args.execute,mode=mode)
        save_report(result,args.out)
        print(json.dumps({'status':result['status'],'result':str(args.out/'result.json'),'report':str(args.out/'report.html'),'provider_calls_attempted':result['provider_calls_attempted']},indent=2))
        return 0 if result['status']=='completed' else 1
    except (ValueError,OSError,KeyError,TypeError,ImportError,ProviderFailure) as exc:
        print(f'Cannot run: {exc}')
        return 2


if __name__=='__main__':
    raise SystemExit(main())
