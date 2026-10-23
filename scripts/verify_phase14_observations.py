"""Verify measured-query rows and hashes without treating timing as calibration."""
import argparse,hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def child(root,name):
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('Path outside root')
    return p

def verify(output):
    output=Path(output).resolve();m=read(output/'manifest.json')
    assert m['artifact_type']=='phase14_local_archive_observations'
    for name,h in m['files'].items():assert sha(child(output,name))==h,name
    for name,h in m['source_sha256'].items():assert sha(child(ROOT,name))==h,name
    for name,h in m['code_sha256'].items():
        p=child(ROOT,name)
        if not p.exists() or sha(p)!=h:p=ROOT/'artifacts/code-archive'/(h+'.py')
        assert sha(p)==h,name
    s=read(output/'summary.json');cohort=read(output/'cohort.json')
    rows=[json.loads(line) for line in (output/'query-observations.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==s['measured_calls']==486
    assert len(cohort)==18 and len({r['event_id'] for r in cohort})==18
    assert sum(len(r['source_ids']) for r in cohort)==s['task_source_pairs']==54
    groups=defaultdict(list)
    for r in rows:
        assert r['backend']=='local_archive' and r['measurement_kind']=='sqlite_metadata_query'
        assert r['latency_unit']=='seconds' and math.isfinite(r['response_latency_seconds']) and r['response_latency_seconds']>=0
        assert r['status']=='success' and type(r['returned_items']) is int and r['returned_items']>=0
        assert r['rate_limit_quota'] is None and r['quota_unit'] is None and r['empirical_calibration'] is False
        assert r['provenance']['index_sha256']==m['source_sha256']['artifacts/index.sqlite']
        groups[r['collection_id']].append(r)
    assert len(groups)==s['query_groups']==162
    for group in groups.values():
        assert sorted(r['repeat_index'] for r in group)==[1,2,3]
        assert len({r['result_sha256'] for r in group})==1
        assert all(r['scope']==group[0]['scope'] for r in group)
    assert len({r['observation_id'] for r in rows})==486
    assert len({r['source_id'] for r in rows})==s['source_ids']==39
    assert sum(r['returned_items'] for r in rows)==s['returned_items_across_repeated_calls']
    times=[r['response_latency_seconds'] for r in rows]
    for k,v in dict(min=min(times),median=statistics.median(times),max=max(times),total=sum(times)).items():
        assert v==s['latency_seconds'][k]
    assert s['network_attempts']==s['label_reads']==0
    assert s['empirical_calibration'] is False and s['source_cost_parameters_replaceable'] is False
    return dict(status='passed',measured_calls=486,query_groups=162,source_ids=39,
        stable_repeated_query_groups=162,quota_observations=0,empirical_calibration=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    print(json.dumps(verify(p.parse_args().output),ensure_ascii=False,indent=2))
