"""Real collection contract: unit correctness, unknowns, repeat isolation and write safety."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

class ObservationCollectionTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dynamic_retrieval.observation_collection'),
                             'real observation collector must exist')
        from dynamic_retrieval import observation_collection
        return observation_collection

    def scope(self):
        return dict(event_id='event-1', market_id='market-1', source_id='publisher.example',
                    cutoff='2026-01-10T00:00:00Z', window_days=7)

    def test_seconds_return_counts_unknown_quota_and_repeat_isolation(self):
        mod=self.module()
        calls=[]
        def query():
            time.sleep(.003)
            calls.append(1)
            return [{'id':'d1'}, {'id':'d2'}]
        rows=mod.collect_query(query, scope=self.scope(), provenance={'index_sha256':'a'*64}, repeats=3)
        self.assertEqual(len(calls),3)
        self.assertEqual([r['repeat_index'] for r in rows],[1,2,3])
        self.assertEqual(len({r['observation_id'] for r in rows}),3)
        for r in rows:
            self.assertEqual(r['returned_items'],2)
            self.assertGreaterEqual(r['response_latency_seconds'],.002)
            self.assertLess(r['response_latency_seconds'],5)
            self.assertEqual(r['backend'],'local_archive')
            self.assertIsNone(r['rate_limit_quota'])
            self.assertIsNone(r['quota_unit'])
            self.assertEqual(r['latency_unit'],'seconds')
            self.assertFalse(r['empirical_calibration'])
            self.assertTrue(r['started_at'].endswith('+00:00'))
        rows[0]['provenance']['index_sha256']='changed'
        self.assertEqual(rows[1]['provenance']['index_sha256'],'a'*64)

    def test_failed_calls_retained_without_secret_error_text_and_following_repeat_runs(self):
        mod=self.module(); attempts=[]
        def query():
            attempts.append(1)
            if len(attempts)==1: raise RuntimeError('secret-token-content')
            return []
        rows=mod.collect_query(query,scope=self.scope(),provenance={'file':'fixture'},repeats=2)
        self.assertEqual([r['status'] for r in rows],['failed','success'])
        self.assertIsNone(rows[0]['returned_items'])
        self.assertEqual(rows[0]['error_type'],'RuntimeError')
        self.assertNotIn('secret-token-content',json.dumps(rows))
        self.assertEqual(rows[1]['returned_items'],0)

    def test_invalid_scope_repeat_or_provenance_never_invokes_query(self):
        mod=self.module()
        def query(): self.fail('invalid collection invoked backend')
        for change in ({'repeats':0},{'repeats':True},{'provenance':{}},
                       {'scope':dict(self.scope(),cutoff='2026-01-10')},
                       {'scope':dict(self.scope(),window_days=-1)}):
            args=dict(scope=self.scope(),provenance={'file':'fixture'},repeats=1);args.update(change)
            with self.assertRaises(ValueError): mod.collect_query(query,**args)

    def test_readonly_source_window_query_excludes_future_failed_and_other_source(self):
        mod=self.module()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'index.sqlite';db=sqlite3.connect(path)
            db.execute('CREATE TABLE documents(id TEXT, canonical_url TEXT, source_id TEXT, published_at TEXT, observed_at TEXT, content_hash TEXT,event_id TEXT, source_file TEXT,scrape_status TEXT,has_text INTEGER)')
            records=[('a','u1','publisher.example','2026-01-05','2026-01-06','ok'),
                     ('b','u2','other','2026-01-05','2026-01-06','ok'),
                     ('c','u3','publisher.example','2026-01-09','2026-01-11','ok'),
                     ('d','u4','publisher.example','2026-01-01','2026-01-01','ok'),
                     ('e','u5','publisher.example','2026-01-05','2026-01-06','failed'),
                     ('old-window','u6','publisher.example','2026-01-05','2026-01-06','ok'),
                     ('latest-window','u6','publisher.example','2026-01-01','2026-01-08','ok'),
                     ('old-source','u7','publisher.example','2026-01-05','2026-01-06','ok'),
                     ('latest-source','u7','other','2026-01-05','2026-01-08','ok')]
            for ident,url,source,pub,obs,status in records:
                db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)',(ident,url,source,pub+'T00:00:00.000000Z',obs+'T00:00:00.000000Z','hash','event-1','raw/file.json',status,1))
            db.commit();db.close()
            with mod.ArchiveQueries(path) as archive:
                rows=archive.query(self.scope())
                self.assertEqual([r['id'] for r in rows],['a'])
                with self.assertRaises(sqlite3.OperationalError): archive.connection.execute('DELETE FROM documents')

    def test_output_refuses_raw_path_nonempty_and_escaping_project(self):
        mod=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); project=root/'project'; raw=root/'raw'
            (project/'artifacts'/'existing').mkdir(parents=True);raw.mkdir()
            old=project/'artifacts'/'existing'/'keep.txt';old.write_text('preserve')
            for dest in (raw/'output',project/'artifacts'/'existing',root/'outside',project/'artifacts'):
                with self.assertRaises(ValueError): mod.prepare_output(dest,project_root=project,raw_root=raw)
            target=mod.prepare_output(project/'artifacts'/'new',project_root=project,raw_root=raw)
            self.assertTrue(target.is_dir());self.assertEqual(old.read_text(),'preserve')

    def test_audit_reports_schema_provenance_and_does_not_invent_telemetry(self):
        mod=self.module()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'run_log.json').write_text('[{"date":"2026-01-01","events":2,"news_count":5}]')
            (root/'daily_run.log').write_text('2026-01-01 INFO completed count=5\n')
            (root/'error.log').write_text('secret-token-value\n')
            report=mod.audit_telemetry(root)
            self.assertFalse(report['empirical_calibration'])
            self.assertEqual(len(report['files']),3)
            row=report['files'][0]
            self.assertEqual(row['status'],'readable')
            self.assertEqual(len(row['sha256']),64)
            self.assertIn('news_count',row['available_fields'])
            self.assertEqual(row['line_count'],1)
            self.assertNotIn('secret-token-value',json.dumps(report))
            self.assertIn('rate_limit_quota',report['unverified_required_fields'])

    def test_audit_missing_files_are_not_claimed_inspected(self):
        mod=self.module()
        with tempfile.TemporaryDirectory() as folder:
            report=mod.audit_telemetry(Path(folder))
            self.assertEqual([r['status'] for r in report['files']],['missing']*3)
            self.assertEqual(report['verified_request_observations'],0)

    def test_script_refuses_nonempty_output_before_reading_input(self):
        path=Path(__file__).resolve().parents[1]/'scripts'/'collect_phase14_observations.py'
        self.assertTrue(path.exists(),'observation collection script must exist')
        spec=importlib.util.spec_from_file_location('phase14_collection_script',path)
        script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'artifacts'/'occupied';output.mkdir(parents=True)
            old=output/'keep.json';old.write_text('preserve')
            with self.assertRaises(ValueError):script.execute(output,project_root=root,raw_root=root/'raw')
            self.assertEqual(old.read_text(),'preserve')

    def test_bounded_source_selection_depends_only_on_stable_source_id(self):
        mod=self.module()
        self.assertTrue(hasattr(mod,'select_sources'),'bounded source selection required')
        docs=[{'source_id':name,'text':'ignored'} for name in ('d','b','c','a','e')]
        chosen=mod.select_sources(docs)
        self.assertEqual(len(chosen),3)
        self.assertEqual(chosen,mod.select_sources(list(reversed(docs))+docs))
        self.assertEqual(chosen,mod.select_sources([{'source_id':r['source_id'],'text':'changed'} for r in docs]))
        self.assertEqual(mod.select_sources([{'source_id':'only'}]),['only'])
        self.assertEqual(len(docs),5)


    def test_script_completion_status_distinguishes_failures(self):
        path=Path(__file__).resolve().parents[1]/'scripts'/'collect_phase14_observations.py'
        spec=importlib.util.spec_from_file_location('phase14_status_script',path)
        script=importlib.util.module_from_spec(spec);spec.loader.exec_module(script)
        self.assertTrue(hasattr(script,'collection_status'),'measurement failure status must be explicit')
        self.assertEqual(script.collection_status([{'status':'success'}]),'completed_local_archive_measurements')
        self.assertEqual(script.collection_status([{'status':'failed'}]),'failed_local_archive_measurements')
        self.assertEqual(script.collection_status([{'status':'failed'},{'status':'success'}]),'partial_local_archive_measurements')
        self.assertEqual(script.collection_status([]),'failed_local_archive_measurements')
