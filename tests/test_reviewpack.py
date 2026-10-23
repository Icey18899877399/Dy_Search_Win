import hashlib
import importlib
import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path


class ReviewPackTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('dynamic_retrieval.reviewpack')
        except ModuleNotFoundError:
            self.fail('Missing review-pack writer')

    def cohort(self):
        doc={'id':'d','title':'<script>alert(1)</script>', 'text':'Original text <img src=x>',
             'source_id':'publisher:paper','source_file':'raw_news/day.json',
             'canonical_url':'https://example.test/news',
             'published_at':'2026-05-01T00:00:00Z','observed_at':'2026-05-02T00:00:00Z'}
        return {'requested':1,'completed':1,'selected':[{
            'task':{'market_id':'m1','event_id':'e1','question':'Will A win?',
                    'description':'Requires a win.','outcomes':['Yes','No'],'cutoff':'2026-05-03T00:00:00Z'},
            'eligibility':{'active':True,'closed':False,'end_date':'2026-06-01T00:00:00Z',
                           'semantic_deadline_review':'pending'},
            'documents':[doc], 'annotations':{'d':{'reviewed':False,'support':[0,0],
                  'elements':{'subject':'A'},'quote':'Original text'}}}],
            'exclusions':[], 'provenance':{'cutoff':'2026-05-03T00:00:00Z'}}

    def test_bundle_has_full_text_safe_html_pending_annotations_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'pack'
            self.module().save_cohort(self.cohort(),root)
            annotations=json.loads((root/'tasks/m1/annotations.json').read_text(encoding='utf-8'))
            self.assertFalse(annotations['d']['reviewed'])
            docs=json.loads((root/'tasks/m1/documents.json').read_text(encoding='utf-8'))
            self.assertEqual(docs[0]['text'],'Original text <img src=x>')
            page=(root/'tasks/m1/review.html').read_text(encoding='utf-8')
            self.assertNotIn('<script>alert(1)',page)
            self.assertNotIn('<img src=x>',page)
            self.assertIn('待审核',page)
            manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
            for rel,sha in manifest['files'].items():
                self.assertEqual(hashlib.sha256((root/rel).read_bytes()).hexdigest(),sha)

    def test_rejects_nonempty_destination_to_preserve_review_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'important.txt').write_text('keep')
            with self.assertRaises(ValueError):self.module().save_cohort(self.cohort(),root)
            self.assertEqual((root/'important.txt').read_text(),'keep')

    def test_market_id_stays_inside_output_and_source_is_not_mutated(self):
        with tempfile.TemporaryDirectory() as tmp:
            cohort=self.cohort();cohort['selected'][0]['task']['market_id']='../escape'
            before=json.dumps(cohort,sort_keys=True)
            root=Path(tmp)/'pack';self.module().save_cohort(cohort,root)
            self.assertFalse((Path(tmp)/'escape').exists())
            self.assertEqual(before,json.dumps(cohort,sort_keys=True))

    def test_does_not_allow_reviewed_annotations_in_new_draft_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            cohort=self.cohort();cohort['selected'][0]['annotations']['d']['reviewed']=True
            with self.assertRaises(ValueError):self.module().save_cohort(cohort,Path(tmp)/'pack')

    def test_launcher_runs_end_to_end_and_preserves_existing_review_output(self):
        from dynamic_retrieval.data.store import build_index
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';data.mkdir()
            batch={'collected_at':'2026-05-02T00:00:00Z','scraped_at':'2026-05-02T00:00:00Z',
                   'events':[{'event_id':'e1','markets':[{'market_id':'m1','question':'Will A win?',
                       'description':'A wins.','outcomes':['Yes','No'],'active':True,'closed':False,
                       'end_date':'2026-06-01T00:00:00Z'}],
                       'articles':[{'title':'A wins','full_text':'A wins.','url':'https://example.test/a',
                           'published_at':'2026-05-01T00:00:00Z','scrape_status':'success'}]}]}
            (data/'day.json').write_text(json.dumps(batch),encoding='utf-8')
            db=root/'index.sqlite';build_index(data,db)
            launcher=Path(__file__).resolve().parents[1]/'prepare_experiment.py'
            args=[sys.executable,str(launcher),'--db',str(db),'--data',str(data),
                  '--cutoff','2026-05-03T00:00:00Z','--count','1','--min-documents','1',
                  '--output',str(root/'pack')]
            unsafe=list(args);unsafe[-1]=str(data/'review-output')
            result=subprocess.run(unsafe,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,2,result.stdout)
            self.assertFalse((data/'review-output').exists())
            result=subprocess.run(args,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            target=root/'pack/tasks/m1/annotations.json';before=target.read_bytes()
            result=subprocess.run(args,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,2)
            self.assertEqual(before,target.read_bytes())


if __name__=='__main__':unittest.main()
