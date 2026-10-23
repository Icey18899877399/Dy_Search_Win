"""Recompute Phase14 totals and check full-band invariants and saved hashes."""
import argparse,json,math
from collections import Counter
from pathlib import Path
from verify_phase12 import ROOT,read,sha,child

def verify(output):
    output=Path(output).resolve();m=read(output/'experiment-manifest.json')
    assert m['artifact_type']=='phase14_comparison'
    for n,h in m['files'].items():assert sha(child(output,n))==h,n
    for n,h in m['source_sha256'].items():assert sha(child(ROOT,n))==h,n
    for n,h in m['code_sha256'].items():
        p=child(ROOT,n)
        if not p.exists() or sha(p)!=h:p=ROOT/'artifacts/code-archive'/(h+'.py')
        assert sha(p)==h,n
    from run_phase14_comparison import metrics
    s=read(output/'summary.json');assert len(s['records'])==s['runs']==180
    parity=0;expansions=0;totals={}
    for rec in s['records']:
        out=read(child(output,rec['path']));assert metrics(out)==rec['metrics']
        if rec['variant']=='legacy':
            old=read(ROOT/'artifacts/phase13-chain-20261023/baseline'/rec['market_id']/(rec['mode']+'.json'))
            assert old==out;parity+=1
        if rec['variant'].startswith('derived_budget'):
            assert out['config']['round_budget']==out['config']['total_budget']/out['config']['rounds']
        strict='full_band' in rec['variant']
        for r in out['rounds']:
            t=r['decision_trace'];recovery=t['recovery']
            assert r['remaining']>=0 and r['spent']>=0
            if strict and r['action']=='expand':
                expansions+=1
                from dynamic_retrieval.engine import day
                assert math.isclose(day(r['boundary_before'])-day(r['boundary_after']),out['config']['band_days'],abs_tol=1e-8)
                assert r['loss_ratio']>=out['config']['high_loss'] and r['net_gain']>=0
                assert recovery['candidate_width_days']==out['config']['band_days']
    for key,stored in s['totals'].items():
        mode,variant=key.split('/');rows=[r for r in s['records'] if r['mode']==mode and r['variant']==variant]
        reasons=Counter()
        for r in rows:reasons.update(r['metrics']['recovery_reasons'])
        actual=dict(runs=len(rows),**{k:sum(r['metrics'][k] for r in rows) for k in ('reads','spent','expansions','contraction_removals','final_directional')},recovery_reasons=dict(reasons))
        assert actual==stored
    assert parity==s['legacy_full_output_parity']==54
    assert s['independent_evaluation_completed'] is False and s['empirical_calibration'] is False
    return dict(status='passed',runs=180,full_legacy_output_parity=54,strict_full_band_expansions=expansions,
        files=len(m['files']),source_files=len(m['source_sha256']))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    print(json.dumps(verify(p.parse_args().output),ensure_ascii=False,indent=2))
