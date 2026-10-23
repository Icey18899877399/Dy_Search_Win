"""Bounded, frozen-development check of patent budget semantics (no model calls)."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config

MARKETS=('1171663','1423716','2354063')

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def check(out):
    remaining=out['config']['total_budget']
    baseline=remaining/out['config']['rounds']
    for row in out['rounds']:
        plan=row['decision_trace']['budget_plan']; costs=row['budget']
        assert abs(plan['regular_baseline']-baseline)<1e-8
        assert abs(plan['remaining_at_start']-remaining)<1e-8
        assert abs(plan['effective']-min(baseline,remaining))<1e-8
        assert sum(plan['reserves'].values())<=plan['effective']+1e-8
        assert abs(sum(costs.values())-row['spent'])<1e-8
        assert row['spent']<=plan['effective']+1e-8
        assert costs['watch']+costs['recovery']<=plan['shared_limit']+1e-8
        if row['state_before']!='slow':assert costs['watch']==0
        wait=row['decision_trace']['waiting_budget']
        assert wait['charged_this_round']==costs['watch']
        if row['state_before']=='slow' and wait['locked_cap'] is not None:
            assert abs(wait['cumulative_spent']-wait['opening_spent']-costs['watch'])<1e-8
        if row['action']=='expand':
            rec=row['decision_trace']['recovery']
            assert abs(costs['recovery']-rec['candidate_span_cost'])<1e-8
            assert row['net_gain']>=-1e-8
        remaining-=row['spent']
        assert abs(remaining-row['remaining'])<1e-8
    assert abs(out['result']['spent']-(out['config']['total_budget']-remaining))<1e-8

def metrics(out):
    return dict(reads=out['diagnostics']['body_reads'],spent=out['result']['spent'],
        expansions=sum(r['action']=='expand' for r in out['rounds']),
        final_directional=out['result']['supporting_evidence_count'],
        reasons=dict(Counter(r['decision_trace']['recovery']['reason'] for r in out['rounds'])))

def execute(output):
    output=output.resolve()
    if not output.is_relative_to(ROOT/'artifacts') or output.exists():
        raise ValueError('Use a new output directory under project artifacts')
    previous=ROOT/'artifacts/phase14-comparison-20261023'
    manifest=read(previous/'experiment-manifest.json')
    manifest['files']={k.replace(chr(92),'/'):v for k,v in manifest['files'].items()}
    inputs={};items=[]
    # Selection is fixed before opening documents: old focus plus first two sorted IDs.
    for market in MARKETS:
        dirs=list((ROOT/'artifacts').glob('semantic-v5-independent-*/inputs/tasks/'+market))
        assert len(dirs)==1,market
        td=dirs[0];base=td.parent.parent.parent
        paths=[td/'task.json',td/'forecast-documents.json',base/'runs'/market/'machine-annotations.json']
        for path in paths:
            relative=path.relative_to(ROOT).as_posix()
            expected=manifest['source_sha256'].get(relative,manifest['source_sha256'].get(str(path.relative_to(ROOT))))
            assert expected==sha(path),(path,'frozen input mismatch')
            inputs[relative]=expected
        items.append((market,paths))
    codes={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src').rglob('*.py'))}
    for p in (Path(__file__).resolve(),ROOT/'tests/test_patent_budget.py'):
        codes[p.relative_to(ROOT).as_posix()]=sha(p)
    for market in MARKETS:
        for mode in ('basic','enhanced'):
            p=previous/'runs'/market/mode/'derived_budget_full_band.json'
            assert manifest['files'][p.relative_to(previous).as_posix()]==sha(p)
            inputs[p.relative_to(ROOT).as_posix()]=sha(p)
    plan=dict(scope='previously_inspected_development_only',selection='prior_focus_plus_first_two_sorted_market_ids',
        markets=MARKETS,modes=['basic','enhanced'],new_runs=6,legacy_parity_runs=6,
        policy='patent_budget_v1',model_requests=0,label_access=False,
        source_sha256=inputs,code_sha256=codes)
    write(output/'execution-plan.json',plan)
    records=[]
    for market,paths in items:
        task,docs,annotations=map(read,paths)
        for mode in plan['modes']:
            old=read(previous/'runs'/market/mode/'derived_budget_full_band.json')
            cfg=Config.from_dict(old['config'])
            replay=run(task,docs,cfg,annotations,comparison_policy='typed_v6',recovery_policy='patent_full_band_v1')
            assert replay==old,(market,mode,'legacy drift')
            out=run(task,docs,cfg,annotations,comparison_policy='typed_v6',budget_policy='patent_budget_v1')
            check(out)
            write(output/'runs'/market/(mode+'.json'),out)
            records.append(dict(market=market,mode=mode,documents=len(docs),legacy_parity=True,
                before=metrics(old),after=metrics(out)))
    summary=dict(status='verified_development_budget_check',markets=MARKETS,
        documents=sum(len(read(paths[1])) for _,paths in items),new_runs=6,legacy_parity_runs=6,
        records=records,model_requests=0,independent_evaluation=False,empirical_calibration=False,
        claim='Budget semantics only; no prediction quality or monetary saving claim.',
        remaining_gaps=['Normalized grid allocation differs from paragraph 0205.',
            'Clock is fixed-cutoff archive simulation, not evidence-arrival replay.',
            'Source cost is an inclusive configured budget equivalent, not a measured invoice.',
            'Historical metadata-only exclusions do not prove semantic exposure of every indexed event.'])
    write(output/'summary.json',summary)
    for name,digest in inputs.items():assert sha(ROOT/name)==digest
    for name,digest in codes.items():assert sha(ROOT/name)==digest
    write(output/'experiment-manifest.json',dict(artifact_type='patent_budget_check',
        source_sha256=inputs,code_sha256=codes,
        files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    execute(parser.parse_args().output)
