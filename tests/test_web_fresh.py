import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from dynamic_retrieval.cli import write_json
from dynamic_retrieval.data.store import Store,build_index
from test_semantic_pipeline import FakeClient,CUTOFF
import test_semantic_pipeline as fixtures

class FreshTests(unittest.TestCase):
    def fixture(self,root):
        data=root/'data';data.mkdir()
        articles=[]
        for i in range(20):
            articles.append(dict(title='Alice campaign '+str(i),source='Paper'+str(i%7),url='https://example.test/'+str(i),
                full_text='Alice Smith announced her candidacy for the Republican presidential nomination. Evidence '+str(i)+'. '+'Reported details. '*20,
                published_at=('2026-05-10' if i<10 else '2026-04-25' if i<16 else '2026-03-20')+'T00:00:00Z',scrape_status='success'))
        obj=dict(collected_at='2026-05-15T00:00:00Z',scraped_at='2026-05-15T00:00:00Z',events=[dict(event_id='e0',markets=[dict(market_id='m0',
            question='Will Alice Smith win the 2028 Republican presidential nomination?',description='Nomination outcome',
            outcomes=['Yes','No'],active=True,closed=False,end_date='2028-11-07T00:00:00Z')],articles=articles)])
        write_json(data/'batch.json',obj);build_index(data,root/'artifacts/index.sqlite')
        return data

    def service(self,root,data):
        from dynamic_retrieval.web_fresh import FreshService
        return FreshService(root,data_root=data)

    def test_preview_no_model_no_label_and_frozen_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.fixture(root);s=self.service(root,data)
            with patch.object(Store,'labels',side_effect=AssertionError('label leakage')):
                p=s.preview(dict(cutoff='2026-05-15T23:59:59Z',count=2,max_documents=20,config={}))
            self.assertEqual(p['retained_count'],1);self.assertEqual(p['model_request_upper_bound'],20)
            payload=s.freeze(p['preview_id'],['m0'],root/'job')
            self.assertTrue(Path(payload['prepared_cohort']).is_dir())
            self.assertEqual(payload['matching_policy'],'typed_v5')
            with self.assertRaises(ValueError):s.freeze(p['preview_id'],['other'],root/'bad')

    def test_preview_limits_timezone_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.fixture(root);s=self.service(root,data)
            for kwargs in ({'cutoff':'2026-05-15'},{'count':True},{'count':21},{'max_documents':100},{'api_key':'not-allowed'}):
                with self.assertRaises(ValueError):s.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,config={})|kwargs)
            p=s.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,config={}))
            folder=root/'.runtime/fresh-previews'/p['preview_id']
            (folder/'cohort.json').write_text('{}')
            with self.assertRaises(ValueError):s.freeze(p['preview_id'],['m0'],root/'bad')

    def test_job_missing_key_and_idempotency_secret_not_persisted(self):
        from dynamic_retrieval.web_jobs import JobManager
        from dynamic_retrieval.web_catalog import Catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.fixture(root);s=self.service(root,data)
            p=s.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,config={}))
            manager=JobManager(root,Catalog(root),start=False);manager.fresh=s
            try:
                with patch.dict(os.environ,{},clear=True):
                    with self.assertRaises(ValueError):manager.submit_fresh(p['preview_id'],['m0'],'one')
                with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'SENTINEL-NEVER-PERSIST'}):
                    job=manager.submit_fresh(p['preview_id'],['m0'],'one')
                    self.assertEqual(job['id'],manager.submit_fresh(p['preview_id'],['m0'],'one')['id'])
                    with self.assertRaises(ValueError):manager.submit_fresh(p['preview_id'],[],'one')
                manager.cancel(job['id'])
                for path in (root/'.runtime').rglob('*.json'):
                    self.assertNotIn('SENTINEL-NEVER-PERSIST',path.read_text(encoding='utf-8'))
            finally:manager.close()

    def test_semantic_progress_and_v4_frozen_before_requests(self):
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=fixtures.SemanticPipelineTests().fixture(root)
            events=[]
            with Store(db) as store:
                summary=run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,max_documents=4,
                    client=FakeClient(fail=True),cache=root/'cache',repair_policies=True,matching_policy='typed_v4',observer=events.append)
            self.assertEqual(summary['validated_documents'],3)
            self.assertTrue(any(e.get('completed_documents')==4 for e in events))
            self.assertEqual(events[-1]['completed_runs'],3)
            t=json.loads((root/'out/inputs/effective-tasks.json').read_text())
            self.assertEqual(t[0]['matching_policy'],'typed_v4')
            traces=(root/'out/partial-extraction.jsonl').read_text().splitlines()
            self.assertEqual(len(traces),4)
            self.assertEqual([json.loads(t)['status'] for t in traces].count('failed'),1)

    def test_subset_keeps_only_selected_split_assignments(self):
        from copy import deepcopy
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.fixture(root)
            obj=json.loads((data/'batch.json').read_text(encoding='utf-8'))
            second=deepcopy(obj['events'][0]);second['event_id']='e1';second['markets'][0]['market_id']='m1'
            for d in second['articles']:
                d['url']+='second';d['full_text']+=' Distinct second event coverage.'
            obj['events'].append(second);write_json(data/'batch.json',obj)
            build_index(data,root/'artifacts/index.sqlite')
            s=self.service(root,data);p=s.preview(dict(cutoff='2026-05-15T23:59:59Z',count=2,max_documents=20))
            self.assertEqual(p['retained_count'],2)
            payload=s.freeze(p['preview_id'],['m1'],root/'job')
            plan=json.loads((Path(payload['prepared_cohort'])/'plan.json').read_text(encoding='utf-8'))
            self.assertEqual(set(plan['split']['assignments']),{'m1'})
            self.assertEqual(set(plan['split']['events']),{'e1'})

    def test_fresh_worker_fake_extraction_three_modes_and_progress(self):
        from dynamic_retrieval.web_fresh import worker
        from dynamic_retrieval.web_catalog import Catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.fixture(root);s=self.service(root,data)
            p=s.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20))
            job=root/'.runtime/web-jobs/test';payload=s.freeze(p['preview_id'],['m0'],job)
            write_json(job/'payload.json',payload)
            output=root/'artifacts/web-semantic/test'
            result=worker(job/'payload.json',output,client=FakeClient())
            self.assertEqual(result['completed_runs'],3)
            self.assertEqual(len(Catalog(root).list()['runs']),3)
            progress=json.loads((job/'progress.json').read_text())
            self.assertEqual(progress['completed_documents'],20)
            self.assertEqual(progress['stage'],'completed')

    def test_completed_document_progress_not_blocked_by_first_request(self):
        import threading,time
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=fixtures.SemanticPipelineTests().fixture(root)
            release=threading.Event();events=[];errors=[];counter=[0];lock=threading.Lock()
            class SlowFirst(FakeClient):
                def complete_json(self,*args,**kwargs):
                    with lock:
                        counter[0]+=1;number=counter[0]
                    if number==1:release.wait(5)
                    return super().complete_json(*args,**kwargs)
            def work():
                try:
                    with Store(db) as store:
                        run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,max_documents=4,
                            client=SlowFirst(),cache=root/'cache',observer=events.append)
                except Exception as e:errors.append(e)
            thread=threading.Thread(target=work);thread.start()
            try:
                deadline=time.monotonic()+2
                while time.monotonic()<deadline and not any(e.get('completed_documents',0)>=2 for e in events):time.sleep(.01)
                self.assertTrue(any(e.get('completed_documents',0)>=2 for e in events))
            finally:release.set();thread.join(10)
            self.assertEqual(errors,[])

    def test_restart_attaches_completed_predictions_without_resuming(self):
        from dynamic_retrieval.web_jobs import JobManager
        from dynamic_retrieval.web_catalog import Catalog
        from dynamic_retrieval.web_fresh import worker
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.fixture(root);service=self.service(root,data)
            preview=service.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20))
            manager=JobManager(root,Catalog(root),start=False);manager.fresh=service
            with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'SENTINEL'}):
                job=manager.submit_fresh(preview['preview_id'],['m0'],'restart')
            manager.close()
            worker(root/'.runtime/web-jobs'/job['id']/'payload.json',root/'artifacts/web-semantic'/job['id'],client=FakeClient())
            manager=JobManager(root,Catalog(root),start=False)
            try:
                value=manager.get(job['id'])
                self.assertEqual(value['status'],'failed')
                self.assertEqual(value['stage'],'interrupted')
                self.assertEqual(len(value['result_ids']),3)
            finally:manager.close()

    @unittest.skipUnless(os.name=='nt','Windows parent-handle watchdog')
    def test_worker_stops_when_parent_process_exits(self):
        import subprocess,sys
        parent=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(30)'])
        child=None
        try:
            child=subprocess.Popen([sys.executable,'-B','-c',
                'import sys,time;from dynamic_retrieval.web_fresh import watch_parent;watch_parent(int(sys.argv[1]));print("ready",flush=True);time.sleep(30)',str(parent.pid)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.assertEqual(child.stdout.readline().strip(),'ready')
            parent.terminate();parent.wait(timeout=5)
            self.assertEqual(child.wait(timeout=5),3)
        finally:
            for process in (child,parent):
                if process and process.poll() is None:process.terminate();process.wait(timeout=5)
            if child:child.stdout.close();child.stderr.close()
