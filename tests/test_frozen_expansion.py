import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_expansion as fixtures
from dynamic_retrieval.data.store import Store,build_index
from dynamic_retrieval.models import Config
from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
import test_semantic_pipeline as semantic_fixtures

class FrozenExpansionTests(unittest.TestCase):
    def make(self,root):
        data=root/'data';data.mkdir()
        rows=fixtures.ExpansionTests().docs();events=[]
        for i in range(2):
            articles=[dict(title=d['title'],full_text=f'Event {i}. '+d['text'],
                url=d['canonical_url']+f'/event{i}',source=d['source_id'],
                published_at=d['published_at'],scrape_status='success') for d in rows]
            events.append(dict(event_id=f'e{i}',markets=[dict(market_id=f'm{i}',
                question=f'Will Alice Smith win the 2028 Republican presidential nomination?',
                description='Republican nomination in 2028',outcomes=['Yes','No'],active=True,closed=False,
                end_date='2028-11-07T00:00:00Z')],articles=articles))
        (data/'batch.json').write_text(json.dumps(dict(collected_at='2026-05-14T01:00:00Z',scraped_at='2026-05-14T01:00:00Z',events=events)))
        db=root/'index.sqlite';build_index(data,db)
        return data,db

    def module(self):return importlib.import_module('dynamic_retrieval.expansion')

    def test_freeze_is_label_blind_load_checks_config_and_tampering(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=self.make(root)
            with Store(db) as store,patch.object(Store,'labels',side_effect=AssertionError('No labels')):
                plan=m.prepare_expansion(store,data,'2026-05-15T00:00:00Z',root/'frozen',history=root/'history',count=2)
            self.assertEqual(plan['retained_tasks'],2)
            cohort,_=m.load_expansion(root/'frozen','2026-05-15T00:00:00Z',Config())
            self.assertEqual(len(cohort['selected']),2)
            with self.assertRaises(ValueError):m.load_expansion(root/'frozen','2026-05-15T00:00:00Z',Config(initial_window_days=20))
            p=root/'frozen/cohort.json';p.write_text('{}')
            with self.assertRaises(ValueError):m.load_expansion(root/'frozen','2026-05-15T00:00:00Z',Config())

    def test_prior_event_is_excluded_without_relaxing_requested_target(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=self.make(root)
            h=root/'history/old';h.mkdir(parents=True)
            (h/'result.json').write_text(json.dumps({'task':{'event_id':'e0'},'provenance':{'inputs':[]}}))
            (h/'manifest.json').write_text(json.dumps({'files':{'result.json':m.sha(h/'result.json')}}))
            with Store(db) as store:
                plan=m.prepare_expansion(store,data,'2026-05-15T00:00:00Z',root/'frozen',history=root/'history',count=2)
            self.assertEqual(plan['retained_tasks'],1)
            self.assertEqual(plan['target_tasks'],2)
            self.assertEqual(plan['selected'][0]['event_id'],'e1')

    def test_semantic_run_consumes_exact_frozen_inputs_and_writes_plan_before_model(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=self.make(root)
            with Store(db) as store:
                m.prepare_expansion(store,data,'2026-05-15T00:00:00Z',root/'frozen',history=root/'history',count=2)
            cohort,plan=m.load_expansion(root/'frozen','2026-05-15T00:00:00Z',Config())
            calls=[]
            class Client:
                def complete_json(self,messages,max_tokens=1800):
                    self_outer.assertTrue((root/'out/inputs/pre-model-plan.json').is_file())
                    self_outer.assertTrue((root/'out/inputs/extraction-protocol.json').is_file())
                    context=json.loads(messages[1]['content'])
                    calls.append(context['evidence']['id'])
                    excerpt=context['evidence']['excerpt']
                    return {'data':{'elements':{},'support':[0,0],'quote':excerpt[:40],
                       'rationale':'No relevant directional fact.','factual_status':'irrelevant','time_scope':'unknown'},
                       'metadata':{'model':'mock','cache_hit':False,'usage':{'total_tokens':10}}}
            self_outer=self
            with Store(db) as store:
                result=run_semantic_pipeline(store,data,'2026-05-15T00:00:00Z',root/'out',
                    prepared_cohort=root/'frozen',client=Client(),cache=root/'cache')
            self.assertEqual(result['completed_runs'],6)
            self.assertEqual(set(calls),{d['id'] for i in cohort['selected'] for d in i['documents']})
            saved=json.loads((root/'out/inputs/pre-model-plan.json').read_text())
            self.assertEqual(saved['split'],plan['split'])
