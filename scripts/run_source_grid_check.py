"""Frozen three-event development check; zero remote/model calls."""
import json
from pathlib import Path
from run_patent_budget_check import ROOT,MARKETS,read,write,sha,check,metrics
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config

POLICY=dict(version='patent_grid_v1',cap_fraction=.2,width_fraction=.25)

def execute(output):
    if output.exists():raise ValueError('New output directory required')
    previous=ROOT/'artifacts/patent-budget-check-20261023'
    manifest=read(previous/'experiment-manifest.json')
    source_hashes=dict(manifest['source_sha256'])
    for relative,digest in source_hashes.items():assert sha(ROOT/relative)==digest
    items=[]
    for market in MARKETS:
        td=next((ROOT/'artifacts').glob('semantic-v5-independent-*/inputs/tasks/'+market))
        paths=[td/'task.json',td/'forecast-documents.json',td.parent.parent.parent/'runs'/market/'machine-annotations.json']
        items.append((market,paths))
        for mode in ('basic','enhanced'):
            path=previous/'runs'/market/(mode+'.json')
            assert sha(path)==manifest['files'][path.relative_to(previous).as_posix()]
            source_hashes[path.relative_to(ROOT).as_posix()]=sha(path)
    codes={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}
    codes[Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
    write(output/'execution-plan.json',dict(scope='previously_inspected_development_only',markets=MARKETS,
        grid_policy=POLICY,source_cost_profile=None,cost_status='unchanged_uncalibrated_examples',
        new_runs=3,prior_budget_parity_runs=6,model_requests=0,label_access=False,
        source_sha256=source_hashes,code_sha256=codes))
    records=[]
    for market,paths in items:
        task,docs,annotations=map(read,paths)
        for mode in ('basic','enhanced'):
            old=read(previous/'runs'/market/(mode+'.json'));cfg=Config.from_dict(old['config'])
            same=run(task,docs,cfg,annotations,comparison_policy='typed_v6',budget_policy='patent_budget_v1')
            assert same==old,(market,mode,'prior budget behavior drift')
            if mode!='enhanced':continue
            new=run(task,docs,cfg,annotations,comparison_policy='typed_v6',budget_policy='patent_budget_v1',grid_policy=POLICY)
            check(new)
            for row in new['rounds']:
                grid=row['decision_trace']['grid_budget']
                assert abs(sum(c['spent'] for c in grid['cells'])-row['budget']['probe'])<1e-8
                assert all(c['spent']<=c['allocated_budget']+1e-8 and c['allocated_budget'] in (0,c['nominal_budget']) for c in grid['cells'])
            write(output/'runs'/market/'enhanced.json',new)
            records.append(dict(market=market,documents=len(docs),before=metrics(old),after=metrics(new),
                feasibility=new['diagnostics']['budget_feasibility']))
    summary=dict(status='verified_development_grid_check',markets=MARKETS,documents=sum(len(read(p[1])) for _,p in items),
        new_runs=3,prior_budget_parity_runs=6,model_requests=0,independent_evaluation=False,
        empirical_calibration=False,records=records,claim='Formula and budget correctness only; no prediction quality improvement claim.')
    write(output/'summary.json',summary)
    for relative,digest in source_hashes.items():assert sha(ROOT/relative)==digest
    for relative,digest in codes.items():assert sha(ROOT/relative)==digest
    write(output/'experiment-manifest.json',dict(artifact_type='source_grid_development_check',source_sha256=source_hashes,
        code_sha256=codes,files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.resolve()
    if not output.is_relative_to(ROOT/'artifacts'):raise ValueError('Output must be under project artifacts')
    execute(output)
