"""Paired frozen development check of v2 task/claim semantics; no labels or API."""
from pathlib import Path
from dataclasses import replace
from collections import Counter
from run_patent_budget_check import ROOT,MARKETS,read,write,sha,check,metrics
from dynamic_retrieval.engine import run
from dynamic_retrieval.evidence import prepare_task,extract
from dynamic_retrieval.models import Config
from dynamic_retrieval.cli import save_run
GRID=dict(version='patent_grid_v1',cap_fraction=.31,width_fraction=.5)

def evaluate_corpus(task,docs,annotations,cfg,policy):
    rows=[]
    for doc in docs:
        out=extract(doc,prepare_task(task),annotations,evidence_policy=policy)
        trace=out['patent_evidence_trace']
        rows.append(dict(id=doc['id'],title=doc.get('title'),elements=out['elements'],relevance=out['relevance'],
            admitted=out['relevance']>=cfg.admission,support=out['support'],quote=out['quote'],trace=trace))
    return rows

def execute(output):
    if output.exists() or not output.is_relative_to(ROOT/'artifacts'):raise ValueError('Use a new project artifact directory')
    oldbase=ROOT/'artifacts/evidence-entry-check-20261023';previous=read(oldbase/'experiment-manifest.json')
    oldretrieval=ROOT/'artifacts/retrieval-optimization-20261023';retrievalmanifest=read(oldretrieval/'experiment-manifest.json')
    items=[];source={}
    for market in MARKETS:
        folder=oldbase/'runs'/market/'enhanced'
        paths=[folder/'inputs'/(name+'.json') for name in ('task','documents','annotations')]
        for p in paths:
            assert sha(p)==previous['files'][p.relative_to(oldbase).as_posix()]
            source[p.relative_to(ROOT).as_posix()]=sha(p)
        items.append((market,paths))
    codes={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}
    codes[Path(__file__).resolve().relative_to(ROOT).as_posix()]=sha(Path(__file__))
    plan=dict(scope='previously_inspected_development_only',markets=MARKETS,modes=['fixed','basic','enhanced'],
        source_sha256=source,code_sha256=codes,model_requests=0,label_access=False,new_runs=9,legacy_parity_runs=24,
        evidence_policy='patent_elements_v2',comparison_evidence_policy='patent_elements_v1',
        budget_policy='patent_budget_v1',retrieval_policy='bm25_read_guard_v1',grid_policy=GRID,
        cost_status='unchanged_uncalibrated_examples',annotations='unchanged_frozen_machine_annotations',
        claims_allowed=['task_contract_coverage','source_grounded_normalization','admission_and_rule_diagnostics'],
        claims_not_established=['prediction_accuracy','independent_generalization','monetary_savings','empirical_calibration'])
    write(output/'execution-plan.json',plan);records=[];parity=0
    for market,paths in items:
        task,docs,annotations=map(read,paths);cfg=Config.from_dict(read(oldbase/'runs'/market/'enhanced/result.json')['config'])
        for base,manifest in ((oldbase,previous),(oldretrieval,retrievalmanifest)):
            for path in sorted((base/'runs'/market).glob('*/result.json')):
                assert sha(path)==manifest['files'][path.relative_to(base).as_posix()]
                old=read(path);p=old['provenance']
                replay=run(task,docs,Config.from_dict(old['config']),annotations,comparison_policy=p.get('comparison_policy'),
                    budget_policy=p.get('budget_policy'),grid_policy=p.get('grid_policy'),retrieval_policy=p.get('retrieval_policy'),
                    evidence_policy=p.get('evidence_policy'))
                assert replay==old,(path,'legacy output changed');parity+=1
        before=evaluate_corpus(task,docs,annotations,cfg,'patent_elements_v1')
        after=evaluate_corpus(task,docs,annotations,cfg,'patent_elements_v2')
        changes=[]
        for old,new in zip(before,after):
            changes.append(dict(id=new['id'],title=new['title'],before={k:old[k] for k in ('elements','relevance','admitted','support')},
                after={k:new[k] for k in ('elements','relevance','admitted','support')},
                assertion=new['trace']['normalization'].get('assertion'),blockers=new['trace']['support']['blockers']))
        write(output/'diagnostics'/market/'documents.json',dict(origin='full_frozen_corpus_not_prediction_input',before=before,after=after,changes=changes))
        diagnostic=dict(before_admitted=sum(e['admitted'] for e in before),after_admitted=sum(e['admitted'] for e in after),
            before_directional=sum(any(e['support']) for e in before),after_directional=sum(any(e['support']) for e in after),
            normalized_documents=sum(bool(e['elements']) for e in after),
            structured_contract=after[0]['trace'].get('structured_contract') if after else None,
            after_relevance_counts=dict(Counter(str(e['relevance']) for e in after)),
            after_support_blockers=dict(Counter(b for e in after for b in e['trace']['support']['blockers'])))
        record=dict(market=market,documents=len(docs),diagnostic=diagnostic,runs={})
        for mode in plan['modes']:
            new=run(task,docs,replace(cfg,mode=mode),annotations,evidence_policy='patent_elements_v2',budget_policy='patent_budget_v1',
                grid_policy=GRID if mode=='enhanced' else None,retrieval_policy='bm25_read_guard_v1');check(new)
            folder=output/'runs'/market/mode;save_run(new,folder)
            for name,value in zip(('task','documents','annotations'),(task,docs,annotations)):write(folder/'inputs'/(name+'.json'),value)
            manifest=read(folder/'manifest.json');manifest['files'].update({p.relative_to(folder).as_posix():sha(p) for p in (folder/'inputs').iterdir()});write(folder/'manifest.json',manifest)
            old=read(oldbase/'runs'/market/mode/'result.json')
            record['runs'][mode]=dict(before=dict(metrics(old),admitted=old['diagnostics']['admitted_documents'],probabilities=old['result']['probabilities']),
                after=dict(metrics(new),admitted=new['diagnostics']['admitted_documents'],probabilities=new['result']['probabilities']))
        records.append(record)
    assert parity==24
    for name,expected in {**source,**codes}.items():assert sha(ROOT/name)==expected
    summary=dict(status='completed_frozen_development_check',events=3,documents=60,new_runs=9,legacy_parity_runs=parity,
        model_requests=0,independent_evaluation=False,empirical_calibration=False,records=records,
        claim='Bounded source semantics development; admission changes do not establish prediction quality.')
    write(output/'summary.json',summary)
    write(output/'experiment-manifest.json',dict(artifact_type='patent_semantics_v2_development',source_sha256=source,
        code_sha256=codes,files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}))
    print(__import__('json').dumps(dict(status=summary['status'],legacy_parity_runs=parity,records=[dict(market=r['market'],
        before_admitted=r['diagnostic']['before_admitted'],after_admitted=r['diagnostic']['after_admitted'],
        normalized_documents=r['diagnostic']['normalized_documents'],directional=r['diagnostic']['after_directional'],
        runs=r['runs']) for r in records]),ensure_ascii=False,indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    execute(parser.parse_args().output.resolve())
