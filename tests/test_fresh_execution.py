import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from dynamic_retrieval.cli import write_json
from dynamic_retrieval.data.store import Store
from dynamic_retrieval.models import Config
import test_web_fresh as fresh_fixtures
from test_semantic_pipeline import FakeClient,CUTOFF
import test_semantic_pipeline as semantic_fixtures

EXECUTION=dict(budget_policy='patent_budget_v1',grid_policy=dict(version='patent_grid_v1',cap_fraction=.31,width_fraction=.5),retrieval_policy='bm25_read_guard_v1')

class FreshExecutionTests(unittest.TestCase):
    def test_preview_freezes_explicit_execution_and_extraction_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); f=fresh_fixtures.FreshTests();data=f.fixture(root);service=f.service(root,data)
            preview=service.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,execution=EXECUTION,extraction_mode='on_demand'))
            self.assertEqual(preview['execution'],EXECUTION)
            self.assertEqual(preview['model_request_upper_bound'],60)
            frozen=service.freeze(preview['preview_id'],['m0'],root/'job')
            plan=json.loads((Path(frozen['prepared_cohort'])/'plan.json').read_text())
            self.assertEqual(frozen['execution'],plan['execution'])
            self.assertEqual(frozen['extraction_mode'],'on_demand')
            self.assertEqual(frozen['model_request_upper_bound'],60)

    def test_shared_pipeline_records_each_mode_execution(self):
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=semantic_fixtures.SemanticPipelineTests().fixture(root);client=FakeClient()
            with Store(db) as store:
                summary=run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,max_documents=4,client=client,cache=root/'cache',execution=EXECUTION)
            self.assertEqual(len(client.calls),4)
            self.assertEqual(summary['execution'],EXECUTION)
            self.assertEqual(summary['extraction_mode'],'shared')
            for mode in ('fixed','basic','enhanced'):
                result=json.loads((root/f'out/runs/m0/{mode}/result.json').read_text())
                self.assertEqual(result['provenance']['budget_policy'],'patent_budget_v1')
                self.assertEqual(result['provenance']['retrieval_policy'],'bm25_read_guard_v1')
                self.assertEqual(result['provenance'].get('grid_policy'),EXECUTION['grid_policy'] if mode=='enhanced' else None)

    def test_invalid_execution_before_any_model_call(self):
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=semantic_fixtures.SemanticPipelineTests().fixture(root);client=FakeClient()
            with Store(db) as store:
                with self.assertRaises(ValueError):
                    run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,client=client,cache=root/'cache',execution=EXECUTION,config=Config(total_budget=1))
            self.assertEqual(client.calls,[])

    def test_on_demand_unread_documents_are_not_model_failures(self):
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=semantic_fixtures.SemanticPipelineTests().fixture(root);client=FakeClient()
            config=Config(rounds=1,min_window_days=.1,initial_window_days=.5,earliest_days=1,band_days=.1)
            with Store(db) as store:
                summary=run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,max_documents=4,client=client,cache=root/'cache',execution=EXECUTION,extraction_mode='on_demand',config=config)
            self.assertEqual(client.calls,[])
            self.assertEqual(summary['tasks'][0]['failed_documents'],0)
            self.assertEqual(summary['tasks'][0]['unread_documents'],4)
            candidates=json.loads((root/'out/inputs/tasks/m0/documents.json').read_text())
            self.assertEqual(len(candidates),4)
            self.assertEqual({d['id'] for d in candidates},{d['id'] for d in json.loads((root/'out/inputs/tasks/m0/sampled-documents.json').read_text())})

    def test_on_demand_transport_mock_keeps_cache_and_mode_bills_separate(self):
        import io
        from dynamic_retrieval.semantic import DeepSeekClient
        from dynamic_retrieval.call_cost import CallCostLedger
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=semantic_fixtures.SemanticPipelineTests().fixture(root)
            fake=FakeClient();client=DeepSeekClient(root/'cache',api_key='fixture-only',max_attempts=1,cost_ledger=CallCostLedger())
            class Opener:
                def open(self,request,timeout):
                    request_data=json.loads(request.data)
                    response=fake.complete_json(request_data['messages'])
                    return io.BytesIO(json.dumps(dict(id='fixture',model='deepseek-flash',usage=response['metadata']['usage'],
                        choices=[dict(finish_reason='stop',message=dict(content=json.dumps(response['data'])))] )).encode())
            client._opener=Opener()
            with Store(db) as store:
                summary=run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,max_documents=4,client=client,cache=root/'cache',execution=EXECUTION,extraction_mode='on_demand')
            rows=summary['mode_model_accounting']
            self.assertEqual(len(rows),3)
            self.assertEqual(rows[0]['accounting']['network_attempts'],4)
            self.assertEqual(rows[1]['accounting']['network_attempts'],0)
            self.assertEqual(rows[1]['accounting']['cache_hits'],4)
            self.assertEqual(rows[2]['accounting']['network_attempts'],0)
            self.assertEqual(client.cost_ledger.snapshot()['events'],[])
            self.assertEqual(len(fake.calls),4)

    def test_shared_profile_never_silently_changes_source_universe_after_failures(self):
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        from dynamic_retrieval.preparation import prepare_cohort
        from test_source_cost_profile import SourceCostProfileTests
        class FailedClient(FakeClient):
            def complete_json(self,*args,**kwargs):
                raise RuntimeError('fixture transport failure')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=semantic_fixtures.SemanticPipelineTests().fixture(root)
            with Store(db) as store:
                cohort=prepare_cohort(store,data,CUTOFF,count=1,min_documents=1)
                source_id=cohort['selected'][0]['documents'][0]['source_id']
                profile=SourceCostProfileTests().profile();profile['observations']=profile['observations'][:1]
                profile['observations'][0]['source_id']=source_id
                execution=dict(EXECUTION,source_cost_profile=profile)
                summary=run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,client=FailedClient(),cache=root/'cache',execution=execution)
            self.assertEqual(summary['completed_runs'],0)
            self.assertEqual(summary['status'],'partial_model_failures')
            self.assertEqual(summary['tasks'][0]['execution_error'],'source_cost_profile_source_set_changed_after_extraction')
            self.assertEqual(summary['execution']['source_cost_profile'],profile)

    def test_new_event_worker_preserves_patent_evidence_in_all_modes(self):
        from dynamic_retrieval.web_fresh import worker
        for extraction_mode in ('shared','on_demand'):
            with self.subTest(extraction_mode=extraction_mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); f=fresh_fixtures.FreshTests();data=f.fixture(root);service=f.service(root,data)
                execution=dict(EXECUTION,evidence_policy='patent_elements_v1')
                preview=service.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,execution=execution,extraction_mode=extraction_mode))
                job=root/'job';payload=service.freeze(preview['preview_id'],['m0'],job)
                write_json(job/'payload.json',payload);out=root/'artifacts/web-semantic/test'
                summary=worker(job/'payload.json',out,client=FakeClient())
                self.assertEqual(summary['execution'],execution)
                self.assertEqual(summary['completed_runs'],3)
                for mode in ('fixed','basic','enhanced'):
                    result=json.loads((out/f'runs/m0/{mode}/result.json').read_text())
                    self.assertEqual(result['provenance']['evidence_policy'],'patent_elements_v1')
                    self.assertEqual(result['provenance']['extraction_mode'],extraction_mode)
                    self.assertEqual(result['result']['probabilities'],[.5,.5])
                manifest=json.loads((out/'manifest.json').read_text())
                self.assertEqual(manifest['execution'],execution)
                self.assertEqual(manifest['extraction_mode'],extraction_mode)
                if extraction_mode=='on_demand':
                    from dynamic_retrieval.web_catalog import Catalog
                    catalog=Catalog(root)
                    for row in catalog.list()['runs']:
                        path=catalog.path(row['id'])
                        _,documents,_=catalog._inputs(path,json.loads(path.read_text(encoding='utf-8')))
                        self.assertEqual(len(documents),20)
                        with self.assertRaisesRegex(ValueError,'[Oo]n-demand'):
                            catalog.replay_inputs(row['id'])

    def test_on_demand_job_row_preserves_mode_and_request_ceiling(self):
        import os
        from dynamic_retrieval.web_jobs import JobManager
        from dynamic_retrieval.web_catalog import Catalog
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); f=fresh_fixtures.FreshTests();data=f.fixture(root);service=f.service(root,data)
            preview=service.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,execution=EXECUTION,extraction_mode='on_demand'))
            manager=JobManager(root,Catalog(root),start=False);manager.fresh=service
            try:
                with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fixture-only-never-sent'}):
                    job=manager.submit_fresh(preview['preview_id'],['m0'],'demand-ceiling')
                self.assertEqual(job['model_request_upper_bound'],60)
                self.assertEqual(job['extraction_mode'],'on_demand')
                self.assertEqual(job['execution'],EXECUTION)
                manager.cancel(job['id'])
            finally:manager.close()

    def test_source_profile_coverage_rejected_before_calls(self):
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        from test_source_cost_profile import SourceCostProfileTests
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=semantic_fixtures.SemanticPipelineTests().fixture(root);client=FakeClient()
            execution=dict(EXECUTION,source_cost_profile=SourceCostProfileTests().profile())
            with Store(db) as store:
                with self.assertRaisesRegex(ValueError,'source_ids'):
                    run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,client=client,cache=root/'cache',execution=execution)
            self.assertEqual(client.calls,[])

    def test_mismatched_frozen_extraction_mode_never_calls_model(self):
        from dynamic_retrieval.web_fresh import worker
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); f=fresh_fixtures.FreshTests();data=f.fixture(root);service=f.service(root,data)
            preview=service.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,execution=EXECUTION))
            job=root/'job';payload=service.freeze(preview['preview_id'],['m0'],job)
            payload['extraction_mode']='on_demand';write_json(job/'payload.json',payload);client=FakeClient()
            with self.assertRaisesRegex(ValueError,'Frozen execution'):worker(job/'payload.json',root/'artifacts/web-semantic/test',client=client)
            self.assertEqual(client.calls,[])

    def test_on_demand_uses_mode_specific_ledgers_and_bounded_calls(self):
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=semantic_fixtures.SemanticPipelineTests().fixture(root);client=FakeClient()
            with Store(db) as store:
                summary=run_semantic_pipeline(store,data,CUTOFF,root/'out',count=1,min_documents=1,max_documents=4,client=client,cache=root/'cache',execution=EXECUTION,extraction_mode='on_demand')
            self.assertEqual(summary['completed_runs'],3)
            self.assertLessEqual(len(client.calls),12)
            self.assertEqual(summary['model_request_upper_bound'],12)
            self.assertEqual(len(summary['mode_model_accounting']),3)
            for mode in ('fixed','basic','enhanced'):
                result=json.loads((root/f'out/runs/m0/{mode}/result.json').read_text())
                self.assertIn('extraction_trace',result)
                self.assertTrue((root/f'out/runs/m0/{mode}/model-call-ledger.json').is_file())

    def test_worker_rejects_execution_payload_tampering(self):
        from dynamic_retrieval.web_fresh import worker
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); f=fresh_fixtures.FreshTests();data=f.fixture(root);service=f.service(root,data)
            preview=service.preview(dict(cutoff='2026-05-15T23:59:59Z',count=1,max_documents=20,execution=EXECUTION))
            job=root/'job';payload=service.freeze(preview['preview_id'],['m0'],job)
            payload['execution']={};write_json(job/'payload.json',payload);client=FakeClient()
            with self.assertRaises(ValueError):worker(job/'payload.json',root/'artifacts/web-semantic/test',client=client)
            self.assertEqual(client.calls,[])

if __name__=='__main__':unittest.main()
