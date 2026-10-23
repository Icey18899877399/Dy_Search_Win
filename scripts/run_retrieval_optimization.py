"""Predeclared paired frozen development check; no model or label access."""
from dataclasses import replace
from collections import Counter
from pathlib import Path
import json
from run_patent_budget_check import ROOT,MARKETS,read,write,sha,check,metrics
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.cli import save_run

GRID=dict(version='patent_grid_v1',cap_fraction=.31,width_fraction=.5)
CONDITIONS=(('fixed_guard','fixed','read_guard_v1'),('fixed_bm25','fixed','bm25_read_guard_v1'),
    ('enhanced_feasible','enhanced',None),('enhanced_guard','enhanced','read_guard_v1'),
    ('enhanced_bm25','enhanced','bm25_read_guard_v1'))

def observations(result):
    rows=result['rounds'];events=[e for r in rows for e in r['decision_trace']['retrieval_events']]
    return dict(metrics(result),admitted_documents=result['diagnostics']['admitted_documents'],
        probe_spent=sum(r['budget']['probe'] for r in rows),
        probe_rounds_without_read=sum(r['budget']['probe']>0 and not any(e['phase']=='probe' and e['read_cost']>0 for e in r['decision_trace']['retrieval_events']) for r in rows),
        admission_status_counts=dict(Counter(e['status'] for e in events)),
        skipped_unaffordable_requests=result['diagnostics'].get('retrieval_execution',{}).get('skipped_unaffordable_requests'),
        indexed_chunks=result['diagnostics'].get('retrieval_execution',{}).get('indexed_chunks'),
        final_unread_band_documents=rows[-1]['decision_trace']['loss_observation'].get('unread_band_documents'),
        read_ids=sorted({e['document_id'] for e in events}),
        read_order=[e['document_id'] for e in events if e['read_cost']>0])

def execute(output):
    if output.exists():raise ValueError('New output directory required')
    old_grid=ROOT/'artifacts/source-grid-check-20261023'
    old_budget=ROOT/'artifacts/patent-budget-check-20261023'
    inputs=read(old_grid/'experiment-manifest.json')['source_sha256'].copy()
    items=[]
    for market in MARKETS:
        td=next((ROOT/'artifacts').glob('semantic-v5-independent-*/inputs/tasks/'+market))
        paths=[td/'task.json',td/'forecast-documents.json',td.parent.parent.parent/'runs'/market/'machine-annotations.json']
        for p in paths:assert sha(p)==inputs[p.relative_to(ROOT).as_posix()]
        items.append((market,paths))
        p=old_grid/'runs'/market/'enhanced.json'
        assert sha(p)==read(old_grid/'experiment-manifest.json')['files'][p.relative_to(old_grid).as_posix()]
        inputs[p.relative_to(ROOT).as_posix()]=sha(p)
    codes={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}
    codes[Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
    plan=dict(scope='previously_inspected_development_only',markets=MARKETS,conditions=CONDITIONS,
        grid_policy=GRID,grid_choice='Analytic minimum query+fresh read feasibility, not prediction tuning',
        grid_previous=dict(version='patent_grid_v1',cap_fraction=.2,width_fraction=.25),
        cost_status='unchanged_uncalibrated_examples',new_runs=15,legacy_parity_runs=9,
        model_requests=0,label_access=False,source_sha256=inputs,code_sha256=codes,
        invariants=['same inputs and annotations','same total budget and rounds','same query/read costs',
            'same admission and fact weights','same loss/recovery equations'],
        limitations=['Not independent evaluation','Offline full-text indexing cost not measured',
            'Grid change is a declared configuration change, not a ranking effect'])
    write(output/'execution-plan.json',plan)
    records=[]
    for market,paths in items:
        task,docs,annotations=map(read,paths)
        for mode in ('basic','enhanced'):
            old=read(old_budget/'runs'/market/(mode+'.json'))
            replay=run(task,docs,Config.from_dict(old['config']),annotations,comparison_policy='typed_v6',budget_policy='patent_budget_v1')
            assert replay==old,(market,mode,'legacy drift')
        old=read(old_grid/'runs'/market/'enhanced.json');cfg=Config.from_dict(old['config'])
        replay=run(task,docs,cfg,annotations,comparison_policy='typed_v6',budget_policy='patent_budget_v1',grid_policy=plan['grid_previous'])
        assert replay==old,(market,'grid legacy drift')
        try:run(task,docs,cfg,annotations,budget_policy='patent_budget_v1',grid_policy=plan['grid_previous'],retrieval_policy='read_guard_v1')
        except ValueError as exc:assert 'fresh read' in str(exc)
        else:raise AssertionError('unexecutable grid accepted')
        record=dict(market=market,documents=len(docs),historical_grid=observations(old),conditions={})
        for name,mode,policy in CONDITIONS:
            result=run(task,docs,replace(cfg,mode=mode),annotations,comparison_policy='typed_v6',
                budget_policy='patent_budget_v1',grid_policy=GRID if mode=='enhanced' else None,retrieval_policy=policy)
            check(result)
            for row in result['rounds']:
                if mode=='enhanced':
                    cells=row['decision_trace']['grid_budget']['cells']
                    assert all(c['spent']<=c['allocated_budget']+1e-8 and c['allocated_budget'] in (0,c['nominal_budget']) for c in cells)
                obs=row['decision_trace']['loss_observation']
                assert abs(obs['loss']-sum(x['contribution'] for x in obs['band_evidence']))<1e-8
            folder=output/'runs'/market/name
            save_run(result,folder)
            for filename,value in zip(('task','documents','annotations'),(task,docs,annotations)):
                write(folder/'inputs'/(filename+'.json'),value)
            manifest=read(folder/'manifest.json')
            manifest['files'].update({p.relative_to(folder).as_posix():sha(p) for p in (folder/'inputs').iterdir()})
            write(folder/'manifest.json',manifest)
            record['conditions'][name]=observations(result)
        records.append(record)
    for name,digest in inputs.items():assert sha(ROOT/name)==digest
    for name,digest in codes.items():assert sha(ROOT/name)==digest
    summary=dict(status='completed_frozen_development_check',new_runs=15,legacy_parity_runs=9,events=3,documents=60,
        model_requests=0,independent_evaluation=False,empirical_calibration=False,records=records,
        claim='Candidate execution and budget observations only; no prediction accuracy or monetary saving claim.')
    write(output/'summary.json',summary)
    write(output/'experiment-manifest.json',dict(artifact_type='retrieval_optimization_development',source_sha256=inputs,
        code_sha256=codes,files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}))
    print(json.dumps({**summary,'records':[{**r,'historical_grid':{k:v for k,v in r['historical_grid'].items() if not k.startswith('read_')},'conditions':{n:{k:v for k,v in x.items() if not k.startswith('read_')} for n,x in r['conditions'].items()}} for r in records]},ensure_ascii=False,indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.resolve()
    if not output.is_relative_to(ROOT/'artifacts'):raise ValueError('Output must be under project artifacts')
    execute(output)
