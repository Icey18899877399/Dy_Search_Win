"""Verify saved run artifacts, code fingerprints, temporal gates and budget invariants."""
import hashlib
import importlib.util
import importlib
import types
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.cli import market_directory
from dynamic_retrieval.semantic import validate_model_annotation
from dynamic_retrieval.semantic_pipeline import _usage
from dynamic_retrieval.engine import iso, day


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_replay(manifest):
    """Load the recorded engine AND its relative dependencies in an isolated package.

    Materialized sources are verified copies under D: .runtime, never replacements
    for live code. A separate package name keeps historical imports out of the
    current application's module cache. No fallback to current unrecorded code.
    """
    records={}
    source_root=(ROOT/'src/dynamic_retrieval').resolve()
    for name,expected in manifest['code_sha256'].items():
        source=(ROOT/name).resolve()
        if not source.is_relative_to(source_root):continue
        relative=source.relative_to(source_root)
        if relative.suffix!='.py':continue
        if not source.is_file() or sha(source)!=expected:
            source=ROOT/'artifacts/code-archive'/(expected+'.py')
        assert source.is_file() and sha(source)==expected, (name,'historical replay source missing')
        records[relative.as_posix()]=(source,expected)
    assert 'engine.py' in records and 'models.py' in records
    signature=hashlib.sha256(json.dumps({k:v[1] for k,v in records.items()},sort_keys=True).encode()).hexdigest()
    package='_patent_history_'+signature
    directory=ROOT/'.runtime/verified-code'/signature
    directory.mkdir(parents=True,exist_ok=True)
    for name,(source,expected) in records.items():
        target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():target.write_bytes(source.read_bytes())
        assert sha(target)==expected, (target,'historical code copy changed')
    if package not in sys.modules:
        module=types.ModuleType(package);module.__path__=[str(directory)]
        module.__package__=package;sys.modules[package]=module
    engine=importlib.import_module(package+'.engine')
    models=importlib.import_module(package+'.models')
    return engine.run,models.Config


def verify_semantic(folder, manifest):
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('amendment'):
        amendment=read(folder/manifest['amendment']);backup=Path(amendment['original'])
        assert sha(backup/'manifest.json')==amendment['original_manifest_sha256']
        original=read(backup/'manifest.json');changes={c['path']:c for c in amendment['changes']}
        for name,digest in original['files'].items():
            assert sha(backup/name)==digest
            if name in changes:
                assert changes[name]['old_sha256']==digest and sha(folder/name)==changes[name]['new_sha256']
                assert name.endswith('/target-elements.json')
            else:assert sha(folder/name)==digest
        assert sha(ROOT/'scripts/amend_target_metadata.py')==amendment['correction_script_sha256']
    summary = read(folder/'summary.json')
    validator = validate_model_annotation
    semantic_hash = manifest['code_sha256']['src/dynamic_retrieval/semantic.py']
    if sha(ROOT/'src/dynamic_retrieval/semantic.py') != semantic_hash:
        archived = ROOT/'artifacts/code-archive'/(semantic_hash+'.py')
        assert sha(archived) == semantic_hash
        spec = importlib.util.spec_from_file_location('dynamic_retrieval.archived_semantic_'+semantic_hash, archived)
        historical = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(historical)
        validator = historical.validate_model_annotation
    assert summary['status'] == manifest['status']
    assert summary['human_reviewed'] is False and summary['official_outcomes_verified'] is False
    assert summary['source_budget_units'] == 'simulation'
    assert summary['selected_tasks'] == len(summary['tasks'])
    assert len({t['event_id'] for t in summary['tasks']}) == summary['selected_tasks']
    traces, completed_runs = [], 0
    for item in summary['tasks']:
        name = market_directory(item['market_id'])
        inputs = folder/'inputs/tasks'/name
        runs = folder/'runs'/name
        task = read(inputs/'task.json')
        targets = read(inputs/'target-elements.json')
        assert targets['target_elements']==task['target_elements'], (inputs,'target metadata mismatch')
        sampled = read(inputs/'sampled-documents.json')
        documents = read(inputs/'forecast-documents.json')
        annotations = read(runs/'machine-annotations.json')
        trace = read(runs/'extraction-trace.json')
        assert len(sampled) == item['sampled_documents'] == len(trace)
        assert len(documents) == item['validated_documents'] == len(annotations)
        assert item['failed_documents'] == len(sampled)-len(documents)
        assert {d['id'] for d in sampled} == {t['document_id'] for t in trace}
        assert {d['id'] for d in documents} == set(annotations) == {t['document_id'] for t in trace if t['status']=='validated'}
        sampled_by_id = {d['id']: d for d in sampled}
        for doc in documents:
            assert doc == sampled_by_id[doc['id']]
            validator(annotations[doc['id']], task, doc)
        assert item['llm_preprocessing'] == _usage(trace)
        traces.extend(trace)
        fingerprints = []
        for mode in ('fixed','basic','enhanced') if documents else ():
            result = read(runs/mode/'result.json')
            assert result['provenance']['annotations'] == annotations
            expected_inputs = [{k:d.get(k) for k in ('id','canonical_url','published_at','observed_at','source_file','source_id')}
                | {'body_sha256':hashlib.sha256(d.get('text','').encode('utf-8')).hexdigest()}
                for d in sorted(documents,key=lambda d:d['id'])]
            for record in expected_inputs:
                for clock in ('published_at','observed_at'):
                    record[clock] = iso(day(record[clock]))
            assert result['provenance']['inputs'] == expected_inputs
            assert result['diagnostics']['human_reviewed'] is False
            fingerprints.append((result['provenance']['input_sha256'],result['provenance']['annotation_sha256']))
            completed_runs += 1
        assert len(set(fingerprints)) == bool(documents)
        assert item['completed_runs'] == (3 if documents else 0)
        if documents:
            assert item['comparison']['verified_brier'] is None
    assert summary['llm_preprocessing'] == _usage(traces)
    assert summary['sampled_documents'] == summary['expected_calls'] == len(traces)
    assert summary['validated_documents'] == sum(t['validated_documents'] for t in summary['tasks'])
    assert summary['available_documents'] == sum(t['available_documents'] for t in summary['tasks'])
    assert summary['completed_runs'] == completed_runs == summary['completed_tasks']*3
    if summary['status'] == 'completed_semantic_experiment':
        assert summary['completed_tasks'] == summary['requested_tasks']
        assert summary['llm_preprocessing']['failed_documents'] == 0


def verify_observation_manifest(folder, manifest):
    """Verify measurement artifacts, including preserved pre-schema observations.

    This checks historical integrity, not publisher cost calibration or PIT validity.
    Final current measurements additionally use verify_phase14_observations.py.
    """
    def streamed_hash(path):
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        return digest.hexdigest()
    products=manifest.get('files',manifest.get('outputs',{}))
    assert 'summary.json' in products and 'query-observations.jsonl' in products
    for name,expected in products.items():
        target=(folder/name).resolve()
        assert target.is_relative_to(folder.resolve())
        assert streamed_hash(target)==expected,(target,'observation output changed')
    inputs=manifest.get('input_sha256')
    if inputs is None:inputs={str(ROOT/name):value for name,value in manifest.get('source_sha256',{}).items()}
    for name,expected in inputs.items():
        target=Path(name).resolve()
        assert target.is_relative_to(ROOT.resolve()),(target,'input outside project')
        if target.suffix=='.py' and (not target.is_file() or streamed_hash(target)!=expected):
            target=ROOT/'artifacts/code-archive'/(expected+'.py')
        assert streamed_hash(target)==expected,(target,'observation input changed')
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8-sig'))
    assert summary['empirical_calibration'] is False and summary['source_cost_parameters_replaceable'] is False
    assert summary['network_attempts']==0 and summary['label_reads']==0
    rows=[json.loads(line) for line in (folder/'query-observations.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==summary['measured_calls']
    assert all(r['backend']=='local_archive' and r['rate_limit_quota'] is None and r['empirical_calibration'] is False for r in rows)


def main():
    checked = []
    prepared = 0
    archived_checks = 0
    historical_semantic = []
    for path in sorted((ROOT / 'artifacts').rglob('manifest.json')):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        folder = path.parent
        if manifest.get('artifact_type')=='phase14_local_archive_observations' or (
            'files' not in manifest and 'input_sha256' in manifest and
            'query-observations.jsonl' in manifest.get('outputs',{}) and
            manifest.get('empirical_calibration') is False):
            verify_observation_manifest(folder,manifest)
            continue
        for filename, expected in manifest['files'].items():
            assert sha(folder / filename) == expected, (path, filename)
        for filename, expected in manifest['code_sha256'].items():
            current=ROOT/filename
            if not current.is_file() or sha(current)!=expected:
                archived=ROOT/'artifacts/code-archive'/(expected+'.py')
                assert archived.is_file() and sha(archived)==expected, (path, filename, 'missing original source')
                archived_checks+=1
        if manifest.get('artifact_type') == 'evaluation_bundle_preparation':
            from dynamic_retrieval.expansion import load_expansion,body_key
            from dynamic_retrieval.models import Config
            plan=json.loads((folder/'bundle-plan.json').read_text(encoding='utf-8'))
            assert plan['selection_uses_labels'] is False and plan['selection_uses_model_support'] is False
            event_ids=set();body_keys=set();url_keys=set();document_count=0
            for batch in plan['batches']:
                prepared_dir=Path(batch['prepared_cohort']).resolve()
                assert prepared_dir.is_relative_to(folder.resolve())
                assert sha(prepared_dir/'manifest.json')==batch['manifest_sha256']
                child=json.loads((prepared_dir/'plan.json').read_text(encoding='utf-8'))
                cohort,_=load_expansion(prepared_dir,batch['cutoff'],Config.from_dict(child['config']))
                assert len(cohort['selected'])==batch['events']
                assert sum(len(i['documents']) for i in cohort['selected'])==batch['documents']
                for item in cohort['selected']:
                    event=item['task']['event_id'];assert event not in event_ids
                    event_ids.add(event)
                    for doc in item['documents']:
                        key=body_key(doc);url=doc.get('canonical_url') or doc['id']
                        assert key not in body_keys and url not in url_keys
                        body_keys.add(key);url_keys.add(url);document_count+=1
            assert len(event_ids)==plan['retained_events'] and document_count==plan['documents']
            continue
        if manifest.get('artifact_type') == 'remediation_ablation':
            run,Config=historical_replay(manifest)
            from dynamic_retrieval.matching import validate_direction
            plan=json.loads((folder/'plan.json').read_text(encoding='utf-8'))
            report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
            source=Path(plan['source'])
            assert sha(source/'manifest.json')==plan['source_manifest_sha256']
            assert report['model_requests']==0 and report['independent_holdout_claim'] is False
            assert report['runs']==len(plan['tasks'])*12==len(report['rows'])
            for item in plan['tasks']:
                name=market_directory(item['market_id']);base=folder/'inputs'/name
                docs=json.loads((base/'documents.json').read_text(encoding='utf-8'))
                anns=json.loads((base/'annotations.json').read_text(encoding='utf-8'))
                task=json.loads((base/'task.json').read_text(encoding='utf-8'))
                for path_name,digest in item['files'].items():assert sha(folder/path_name)==digest
                for doc in docs:
                    validate_model_annotation(anns[doc['id']],task,doc);validate_direction(anns[doc['id']])
                fingerprints=set()
                for variant,flags in plan['variants'].items():
                    expected_task=dict(task)
                    expected_task.pop('matching_policy',None);expected_task.pop('scheduler_policy',None)
                    if flags[0]:expected_task['matching_policy']=plan.get('matching_policy','typed_v2')
                    if flags[1]:expected_task['scheduler_policy']='grid_credit_v2'
                    for mode in ('fixed','basic','enhanced'):
                        actual=json.loads((folder/'runs'/name/variant/mode/'result.json').read_text(encoding='utf-8'))
                        cfg=dict(item['config'],mode=mode)
                        expected=run(expected_task,docs,Config.from_dict(cfg),anns)
                        assert actual==expected,(name,variant,mode)
                        fingerprints.add((actual['provenance']['input_sha256'],actual['provenance']['annotation_sha256']))
                        row=next(r for r in report['rows'] if r['market_id']==item['market_id'] and r['variant']==variant and r['mode']==mode)
                        assert row['probabilities']==actual['result']['probabilities']
                        assert row['body_reads']==actual['diagnostics']['body_reads']
                        assert row['spent']==actual['result']['spent']
                assert len(fingerprints)==1
            continue
        if manifest.get('artifact_type') == 'expanded_preparation':
            from dynamic_retrieval.expansion import load_expansion, body_key, zone
            from dynamic_retrieval.models import Config
            from collections import Counter
            plan=json.loads((folder/'plan.json').read_text(encoding='utf-8'))
            cfg=Config.from_dict(plan['config'])
            cohort,_=load_expansion(folder,plan['cutoff'],cfg)
            assert len(cohort['selected'])==plan['retained_tasks']
            bodies=set();urls=set()
            for item in cohort['selected']:
                docs=item['documents'];task=item['task'];name=market_directory(task['market_id'])
                assert docs==json.loads((folder/'tasks'/name/'documents.json').read_text(encoding='utf-8'))
                assert task==json.loads((folder/'tasks'/name/'task.json').read_text(encoding='utf-8'))
                sources=Counter(d['source_id'] for d in docs)
                zones=Counter(zone(d,plan['cutoff'],cfg) for d in docs)
                assert 12<=len(docs)<=plan['target_documents_per_task']
                assert zones['window']>=4 and zones['window']+zones['band']>=8
                assert len(sources)>=3 and max(sources.values())<=plan['source_cap']
                assert task['event_id'] not in plan['excluded_events']
                assert plan['split']['assignments'][task['market_id']]==plan['split']['events'][task['event_id']]
                cutoff=datetime.fromisoformat(plan['cutoff'].replace('Z','+00:00'))
                for doc in docs:
                    key=body_key(doc);url=doc.get('canonical_url') or doc['id']
                    assert key not in bodies and url not in urls
                    bodies.add(key);urls.add(url)
                    assert all(datetime.fromisoformat(doc[k].replace('Z','+00:00'))<=cutoff for k in ('published_at','observed_at'))
            for original,expected in plan['historical_result_sha256'].items():
                assert sha(Path(original))==expected
            continue
        if manifest.get('artifact_type') == 'quality_evaluation':
            from dynamic_retrieval.quality_pipeline import verify_source
            from dynamic_retrieval.quality import validate_resolution, binary_metrics
            report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
            plan=json.loads((folder/'evaluation-plan.json').read_text(encoding='utf-8'))
            source=Path(manifest['source_experiment'])
            verify_source(source)
            assert sha(source/'manifest.json')==manifest['source_manifest_sha256']==plan['source_manifest_sha256']
            assert report['independent_holdout_claim'] is False
            if plan.get('pre_model_split_used'):
                assert sha(source/'inputs/pre-model-plan.json')==plan['pre_model_plan_sha256']
                pre=json.loads((source/'inputs/pre-model-plan.json').read_text(encoding='utf-8'))
                assert pre['split']==plan['split']
                assert not set(pre['excluded_events']) & {t['event_id'] for t in report['tasks']}
            assert report['llm_new_requests']==0
            assert len(report['tasks'])==report['requested_tasks']
            verified=0
            event_groups={}
            for item in report['tasks']:
                market=market_directory(item['market_id'])
                assert item['split']==plan['split']['assignments'][item['market_id']]
                event_groups.setdefault(item['event_id'],set()).add(item['split'])
                saved=json.loads((folder/'official'/(market+'.json')).read_text(encoding='utf-8'))
                assert saved['validated_label']==item['label']
                if item['label']['status']=='official_resolved':
                    task=json.loads((source/'inputs/tasks'/market/'task.json').read_text(encoding='utf-8'))
                    snap=saved['snapshot']
                    if item['label'].get('verification')=='official_api_terminal_winner_not_payout_audit':
                        from dynamic_retrieval.quality import validate_final_winner
                        assert plan['label_protocol']=='official_terminal_winner_v1_or_payout'
                        actual=validate_final_winner(task,snap['gamma'],snap['resolution'],snap['clob'],snap['fetched_at'],snap.get('event'))
                    else:actual=validate_resolution(task,snap['gamma'],snap['resolution'],snap['fetched_at'],snap.get('event'))
                    assert actual==item['label']
                    verified+=1
                for mode in ('fixed','basic','enhanced'):
                    original=json.loads((source/'runs'/market/mode/'result.json').read_text(encoding='utf-8'))
                    from dynamic_retrieval.quality import yes_probability
                    assert item['modes'][mode]['p_yes']==yes_probability(original)
            assert all(len(groups)==1 for groups in event_groups.values())
            assert verified==report['official_resolved_tasks']
            for partition in ('all','validation','test'):
                rows=[r for r in report['tasks'] if (partition=='all' or r['split']==partition) and r['label']['status']=='official_resolved']
                for mode in ('fixed','basic','enhanced','uniform_baseline'):
                    pairs=[(.5 if mode=='uniform_baseline' else r['modes'][mode]['p_yes'],int(r['label']['outcome']=='Yes')) for r in rows]
                    assert report['metrics'][partition][mode]==binary_metrics(pairs)
            continue
        if manifest.get('artifact_type') == 'semantic_pipeline':
            verify_semantic(folder, manifest)
            if sha(ROOT/'src/dynamic_retrieval/semantic.py') != manifest['code_sha256']['src/dynamic_retrieval/semantic.py']:
                historical_semantic.append(str(folder.relative_to(ROOT)))
            continue
        if manifest.get('artifact_type') == 'automatic_pipeline':
            summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
            assert summary['completed_tasks']==summary['requested_tasks']==len(summary['tasks']), path
            assert summary['completed_runs']==3*summary['completed_tasks'], path
            assert summary['human_reviewed'] is False and summary['official_outcomes_verified'] is False, path
            assert len({t['event_id'] for t in summary['tasks']})==summary['completed_tasks'], path
            for task in summary['tasks']:
                fingerprints=[]
                for mode in ('fixed','basic','enhanced'):
                    run=json.loads((folder/'runs'/market_directory(task['market_id'])/mode/'result.json').read_text(encoding='utf-8'))
                    fingerprints.append((run['provenance']['input_sha256'],run['provenance']['annotation_sha256']))
                    assert not run['provenance']['annotations'], path
                    assert run['task']['automatic_policy']==task['policy'], path
                    assert run['diagnostics']['human_reviewed'] is False, path
                assert len(set(fingerprints))==1, path
                assert task['comparison']['verified_brier'] is None, path
            continue
        if manifest.get('artifact_type') == 'experiment_preparation':
            cohort = json.loads((folder/'cohort.json').read_text(encoding='utf-8'))
            assert len({item['task']['event_id'] for item in cohort['selected']}) == cohort['completed'], path
            for item in cohort['selected']:
                taskdir = folder/item['directory']
                documents = json.loads((taskdir/'documents.json').read_text(encoding='utf-8'))
                annotations = json.loads((taskdir/'annotations.json').read_text(encoding='utf-8'))
                assert set(annotations) == {d['id'] for d in documents}, path
                assert all(a['reviewed'] is False and a['support']==[0,0] for a in annotations.values()), path
                cutoff = datetime.fromisoformat(item['task']['cutoff'].replace('Z','+00:00'))
                for doc in documents:
                    assert all(datetime.fromisoformat(doc[k].replace('Z','+00:00'))<=cutoff
                               for k in ('published_at','observed_at')), path
                    assert annotations[doc['id']]['body_sha256']==hashlib.sha256(doc['text'].encode('utf-8')).hexdigest(), path
                prepared += 1
            continue
        run = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        cutoff = datetime.fromisoformat(run['task']['cutoff'].replace('Z', '+00:00'))
        for doc in run['provenance']['inputs']:
            for field in ('published_at', 'observed_at'):
                assert datetime.fromisoformat(doc[field].replace('Z', '+00:00')) <= cutoff, (path, doc['id'], field)
        for field in ('inputs', 'annotations'):
            digest = hashlib.sha256(json.dumps(run['provenance'][field], ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
            key = 'input_sha256' if field == 'inputs' else 'annotation_sha256'
            assert digest == run['provenance'][key] == manifest[key], (path, key)
        assert run['diagnostics']['label_access'] is False, path
        assert abs(sum(run['result']['probabilities']) - 1) < 1e-8, path
        spent = sum(row['spent'] for row in run['rounds'])
        assert abs(spent - run['result']['spent']) < 1e-7, path
        assert spent <= run['config']['total_budget'] + 1e-7, path
        for row in run['rounds']:
            assert abs(sum(row['budget'].values()) - row['spent']) < 1e-7, path
        checked.append(str(folder.relative_to(ROOT)))
    assert checked, 'No saved runs found'
    pilot = json.loads((ROOT / 'artifacts/pilot/summary.json').read_text(encoding='utf-8'))
    assert pilot['completed'] == pilot['requested'] == len(pilot['tasks']), 'Incomplete pilot'
    for task in pilot['tasks']:
        assert task['verified_brier'] is None, 'Proxy promoted to verified outcome'
        fingerprints = []
        for mode in ('fixed', 'basic', 'enhanced'):
            run = json.loads((ROOT / 'artifacts/pilot' / market_directory(task['market_id']) / mode / 'result.json').read_text(encoding='utf-8'))
            fingerprints.append((run['provenance']['input_sha256'], run['provenance']['annotation_sha256']))
        assert len(set(fingerprints)) == 1, 'Comparison input differs across modes'
    print(json.dumps({'status': 'passed', 'verified_runs': len(checked), 'pilot_tasks': pilot['completed'],
                      'prepared_review_tasks': prepared,
                      'historical_source_checks_from_archive': archived_checks,
                      'semantic_runs_verified_under_historical_policy_only': historical_semantic,
                      'checks': ['artifact hashes', 'code hashes', 'input hashes', 'both cutoff clocks',
                                 'budget accounting', 'comparison input equality', 'proxy isolation']}, indent=2))


if __name__ == '__main__':
    main()
