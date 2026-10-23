"""Verify Phase 13 frozen outputs, baseline equality, trace arithmetic and indexes."""
import argparse,json
from pathlib import Path
from verify_phase12 import ROOT,sha,read,child

def verify(output):
    output=Path(output).resolve();manifest=read(output/'experiment-manifest.json')
    assert manifest['artifact_type']=='phase13_chain'
    for name,digest in manifest['files'].items(): assert sha(child(output,name))==digest,name
    for name,digest in manifest['source_sha256'].items(): assert sha(child(ROOT,name))==digest,name
    for name,digest in manifest['code_sha256'].items():
        p=child(ROOT,name)
        if not p.exists() or sha(p)!=digest: p=ROOT/'artifacts/code-archive'/(digest+'.py')
        assert sha(p)==digest,name
    from run_phase13_chain import original_shape,metrics
    summary=read(output/'summary.json')
    assert len(summary['records'])==summary['full_output_parity_runs']==54
    assert len(summary['experiments'])==18
    for record in summary['records']+summary['experiments']:
        result=read(child(output,record['path']))
        assert metrics(result)==record['metrics']
        if 'market_id' in record:
            old=read(ROOT/'artifacts/phase12-development-20261023/runs'/record['market_id']/record['mode']/'v6_admission.json')
            assert original_shape(result)==old
        for r in result['rounds']:
            t=r['decision_trace'];obs=t['loss_observation'];adj=t['boundary_adjustment']
            assert abs(sum(x['contribution'] for x in obs['band_evidence'])-obs['loss'])<1e-10
            assert sorted(set(r['window_ids'])-set(obs['window_ids']))==adj['entered_ids']
            assert sorted(set(obs['window_ids'])-set(r['window_ids']))==adj['removed_ids']
            assert t['recovery']['executed']==(r['action']=='expand')
            assert r['spent']>=0 and r['remaining']>=0
    focus=read(output/'baseline/2354063/enhanced.json')['rounds'][16]['decision_trace']['recovery']
    assert focus['reason']=='insufficient_recovery_budget' and focus['candidate_width_days']==0
    basic=read(output/'baseline/2354063/basic.json')['rounds']
    assert basic[0]['action']=='expand' and basic[1]['decision_trace']['boundary_adjustment']['removed_ids']
    assert not summary['empirical_calibration'] and not summary['accuracy_improvement_verified']
    return dict(status='passed',baseline_full_output_parity=54,sensitivity_runs=16,runtime_demo_runs=2,
        files=len(manifest['files']),source_files=len(manifest['source_sha256']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    print(json.dumps(verify(p.parse_args().output),ensure_ascii=False,indent=2))
