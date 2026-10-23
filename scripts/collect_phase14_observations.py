"""Collect genuine local archive observations on the frozen 18 development tasks.

No model, external API, outcome labels, quota imputation or cost normalization.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.observation_collection import (
    ArchiveQueries, audit_telemetry, collect_query, file_sha256, prepare_output, select_sources)

RAW=Path(r'D:\agents-main\agents\polymarket\data')


def collection_status(rows):
    successes=sum(row['status']=='success' for row in rows)
    if rows and successes==len(rows):return 'completed_local_archive_measurements'
    return 'partial_local_archive_measurements' if successes else 'failed_local_archive_measurements'


def execute(output, *, project_root=ROOT, raw_root=RAW):
    root=Path(project_root).resolve()
    output=prepare_output(output,project_root=root,raw_root=raw_root)
    def write(name,value):
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    started=datetime.now(timezone.utc).isoformat()
    index=root/'artifacts'/'index.sqlite'
    hashes={str(index):file_sha256(index)}
    for path in (Path(__file__),ROOT/'src/dynamic_retrieval/observation_collection.py'):
        hashes[str(path.resolve())]=file_sha256(path)
    tasks=[]
    for batch in sorted((root/'artifacts').glob('semantic-v5-independent-*')):
        for path in sorted((batch/'inputs'/'tasks').glob('*/task.json')):
            docpath=path.parent/'forecast-documents.json'
            task=json.loads(path.read_text(encoding='utf-8-sig'))
            docs=json.loads(docpath.read_text(encoding='utf-8-sig'))
            for p in (path,docpath):hashes[str(p)]=file_sha256(p)
            sources=select_sources(docs)
            tasks.append((task,sources,path,docpath,len(docs)))
    if len(tasks)!=18 or len({t[0]['market_id'] for t in tasks})!=18:
        raise ValueError('Requires the exact 18 previously inspected development tasks')
    historical=audit_telemetry(raw_root)
    write('historical-telemetry-audit.json',historical)
    measurements=[];cohort=[];windows=[7,14,30];repeats=3
    with ArchiveQueries(index) as archive:
        for task,sources,path,docpath,count in tasks:
            cohort.append(dict(market_id=task['market_id'],event_id=task['event_id'],cutoff=task['cutoff'],
                source_ids=sources,source_selection_rule='first_three_SHA256_UTF8_source_id_ascending',frozen_documents=count,task_file=str(path),task_sha256=hashes[str(path)],
                source_selection_file=str(docpath),source_selection_sha256=hashes[str(docpath)]))
            for source in sources:
                for days in windows:
                    scope=dict(market_id=str(task['market_id']),event_id=str(task['event_id']),
                        cutoff=task['cutoff'],source_id=source,window_days=days)
                    provenance=dict(index_file=str(index),index_sha256=hashes[str(index)],
                        task_file=str(path),task_sha256=hashes[str(path)],
                        source_selection_file=str(docpath),source_selection_sha256=hashes[str(docpath)],
                        query_implementation=str(ROOT/'src/dynamic_retrieval/observation_collection.py'),
                        query_implementation_sha256=hashes[str(ROOT/'src/dynamic_retrieval/observation_collection.py')],
                        timing_scope='SQLite source/event/window metadata query and row materialization; excludes hash serialization, setup and body decompression',
                        database_open_mode='ro',time_policy='latest usable version by observed_at/id under published_at and observed_at <= cutoff, then source and inclusive publication window')
                    measurements.extend(collect_query(lambda:archive.query(scope),scope=scope,
                        provenance=provenance,repeats=repeats))
            print('Measured development task',task['market_id'],'sources',len(sources),flush=True)
    with (output/'query-observations.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for row in measurements:stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    write('cohort.json',cohort)
    grouped=defaultdict(list)
    for row in measurements:grouped[row['source_id']].append(row)
    source_summary=[]
    for source,rows in sorted(grouped.items()):
        success=[r for r in rows if r['status']=='success'];times=[r['response_latency_seconds'] for r in success]
        source_summary.append(dict(source_id=source,backend='local_archive',calls=len(rows),successful_calls=len(success),
            failed_calls=len(rows)-len(success),median_latency_seconds=statistics.median(times) if times else None,
            mean_latency_seconds=statistics.mean(times) if times else None,
            returned_items_across_repeated_calls=sum(r['returned_items'] for r in success),
            rate_limit_quota=None,quota_unit=None,empirical_calibration=False))
    write('source-descriptive-summary.json',source_summary)
    for path,digest in hashes.items():
        if file_sha256(path)!=digest:raise RuntimeError('An input changed during collection: '+path)
    successes=[r for r in measurements if r['status']=='success']
    times=[r['response_latency_seconds'] for r in successes]
    independent_groups=defaultdict(list)
    for r in measurements:independent_groups[r['collection_id']].append(r)
    stable=sum(len({r['result_sha256'] for r in rs if r['status']=='success'})==1 and
        all(r['status']=='success' for r in rs) for rs in independent_groups.values())
    summary=dict(status=collection_status(measurements),started_at=started,
        ended_at=datetime.now(timezone.utc).isoformat(),development_tasks=len(tasks),
        unique_event_ids=len({t[0]['event_id'] for t in tasks}),frozen_documents=sum(t[4] for t in tasks),
        source_ids=len(grouped),task_source_pairs=sum(len(t[1]) for t in tasks),window_days=windows,
        source_selection_rule='first_three_SHA256_UTF8_source_id_ascending_per_frozen_task',maximum_query_calls=486,
        repeats_per_query=repeats,query_groups=len(independent_groups),measured_calls=len(measurements),
        successful_calls=len(successes),failed_calls=len(measurements)-len(successes),
        repeat_groups_with_identical_return_hashes=stable,
        zero_return_calls=sum(r['returned_items']==0 for r in successes),
        nonzero_return_calls=sum(r['returned_items']>0 for r in successes),
        returned_items_across_repeated_calls=sum(r['returned_items'] for r in successes),
        latency_seconds=dict(min=min(times) if times else None,median=statistics.median(times) if times else None,
            max=max(times) if times else None,total=sum(times)),
        observations_with_quota=0,historical_verified_request_observations=historical['verified_request_observations'],
        historical_file_statuses={Path(r['path']).name:r['status'] for r in historical['files']},
        backend='local_archive',network_attempts=0,label_reads=0,empirical_calibration=False,
        source_cost_calibration_status='underidentified_missing_publisher_latency_and_rate_quota',
        incubation_calibration_status='underidentified_missing_independent_event_occurrence_pairs',
        defaults_changed=False,source_cost_parameters_replaceable=False,source_inputs_unchanged=True,
        limitations=['Development contexts already inspected; not independent evaluation.',
            'Local SQLite metadata latency is measured now, not historical publisher/network response time.',
            'Sources are selected only from frozen development document sets; other archive sources are outside scope.',
            'Returned counts cover unique eligible archived records, not newly fetched publisher articles.',
            'Repeated queries share OS/SQLite cache; no cold-cache equivalence or representative load claim.',
            'Counts summed across repeats/windows overlap and must not be called unique documents.',
            'Unknown rate limit quotas remain null; patent three-component costs cannot be normalized.',
            'No observed event occurrence timestamps were established; no incubation band fitted.'])
    write('summary.json',summary)
    products=['query-observations.jsonl','cohort.json','historical-telemetry-audit.json',
              'source-descriptive-summary.json','summary.json']
    write('manifest.json',dict(status='complete' if summary['status']=='completed_local_archive_measurements' else 'collection_completed_with_failures',
        artifact_type='phase14_local_archive_observations',
        code_sha256={Path(p).relative_to(root).as_posix():h for p,h in hashes.items() if p.endswith('.py')},
        source_sha256={Path(p).relative_to(root).as_posix():h for p,h in hashes.items() if not p.endswith('.py')},
        files={name:file_sha256(output/name) for name in products},input_sha256=hashes,
        outputs={name:file_sha256(output/name) for name in products},
        source_input_verification='all input hashes rechecked after measurement',
        query_count=len(measurements),empirical_calibration=False))
    print(json.dumps({k:summary[k] for k in ('status','development_tasks','source_ids','task_source_pairs',
        'query_groups','measured_calls','successful_calls','failed_calls','latency_seconds','historical_file_statuses')},ensure_ascii=True))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/phase14-observations-20261023')
    args=parser.parse_args()
    execute(args.output)

