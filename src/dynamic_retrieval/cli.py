"""CLI entry points; all artifact paths are explicit or project-relative."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import sqlite3
import re
from .models import Config
from .engine import run
from .demo import demo_result
from .report import render_report
from .evaluation import summarize_comparison
from .data.store import build_index, Store

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_DATA=Path(r'D:\agents-main\agents\polymarket\data')


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def market_directory(market_id):
    value=str(market_id)
    reserved={'CON','PRN','AUX','NUL'}|{f'{p}{i}' for p in ('COM','LPT') for i in range(1,10)}
    if re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value) and value.upper() not in reserved:return value
    return 'market-'+hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]


def save_run(result,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    write_json(output/'result.json',result)
    write_json(output/'rounds.json',result['rounds'])
    write_json(output/'evidence.json',result['evidence'])
    render_report(result,output/'report.html')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.name in ('result.json','rounds.json','evidence.json','report.html')}
    write_json(output/'manifest.json',dict(format_version=1,files=hashes,python=sys.version,
              mode=result['config']['mode'],market_id=result['task']['market_id'],cutoff=result['task']['cutoff'],
              visible_documents=result['diagnostics']['visible_documents'],
              input_sha256=result['provenance']['input_sha256'],
              annotation_sha256=result['provenance']['annotation_sha256'],
              code_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((ROOT/'src').rglob('*.py'))},
              config_sha256=hashlib.sha256(json.dumps(result['config'],sort_keys=True).encode()).hexdigest()))


def load_task(store,market,cutoff,task_file=None):
    tasks={str(t['market_id']):t for t in store.tasks(cutoff)}
    if market not in tasks:raise ValueError(f'Market {market} has no task snapshot before cutoff')
    task=tasks[market]
    if task_file:
        spec=read_json(task_file)
        allowed={'target_elements','element_aliases','positive_patterns','negative_patterns','support_rules'}
        if set(spec)-allowed:raise ValueError('Task rule file only accepts '+', '.join(sorted(allowed)))
        task.update(spec)
    task['cutoff']=cutoff
    return task


def parser():
    p=argparse.ArgumentParser(description='事件预测动态检索窗口：专利离线实现')
    sub=p.add_subparsers(dest='command',required=True)
    index=sub.add_parser('index',help='审计归档并建立可重复构建的 SQLite 索引')
    index.add_argument('--data',type=Path,default=DEFAULT_DATA);index.add_argument('--db',type=Path,default=ROOT/'artifacts/index.sqlite')
    tasks=sub.add_parser('tasks',help='列出截止时刻之前的任务')
    tasks.add_argument('--db',type=Path,default=ROOT/'artifacts/index.sqlite');tasks.add_argument('--cutoff',required=True)
    tasks.add_argument('--limit',type=int,default=20)
    for name in ('run','compare','annotate-template'):
        r=sub.add_parser(name)
        r.add_argument('--db',type=Path,default=ROOT/'artifacts/index.sqlite')
        r.add_argument('--market',required=True);r.add_argument('--cutoff',required=True)
        r.add_argument('--config',type=Path);r.add_argument('--task-rules',type=Path);r.add_argument('--annotations',type=Path)
        r.add_argument('--output',type=Path,required=True)
        r.add_argument('--mode',choices=['fixed','basic','enhanced'],default=None)
        if name in ('run','compare'):
            r.add_argument('--budget-policy',choices=['patent_budget_v1'],default=None,
                help='专利预算账本与整带回收；未传入时复现历史行为')
            r.add_argument('--evidence-policy',choices=['patent_elements_v1','patent_elements_v2','patent_elements_v3','patent_elements_v4'],default=None)
            r.add_argument('--retrieval-policy',choices=['read_guard_v1','bm25_read_guard_v1'],default=None)
            r.add_argument('--grid-policy',type=Path,help='逐格预算 JSON 配置；compare 仅用于 enhanced')
            r.add_argument('--source-cost-profile',type=Path,help='完整可见来源的成本观测 JSON 配置')
    pilot=sub.add_parser('pilot',help='对少量真实问题执行三种配置并输出汇总')
    pilot.add_argument('--db',type=Path,default=ROOT/'artifacts/index.sqlite');pilot.add_argument('--cutoff',required=True)
    pilot.add_argument('--count',type=int,default=5);pilot.add_argument('--min-documents',type=int,default=5)
    pilot.add_argument('--config',type=Path);pilot.add_argument('--output',type=Path,required=True)
    demo=sub.add_parser('demo',help='运行人工标注的合成验收场景')
    demo.add_argument('--output',type=Path,default=ROOT/'artifacts/demo')
    demo.add_argument('--mode',choices=['fixed','basic','enhanced'],default='enhanced')
    report=sub.add_parser('report');report.add_argument('result',type=Path);report.add_argument('--output',type=Path,required=True)
    return p


def execution_options(args, mode):
    grid=read_json(args.grid_policy) if args.grid_policy else None
    profile=read_json(args.source_cost_profile) if args.source_cost_profile else None
    if (grid is not None or profile is not None) and args.budget_policy!='patent_budget_v1':
        raise ValueError('Grid and cost profiles require --budget-policy patent_budget_v1')
    if grid is not None and args.command=='run' and mode!='enhanced':
        raise ValueError('Grid policy requires enhanced mode')
    return dict(budget_policy=args.budget_policy,grid_policy=grid if mode=='enhanced' else None,
                source_cost_profile=profile,retrieval_policy=args.retrieval_policy,evidence_policy=args.evidence_policy)


def main(argv=None):
    # Archive titles and filesystem paths may contain characters outside Windows GBK.
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='backslashreplace')
    p=parser();args=p.parse_args(argv)
    try:
        if args.command=='index':
            audit=build_index(args.data,args.db)
            print(json.dumps(audit,ensure_ascii=False,indent=2));return 0
        if args.command=='demo':
            result=demo_result(args.mode);save_run(result,args.output)
            print(json.dumps(result['result'],ensure_ascii=False));print(args.output.resolve()/'report.html');return 0
        if args.command=='report':
            render_report(read_json(args.result),args.output);print(args.output.resolve());return 0
        with Store(args.db) as store:
            if args.command=='tasks':
                if args.limit<1:raise ValueError('--limit must be positive')
                tasks=store.tasks(args.cutoff)
                print(json.dumps(dict(total=len(tasks),tasks=tasks[:args.limit]),ensure_ascii=False,indent=2));return 0
            cfg=Config.from_dict(read_json(args.config)) if args.config else Config()
            if args.command=='pilot':
                if args.count<1 or args.min_documents<1:raise ValueError('Positive pilot sizes required')
                summaries=[]
                for task in sorted(store.tasks(args.cutoff),key=lambda t:str(t['market_id'])):
                    if {str(x).lower() for x in task['outcomes']}!={'yes','no'} or task.get('metadata_quality')!='full_metadata':continue
                    docs=store.documents(task['event_id'],args.cutoff)
                    if len(docs)<args.min_documents:continue
                    task['cutoff']=args.cutoff;results={}
                    for mode in ('fixed','basic','enhanced'):
                        result=run(task,docs,replace(cfg,mode=mode));results[mode]=result
                        save_run(result,args.output/market_directory(task['market_id'])/mode)
                    summary=summarize_comparison(results,store.labels(task['market_id']))
                    summary.update(market_id=task['market_id'],question=task['question'],cutoff=args.cutoff)
                    summaries.append(summary)
                    print(f"Pilot {len(summaries)}/{args.count}: {task['market_id']}",flush=True)
                    if len(summaries)>=args.count:break
                write_json(args.output/'summary.json',dict(requested=args.count,completed=len(summaries),tasks=summaries,
                           extraction='unreviewed lexical; support abstains',parameters='illustrative; not calibrated'))
                return 0 if len(summaries)==args.count else 2
            task=load_task(store,args.market,args.cutoff,args.task_rules)
            docs=store.documents(task['event_id'],args.cutoff)
            if args.command=='annotate-template':
                from .evidence import prepare_task,extract
                task=prepare_task(task)
                template={d['id']:dict(reviewed=False,elements=extract(d,task)['elements'],support=[0,0],
                                      quote=d['text'][:300],title=d['title'],source_file=d['source_file']) for d in docs}
                write_json(args.output,template);print(f'{len(template)} unreviewed annotation entries');return 0
            annotation=read_json(args.annotations) if args.annotations else None
            if args.mode:cfg=replace(cfg,mode=args.mode)
            if args.command=='run':
                result=run(task,docs,cfg,annotation,**execution_options(args,cfg.mode));save_run(result,args.output)
                print(json.dumps(result['result'],ensure_ascii=False));print(args.output.resolve()/'report.html')
            else:
                results={}
                for mode in ('fixed','basic','enhanced'):
                    results[mode]=run(task,docs,replace(cfg,mode=mode),annotation,**execution_options(args,mode))
                    save_run(results[mode],args.output/mode)
                summary=summarize_comparison(results,store.labels(task['market_id']))
                write_json(args.output/'comparison.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError,sqlite3.Error) as exc:
        p.exit(2,f'Error: {exc}\n')


if __name__=='__main__':raise SystemExit(main())
