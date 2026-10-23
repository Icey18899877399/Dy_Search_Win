import importlib
import json
from pathlib import Path
import tempfile
import unittest
from dynamic_retrieval.data.store import build_index, Store


class PipelineTests(unittest.TestCase):
    def module(self):
        try:return importlib.import_module('dynamic_retrieval.pipeline')
        except ModuleNotFoundError:self.fail('Missing automatic end-to-end pipeline')

    def fixture(self,root,outcomes=None):
        data=root/'data';data.mkdir()
        market=dict(market_id='m1',question='Will Alice Smith win the 2028 Republican presidential nomination?',
                    description='Resolves Yes for winning the Republican nomination.',outcomes=outcomes or ['Yes','No'],
                    active=True,closed=False,end_date='2028-11-07T00:00:00Z')
        articles=[dict(title='Alice Smith campaign',full_text='Alice Smith announced her candidacy for the Republican presidential nomination.',
                       source='Paper',url='https://example.test/a',published_at='2026-05-01T00:00:00Z',scrape_status='success')]
        batch=dict(collected_at='2026-05-02T00:00:00Z',scraped_at='2026-05-02T00:00:00Z',
                   events=[dict(event_id='e1',markets=[market],articles=articles)])
        (data/'batch.json').write_text(json.dumps(batch),encoding='utf-8')
        db=root/'index.sqlite';build_index(data,db)
        return data,db

    def test_end_to_end_runs_three_modes_without_reviewed_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=self.fixture(root)
            with Store(db) as store:
                summary=self.module().run_pipeline(store,data,'2026-05-03T00:00:00Z',root/'out',count=1,min_documents=1)
            self.assertEqual(summary['completed_tasks'],1)
            self.assertEqual(summary['completed_runs'],3)
            self.assertEqual(summary['status'],'completed_automatic_rules_experiment')
            self.assertFalse(summary['human_reviewed'])
            for mode in ('fixed','basic','enhanced'):
                run=json.loads((root/'out/runs/m1'/mode/'result.json').read_text(encoding='utf-8'))
                self.assertEqual(run['provenance']['annotations'],{})
                self.assertIs(run['diagnostics']['label_access'],False)
                self.assertTrue(run['task']['positive_patterns'])
                self.assertGreater(run['result']['supporting_evidence_count'],0)
            self.assertTrue((root/'out/index.html').is_file())

    def test_report_yes_no_labels_reorder_reversed_outcome_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=self.fixture(root,['No','Yes'])
            with Store(db) as store:
                self.module().run_pipeline(store,data,'2026-05-03T00:00:00Z',root/'out',count=1,min_documents=1)
            page=(root/'out/index.html').read_text(encoding='utf-8')
            self.assertIn('<td>0.982 / 0.018</td>',page)

    def test_pipeline_refuses_raw_directory_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=self.fixture(root)
            before=list(data.rglob('*'))
            with Store(db) as store,self.assertRaises(ValueError):
                self.module().run_pipeline(store,data,'2026-05-03T00:00:00Z',data/'out',count=1,min_documents=1)
            self.assertEqual(before,list(data.rglob('*')))


if __name__=='__main__':unittest.main()
