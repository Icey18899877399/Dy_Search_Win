"""Verify Phase 12 hashes and recompute aggregate claims from saved run records."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def child(root,name):
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('Path escapes artifact root')
    return p

def verify(output):
    output=Path(output).resolve();manifest=read(output/'experiment-manifest.json')
    assert manifest['artifact_type']=='phase12_development'
    for name,digest in manifest['files'].items():assert sha(child(output,name))==digest,name
    for name,digest in manifest['source_sha256'].items():assert sha(child(ROOT,name))==digest,name
    for name,digest in manifest['code_sha256'].items():
        current=child(ROOT,name)
        if not current.exists() or sha(current)!=digest:current=ROOT/'artifacts/code-archive'/(digest+'.py')
        assert sha(current)==digest,name
    summary=read(output/'summary.json');plan=read(output/'execution-plan.json')
    records=summary['records'];network=cache=0
    totals={v:{k:0 for k in ('body_reads','admitted','directional_admitted','directional_final','simulated_spent','changed_prediction_runs_vs_v5')} for v in plan['ablations']}
    for record in records:
        folder=output/'runs'/record['market_id']/record['mode']
        baseline=read(folder/'v5_legacy.json');lazy=read(folder/'on-demand-cache.json')
        assert all(lazy[k]==baseline[k] for k in ('result','rounds','evidence'))
        assert record['lazy_shared_parity'] is True
        calls=lazy['diagnostics']['model_calls']
        assert all(e['kind']=='cache_read' for e in calls['events'])
        assert calls['network_attempts']==0 and calls['actual_usage']['total_tokens']==0
        assert calls['cache_hits']==sum(e['outcome']=='success' for e in calls['events'])
        assert {k:v for k,v in calls.items() if k!='events'}==record['lazy_calls']
        durable=[json.loads(line) for line in (folder/'cache-attempts.jsonl').read_text().splitlines()]
        assert durable==calls['events']
        network+=calls['network_attempts'];cache+=calls['cache_hits']
        for variant in plan['ablations']:
            run=read(folder/(variant+'.json'));actual=record['variants'][variant]
            assert actual['probabilities']==run['result']['probabilities']
            assert actual['body_reads']==sum(r['body_reads'] for r in run['rounds'])
            assert actual['admitted']==len(run['evidence'])
            assert actual['directional_admitted']==sum(any(e['support']) for e in run['evidence'])
            assert actual['directional_final']==sum(any(e['support']) and e['in_final_window'] for e in run['evidence'])
            assert actual['simulated_spent']==run['result']['spent']
            for key in totals[variant]:
                totals[variant][key]+=(actual['probabilities']!=record['variants']['v5_legacy']['probabilities']) if key=='changed_prediction_runs_vs_v5' else actual[key]
    # Match Python's compensated sum used by the producer, after each
    # individual serialized expenditure has been checked against its run.
    for variant in plan['ablations']:
        totals[variant]['simulated_spent']=sum(r['variants'][variant]['simulated_spent'] for r in records)
    assert totals==summary['totals']
    assert network==summary['external_network_attempts']==0
    assert cache==summary['cache_hits']
    assert len(records)==summary['on_demand_runs']==summary['on_demand_parity_runs']
    assert len(records)*len(plan['ablations'])==summary['ablation_runs']
    assert len({r['event_id'] for r in records})==summary['events']==plan['task_count']
    assert summary['monetary_savings_verified'] is False and summary['accuracy_improvement_verified'] is False
    return dict(status='passed',files=len(manifest['files']),source_files=len(manifest['source_sha256']),
        events=summary['events'],ablation_runs=summary['ablation_runs'],on_demand_parity_runs=len(records),
        network_attempts=network,cache_hits=cache)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    print(json.dumps(verify(parser.parse_args().output),ensure_ascii=False))
