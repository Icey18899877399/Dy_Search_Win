"""Frozen development diagnostic of opt-in patent evidence; no model calls or labels."""
from pathlib import Path
from collections import Counter
from dataclasses import replace
from run_patent_budget_check import ROOT,MARKETS,read,write,sha,check,metrics
from dynamic_retrieval.engine import run
from dynamic_retrieval.evidence import prepare_task,extract
from dynamic_retrieval.models import Config
from dynamic_retrieval.cli import save_run

GRID=dict(version='patent_grid_v1',cap_fraction=.31,width_fraction=.5)
def execute(output):
    if output.exists() or not output.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Use a new output directory under project artifacts')
    previous=ROOT/'artifacts/retrieval-optimization-20261023'
    previous_manifest=read(previous/'experiment-manifest.json')
    items=[];source={}
    for market in MARKETS:
        folder=previous/'runs'/market/'enhanced_bm25'
        paths=[folder/'inputs'/(name+'.json') for name in ('task','documents','annotations')]
        for p in paths:
            assert sha(p)==previous_manifest['files'][p.relative_to(previous).as_posix()]
            source[p.relative_to(ROOT).as_posix()]=sha(p)
        items.append((market,paths))
    codes={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}
    codes[Path(__file__).resolve().relative_to(ROOT).as_posix()]=sha(Path(__file__))
    plan=dict(scope='previously_inspected_development_only',markets=MARKETS,modes=['fixed','basic','enhanced'],
        source_sha256=source,code_sha256=codes,model_requests=0,label_access=False,new_runs=9,legacy_parity_runs=15,
        evidence_policy='patent_elements_v1',budget_policy='patent_budget_v1',retrieval_policy='bm25_read_guard_v1',grid_policy=GRID,
        cost_status='unchanged_uncalibrated_examples',support_contracts='unchanged_tasks_no_new_rules_or_aliases',
        limitations=['Not independent evaluation','Diagnostics of existing frozen model extraction only',
            'Narrow explicit rule coverage; neutral output does not establish prediction quality'])
    write(output/'execution-plan.json',plan)
    records=[]
    for market,paths in items:
        task,docs,annotations=map(read,paths)
        for path in sorted((previous/'runs'/market).glob('*/result.json')):
            assert sha(path)==previous_manifest['files'][path.relative_to(previous).as_posix()]
            old=read(path);p=old['provenance']
            current=run(task,docs,Config.from_dict(old['config']),annotations,
                comparison_policy=p.get('comparison_policy'),budget_policy=p.get('budget_policy'),
                grid_policy=p.get('grid_policy'),retrieval_policy=p.get('retrieval_policy'))
            assert current==old,(market,path.parent.name,'historical output changed')
        cfg=Config.from_dict(read(previous/'runs'/market/'enhanced_bm25/result.json')['config'])
        diagnostics=[extract(d,prepare_task(task),annotations,evidence_policy='patent_elements_v1') for d in docs]
        diagnostic=dict(origin='full_frozen_corpus_not_prediction_input',task=task,
            documents=len(diagnostics),admitted=sum(e['relevance']>=cfg.admission for e in diagnostics),
            directional=sum(any(x!=0 for x in e['support']) for e in diagnostics),
            task_parse=diagnostics[0]['patent_evidence_trace']['task_parse'] if diagnostics else None,
            effective_target=diagnostics[0]['patent_evidence_trace']['effective_target'] if diagnostics else None,
            relevance_counts=dict(Counter(str(e['relevance']) for e in diagnostics)),
            support_resolutions=dict(Counter(e['patent_evidence_trace']['support']['resolution'] for e in diagnostics)),
            support_blockers=dict(Counter(b for e in diagnostics for b in e['patent_evidence_trace']['support']['blockers'])))
        write(output/'diagnostics'/market/'full-corpus.json',diagnostic)
        record=dict(market=market,documents=len(docs),diagnostic=diagnostic,runs={})
        for mode in plan['modes']:
            result=run(task,docs,replace(cfg,mode=mode),annotations,evidence_policy='patent_elements_v1',
                budget_policy='patent_budget_v1',grid_policy=GRID if mode=='enhanced' else None,
                retrieval_policy='bm25_read_guard_v1')
            check(result)
            folder=output/'runs'/market/mode
            save_run(result,folder)
            for name,value in zip(('task','documents','annotations'),(task,docs,annotations)):
                write(folder/'inputs'/(name+'.json'),value)
            manifest=read(folder/'manifest.json')
            manifest['files'].update({p.relative_to(folder).as_posix():sha(p) for p in (folder/'inputs').iterdir()})
            write(folder/'manifest.json',manifest)
            record['runs'][mode]=dict(metrics(result),admitted=result['diagnostics']['admitted_documents'],
                probabilities=result['result']['probabilities'])
        records.append(record)
    for name,expected in {**source,**codes}.items():assert sha(ROOT/name)==expected
    summary=dict(status='completed_frozen_development_check',events=3,documents=60,new_runs=9,legacy_parity_runs=15,
        model_requests=0,independent_evaluation=False,empirical_calibration=False,records=records,
        claim='Evidence-chain and entry integrity verified; no prediction accuracy gain or real monetary saving claim.')
    write(output/'summary.json',summary)
    write(output/'experiment-manifest.json',dict(artifact_type='patent_evidence_entry_development',source_sha256=source,
        code_sha256=codes,files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}))
    print(__import__('json').dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    execute(parser.parse_args().output.resolve())
