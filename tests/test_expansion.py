import importlib
import unittest
from collections import Counter
from dynamic_retrieval.models import Config

class ExpansionTests(unittest.TestCase):
    def module(self):
        try:return importlib.import_module('dynamic_retrieval.expansion')
        except ModuleNotFoundError:self.fail('Missing frozen expansion and stratified sampler')

    def docs(self):
        rows=[]
        for zone,date in [('window','2026-05-14'),('band','2026-04-25'),('history','2026-03-01')]:
            for i in range(16):
                rows.append(dict(id=f'{zone}{i}',title=f'Independent report {i}',
                    text=(f'Officials confirmed a new development {zone} {i}. '*8),
                    canonical_url=f'https://paper{i%8}.test/{zone}/{i}',source_id=f'paper{i%8}',
                    event_id='e',published_at=date+'T00:00:00Z',observed_at='2026-05-14T01:00:00Z'))
        return rows

    def test_stratification_balances_time_and_caps_sources(self):
        m=self.module();docs=self.docs()
        selected,audit=m.stratified_documents({'event_id':'e','cutoff':'2026-05-15T00:00:00Z'},docs,Config(),20,3)
        self.assertEqual(len(selected),20)
        self.assertEqual(audit['selected_by_zone'],{'window':10,'band':6,'history':4})
        self.assertLessEqual(max(Counter(d['source_id'] for d in selected).values()),3)
        other,_=m.stratified_documents({'event_id':'e','cutoff':'2026-05-15T00:00:00Z'},list(reversed(docs)),Config(),20,3)
        self.assertEqual([d['id'] for d in selected],[d['id'] for d in other])

    def test_odds_future_foreign_and_republished_body_excluded(self):
        m=self.module();docs=self.docs()
        docs += [dict(docs[0],id='odds',title='Polymarket odds rise to 70% YES'),
                 dict(docs[1],id='future',observed_at='2026-05-16T00:00:00Z'),
                 dict(docs[2],id='foreign',event_id='other'),
                 dict(docs[0],id='republished',canonical_url='https://copy.test/a',source_id='copy')]
        selected,audit=m.stratified_documents({'event_id':'e','cutoff':'2026-05-15T00:00:00Z'},docs,Config(),20,3)
        self.assertEqual(audit['excluded']['market_commentary'],1)
        self.assertEqual(audit['excluded']['temporal_or_foreign'],2)
        self.assertEqual(audit['excluded']['duplicate_body_or_url'],1)
        self.assertNotIn('odds',{d['id'] for d in selected})

    def test_no_forced_fill_with_old_or_concentrated_articles(self):
        m=self.module()
        docs=[d for d in self.docs() if d['id'].startswith('history')]
        selected,audit=m.stratified_documents({'event_id':'e','cutoff':'2026-05-15T00:00:00Z'},docs,Config(),20,3)
        self.assertEqual(audit['selected_by_zone']['window'],0)
        self.assertLess(len(selected),20)
        docs=[dict(d,source_id='one') for d in self.docs()]
        selected,_=m.stratified_documents({'event_id':'e','cutoff':'2026-05-15T00:00:00Z'},docs,Config(),20,3)
        self.assertEqual(len(selected),3)

    def test_used_documents_are_excluded_across_events(self):
        m=self.module();docs=self.docs()
        selected,_=m.stratified_documents({'event_id':'e','cutoff':'2026-05-15T00:00:00Z'},docs,Config(),20,3)
        keys={m.body_key(d) for d in selected}
        again,audit=m.stratified_documents({'event_id':'e','cutoff':'2026-05-15T00:00:00Z'},docs,Config(),20,3,used_bodies=keys)
        self.assertFalse(keys & {m.body_key(d) for d in again})
        self.assertEqual(audit['excluded']['previously_selected_document'],20)
