import importlib
import json
from pathlib import Path
import tempfile
import unittest
import test_semantic_pipeline as fixtures
from dynamic_retrieval.data.store import Store
from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
from dynamic_retrieval.official import GAMMA, RESOLUTIONS
from dynamic_retrieval.quality import validate_resolution

class QualityPipelineTests(unittest.TestCase):
    def module(self):
        try:return importlib.import_module('dynamic_retrieval.quality_pipeline')
        except ModuleNotFoundError:self.fail('Quality reporting pipeline is missing')

    def experiment(self,root,client=None):
        data,db=fixtures.SemanticPipelineTests().fixture(root)
        with Store(db) as store:
            run_semantic_pipeline(store,data,'2026-05-03T00:00:00Z',root/'experiment',
                count=1,min_documents=1,max_documents=4,client=client or fixtures.FakeClient(),cache=root/'cache')
        return root/'experiment'

    def snapshot(self,task):
        gamma=dict(id=task['market_id'],conditionId='0x'+'a'*64,question=task['question'],
                   description=task['description'],outcomes='["Yes","No"]',closed=True,
                   events=[dict(id=task['event_id'])])
        response=dict(data=[dict(condition_id=gamma['conditionId'],status='resolved',
                      payouts=[1,0],resolved_at='2026-06-01T00:00:00Z',transaction_hash='0x'+'b'*64)])
        return dict(gamma=gamma,resolution=response,fetched_at='2026-10-22T00:00:00Z',
                    urls=[GAMMA+task['market_id'],RESOLUTIONS+gamma['conditionId']])

    def test_freeze_precedes_collection_and_official_denominator_is_explicit(self):
        q=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.experiment(root);out=root/'quality'
            def collector(task):
                self.assertTrue((out/'evaluation-plan.json').is_file())
                return self.snapshot(task)
            report=q.build_quality_report(source,out,fetch=True,collector=collector)
            self.assertEqual(report['official_resolved_tasks'],1)
            self.assertEqual(report['metrics']['test']['enhanced']['n'],1)
            self.assertFalse(report['independent_holdout_claim'])
            self.assertTrue((out/'manifest.json').is_file())

    def test_offline_mode_keeps_metrics_null_and_no_requests(self):
        q=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.experiment(root)
            report=q.build_quality_report(source,root/'quality',collector=lambda t:self.fail('No network expected'))
            self.assertEqual(report['official_resolved_tasks'],0)
            self.assertIsNone(report['metrics']['test']['enhanced']['brier'])

    def test_tampered_source_and_nested_output_rejected_before_fetch(self):
        q=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.experiment(root)
            with self.assertRaises(ValueError):q.build_quality_report(source,source/'nested')
            p=source/'summary.json';p.write_text('{}')
            with self.assertRaises(ValueError):q.build_quality_report(source,root/'quality')

    def test_forged_label_marker_cannot_bypass_raw_resolution_validation(self):
        q=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.experiment(root)
            def collector(task):
                snap=self.snapshot(task);snap['resolution']['data'][0]['status']='proposed'
                snap['label']={'status':'official_resolved','outcome':'Yes'}
                return snap
            report=q.build_quality_report(source,root/'quality',fetch=True,collector=collector)
            self.assertEqual(report['official_resolved_tasks'],0)


    def test_partial_extraction_is_evaluated_with_explicit_failed_denominator(self):
        q=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.experiment(root,client=fixtures.FakeClient(fail=True))
            summary=json.loads((source/'summary.json').read_text())
            self.assertEqual(summary['status'],'partial_model_failures')
            report=q.build_quality_report(source,root/'quality')
            self.assertEqual(report['failed_semantic_documents'],1)
            self.assertEqual(report['source_extraction_status'],'partial_model_failures')
            self.assertEqual(report['requested_tasks'],1)
