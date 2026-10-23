"""Behavior tests for local, frozen-input web runs."""
import http.client
import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from dynamic_retrieval.cli import save_run, write_json
from dynamic_retrieval.demo import demo_inputs, demo_result


class WebBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.result = demo_result()
        self.folder = self.root/'artifacts/sample/runs/synthetic-demo/enhanced'
        save_run(self.result, self.folder)
        task, docs, annotations = demo_inputs()
        inputs = self.root/'artifacts/sample/inputs/tasks/synthetic-demo'
        write_json(inputs/'documents.json', docs)
        write_json(inputs/'task.json', task)
        write_json(inputs/'annotations.json', annotations)
        write_json(self.root/'artifacts/sample/manifest.json',{'files':{'inputs/tasks/synthetic-demo/documents.json':hashlib.sha256((inputs/'documents.json').read_bytes()).hexdigest()}})
        (self.root/'web').mkdir()
        (self.root/'web/index.html').write_text('test', encoding='utf-8')
        (self.root/'web/module.mjs').write_text('export const x=1;',encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def catalog(self):
        from dynamic_retrieval.web_catalog import Catalog
        return Catalog(self.root)

    def test_catalog_excludes_corrupt_and_code_archive(self):
        write_json(self.root/'artifacts/invalid/result.json', {'task': {}})
        bad = self.root/'artifacts/broken/result.json'
        bad.parent.mkdir(); bad.write_text('{broken')
        save_run(self.result, self.root/'artifacts/code-archive/old/demo')
        catalog = self.catalog()
        rows = catalog.list()['runs']
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['replay_available'])
        self.assertEqual(rows[0]['id'], self.catalog().list()['runs'][0]['id'])
        self.assertEqual(catalog.get(rows[0]['id'])['run'], self.result)
        self.assertGreaterEqual(catalog.list()['rejected_count'], 2)

    def test_frozen_documents_fail_closed_when_body_changed(self):
        catalog = self.catalog(); ident = catalog.list()['runs'][0]['id']
        path = self.root/'artifacts/sample/inputs/tasks/synthetic-demo/documents.json'
        docs = json.loads(path.read_text()); docs[0]['text'] += ' mutated'
        write_json(path, docs)
        with self.assertRaises(ValueError):
            catalog.replay_inputs(ident)

    def test_config_boundaries(self):
        from dynamic_retrieval.web_jobs import validated_config
        for override in ({'cutoff':'2030'}, {'rounds':True}, {'rounds':100000}, {'total_budget':float('nan')}, {'admission':.9}):
            with self.assertRaises(ValueError): validated_config(self.result['config'],override)
        self.assertEqual(validated_config(self.result['config'], {'mode':'fixed'}).mode, 'fixed')

    def test_successful_job_replays_identically_and_is_idempotent(self):
        from dynamic_retrieval.web_jobs import JobManager
        catalog = self.catalog(); ident = catalog.list()['runs'][0]['id']
        manager = JobManager(self.root, catalog)
        try:
            job = manager.submit(ident, {}, 'test-once')
            self.assertEqual(job['id'], manager.submit(ident, {}, 'test-once')['id'])
            deadline = time.monotonic()+20
            while time.monotonic()<deadline and manager.get(job['id'])['status'] in ('queued','running'):
                time.sleep(.05)
            job = manager.get(job['id'])
            self.assertEqual(job['status'], 'completed', str(job)+' '+(self.root/'.runtime/web-jobs'/job['id']/'worker.log').read_text(encoding='utf-8'))
            output = self.root/'artifacts/web-runs'/job['id']
            actual=json.loads((output/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(actual['result'], self.result['result'])
            self.assertEqual(actual['rounds'], self.result['rounds'])
            self.assertEqual(actual['provenance'], self.result['provenance'])
            self.assertTrue((output/'manifest.json').is_file())
            self.assertTrue(job['result_id'])
            self.assertEqual(job['completed_rounds'],len(actual['rounds']))
            self.assertEqual(manager.progress(job['id'])['rounds'],actual['rounds'])
        finally: manager.close()

    def test_queued_cancel_and_restart_does_not_resume(self):
        from dynamic_retrieval.web_jobs import JobManager
        catalog = self.catalog(); ident=catalog.list()['runs'][0]['id']
        manager = JobManager(self.root,catalog,start=False)
        job=manager.submit(ident,{},'cancel-me')
        self.assertEqual(manager.cancel(job['id'])['status'],'cancelled')
        job2=manager.submit(ident,{},'restart-me'); manager.close()
        manager=JobManager(self.root,catalog,start=False)
        try:
            self.assertEqual(manager.get(job2['id'])['status'],'failed')
            self.assertEqual(manager.get(job2['id'])['stage'],'interrupted')
        finally: manager.close()

    def test_http_origin_token_export_and_traversal(self):
        from dynamic_retrieval.web_server import create_server
        server=create_server(self.root,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        host='127.0.0.1:'+str(server.server_port)
        def request(method,path,body=None,headers=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request(method,path,body,headers or {})
            response=connection.getresponse(); result=(response.status,response.read()); connection.close(); return result
        try:
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request('GET','/module.mjs')
            response=connection.getresponse()
            self.assertTrue(response.getheader('Content-Type').startswith('text/javascript'))
            response.read(); connection.close()
            status,body=request('GET','/api/catalog'); self.assertEqual(status,200)
            ident=json.loads(body)['runs'][0]['id']
            self.assertEqual(request('GET','/api/runs/'+ident+'/export')[0],200)
            self.assertEqual(request('GET','/../AGENTS.md')[0],404)
            self.assertEqual(request('GET','/api/catalog',headers={'Host':'evil.example'})[0],403)
            self.assertEqual(request('GET','/api/session',headers={'Origin':'https://evil.example'})[0],403)
            payload=json.dumps({'source_id':ident,'config':{},'idempotency_key':'http-test'})
            self.assertEqual(request('POST','/api/jobs',payload,{'Content-Type':'application/json'})[0],403)
            token=json.loads(request('GET','/api/session')[1])['token']
            headers={'Content-Type':'application/json','Origin':'http://'+host,'X-Run-Token':token}
            self.assertEqual(request('POST','/api/jobs',payload,headers)[0],202)
        finally:
            server.shutdown(); server.server_close(); server.jobs.close(); thread.join()

    def test_diagnostics_exposes_rejected_and_unread_without_mutation(self):
        from dynamic_retrieval.engine import run
        from dynamic_retrieval.models import Config
        task,docs,annotations=demo_inputs()
        result=run(task,docs,Config(initial_window_days=2,min_window_days=1,admission=.99,total_budget=2,round_budget=2,rounds=1),annotations)
        save_run(result,self.folder)
        before=(self.folder/'result.json').read_bytes()
        catalog=self.catalog(); ident=catalog.list()['runs'][0]['id']
        diagnostic=catalog.diagnostics_evidence(ident)
        self.assertEqual(diagnostic['origin'],'current_extraction_diagnostic_not_saved_prediction')
        self.assertEqual(len(diagnostic['evidence']),len(docs))
        self.assertTrue(any(not e['admitted'] for e in diagnostic['evidence']))
        self.assertTrue(any(not e['read_in_saved_run'] for e in diagnostic['evidence']))
        extra=next(e for e in diagnostic['evidence'] if not e['in_saved_evidence'])
        detail=catalog.evidence(ident,extra['id'])
        self.assertTrue(detail['full_text_available'])
        self.assertEqual((self.folder/'result.json').read_bytes(),before)

    def test_running_job_cancel_terminates_process(self):
        from dynamic_retrieval.web_jobs import JobManager
        catalog=self.catalog(); ident=catalog.list()['runs'][0]['id']
        manager=JobManager(self.root,catalog)
        try:
            job=manager.submit(ident,{'rounds':1000,'total_budget':100000},'running-cancel')
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                with manager.lock:
                    if manager.process is not None:
                        process=manager.process
                        manager.cancel(job['id'])
                        break
                time.sleep(.001)
            else: self.fail('Worker process was never observed')
            process.wait(timeout=10)
            self.assertEqual(manager.get(job['id'])['status'],'cancelled')
            self.assertIsNotNone(process.returncode)
        finally: manager.close()

    def test_saved_result_hash_mismatch_is_rejected(self):
        changed=dict(self.result)
        changed['result']=dict(self.result['result'],probabilities=[.99,.01])
        write_json(self.folder/'result.json',changed)
        catalog=self.catalog()
        self.assertEqual(catalog.list()['runs'],[])
        self.assertEqual(catalog.list()['rejected_count'],1)

    def test_title_change_rejects_frozen_corpus(self):
        catalog=self.catalog(); ident=catalog.list()['runs'][0]['id']
        path=self.root/'artifacts/sample/inputs/tasks/synthetic-demo/documents.json'
        docs=json.loads(path.read_text()); docs[0]['title']+=' changed'
        write_json(path,docs)
        with self.assertRaises(ValueError): catalog.replay_inputs(ident)

    def test_cancel_after_round_keeps_partial_trace(self):
        from dynamic_retrieval.web_jobs import JobManager
        result=dict(self.result)
        result['config']=dict(result['config'],rounds=1000,total_budget=100000,confirmation_rounds=100000,source_confirmation_rounds=100000)
        save_run(result,self.folder)
        catalog=self.catalog(); manager=JobManager(self.root,catalog)
        try:
            job=manager.submit(catalog.list()['runs'][0]['id'],{},'partial-cancel')
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if manager.get(job['id']).get('completed_rounds',0)>0:
                    manager.cancel(job['id']); break
                time.sleep(.001)
            else: self.fail('No real completed round was reported')
            progress=manager.progress(job['id'])
            self.assertTrue(progress['trace_only'])
            self.assertGreater(len(progress['rounds']),0)
            self.assertEqual(manager.get(job['id'])['status'],'cancelled')
        finally: manager.close()


    def test_partial_trace_available_before_atomic_snapshot(self):
        from dynamic_retrieval.web_jobs import JobManager
        catalog=self.catalog(); manager=JobManager(self.root,catalog,start=False)
        try:
            job=manager.submit(catalog.list()['runs'][0]['id'],{},'trace-before-snapshot')
            trace=self.root/'.runtime/web-jobs'/job['id']/'rounds.jsonl'
            trace.write_text(json.dumps({'round':1})+'\n'+ '{incomplete',encoding='utf-8')
            manager.cancel(job['id'])
            status=manager.get(job['id'])
            self.assertTrue(status['partial_trace_available'])
            self.assertEqual(status['completed_rounds'],1)
            self.assertEqual(manager.progress(job['id'])['rounds'],[{'round':1}])
        finally: manager.close()

