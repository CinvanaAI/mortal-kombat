"""Installed CLI: meaningful offline first use and explicit configured execution."""
from __future__ import annotations
import argparse
import importlib.resources
import json
from pathlib import Path
from .report import save_report
from .task import plan_task,validate_task
from .workflow import run_task


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
    report=commands.add_parser('report',help='Render a saved result without executing candidates or providers.')
    report.add_argument('result',type=Path)
    report.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
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
        task=validate_task(demo_task() if args.command=='demo' else json.loads(args.task.read_text(encoding='utf-8-sig')))
        plan=plan_task(task)
        if args.command=='run' and not args.execute:
            print(json.dumps({'mode':'plan',**plan},indent=2))
            return 0
        if args.out is None:
            raise ValueError('--out is required for execution.')
        # Reserve a new directory before any call. Two processes cannot silently
        # write into one result set, and an existing run can never be replaced.
        args.out.mkdir(parents=True,exist_ok=False)
        result=run_task(task,allow_network=args.command=='run' and args.execute)
        save_report(result,args.out)
        print(json.dumps({'status':result['status'],'result':str(args.out/'result.json'),'report':str(args.out/'report.html'),'provider_calls_attempted':result['provider_calls_attempted']},indent=2))
        return 0 if result['status']=='completed' else 1
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f'Cannot run: {exc}')
        return 2


if __name__=='__main__':
    raise SystemExit(main())
