import importlib
import unittest
from copy import deepcopy

class QualityTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('dynamic_retrieval.quality')
        except ModuleNotFoundError:
            self.fail('Task 7 quality evaluation module is missing')

    def fixtures(self):
        task=dict(market_id='7',event_id='9',question='Will Alice win?',cutoff='2026-05-01T00:00:00Z')
        gamma=dict(id='7',conditionId='0x'+'a'*64,question=task['question'],
                   outcomes='["No","Yes"]',closed=True,events=[dict(id='9')])
        resolution=dict(data=[dict(condition_id=gamma['conditionId'],status='resolved',
                         payouts=[0,1],resolved_at='2026-06-01T00:00:00Z',
                         transaction_hash='0x'+'b'*64)])
        return task,gamma,resolution

    def test_resolution_uses_payouts_not_proxy_prices_and_matches_identity(self):
        q=self.module();task,gamma,resolution=self.fixtures()
        gamma['outcomePrices']='["1","0"]'
        row=q.validate_resolution(task,gamma,resolution,'2026-10-22T00:00:00Z')
        self.assertEqual(row['status'],'official_resolved')
        self.assertEqual(row['outcome'],'Yes')
        changed=dict(gamma,id='8')
        self.assertEqual(q.validate_resolution(task,changed,resolution,'2026-10-22T00:00:00Z')['status'],'identity_mismatch')

    def test_unresolved_fractional_disputed_and_pre_cutoff_outcomes_not_scored(self):
        q=self.module();task,gamma,resolution=self.fixtures()
        for change in (dict(status='proposed'),dict(status='disputed'),dict(payouts=[.5,.5]),
                       dict(resolved_at='2026-04-01T00:00:00Z'),dict(transaction_hash='')):
            with self.subTest(change=change):
                r=deepcopy(resolution);r['data'][0].update(change)
                self.assertNotEqual(q.validate_resolution(task,gamma,r,'2026-10-22T00:00:00Z')['status'],'official_resolved')
        self.assertNotEqual(q.validate_resolution(task,gamma,{'data':[]},'2026-10-22T00:00:00Z')['status'],'official_resolved')

    def test_event_split_is_stable_and_never_leaks_same_event(self):
        q=self.module()
        tasks=[dict(market_id=str(i),event_id='same' if i<2 else str(i)) for i in range(8)]
        a=q.event_split(tasks,'seed')
        b=q.event_split(list(reversed(tasks)),'seed')
        self.assertEqual(a,b)
        self.assertEqual(a['assignments']['0'],a['assignments']['1'])
        self.assertEqual(set(a['assignments'].values()),{'validation','test'})
        with self.assertRaises(ValueError):q.event_split([{'market_id':'1'}],'seed')

    def test_metrics_handle_zero_denominator_reversed_outcomes_and_bad_probabilities(self):
        q=self.module()
        self.assertIsNone(q.binary_metrics([])['brier'])
        m=q.binary_metrics([(.8,1),(.2,0)])
        self.assertAlmostEqual(m['brier'],.04)
        self.assertEqual(m['n'],2)
        self.assertEqual(sum(x['n'] for x in m['reliability_bins']),2)
        self.assertAlmostEqual(q.yes_probability({'task':{'outcomes':['No','Yes']},'result':{'probabilities':[.2,.8]}}),.8)
        for p in (float('nan'),1.1,-.1):
            with self.assertRaises(ValueError):q.binary_metrics([(p,1)])

    def test_coverage_distinguishes_stale_samples_from_zero_support(self):
        q=self.module()
        task={'cutoff':'2026-05-15T00:00:00Z'}
        cfg={'initial_window_days':14,'band_days':14,'earliest_days':120}
        docs=[{'id':'old','published_at':'2026-04-01T00:00:00Z'},
              {'id':'band','published_at':'2026-04-25T00:00:00Z'},
              {'id':'new','published_at':'2026-05-14T00:00:00Z'}]
        row=q.coverage_diagnostic(task,docs,{'old':{'support':[1,-1]}},cfg)
        self.assertEqual(row['initial_window'],1)
        self.assertEqual(row['initial_transition_band'],1)
        self.assertEqual(row['older_than_initial_reach'],1)
        self.assertEqual(row['directional_outside_initial_reach'],1)

    def test_resolution_rejects_duplicates_bad_times_and_nonbinary_payload(self):
        q=self.module();task,gamma,r=self.fixtures()
        r['data']*=2
        self.assertNotEqual(q.validate_resolution(task,gamma,r,'2026-10-22T00:00:00Z')['status'],'official_resolved')
        for value in (None,'invalid','2027-01-01T00:00:00Z'):
            task,gamma,r=self.fixtures();r['data'][0]['resolved_at']=value
            self.assertNotEqual(q.validate_resolution(task,gamma,r,'2026-10-22T00:00:00Z')['status'],'official_resolved')


    def test_official_event_membership_scaled_payout_and_block_provenance(self):
        q=self.module();task,gamma,r=self.fixtures()
        gamma.pop('events')
        event={'id':'9','markets':[{'id':'7','conditionId':gamma['conditionId']}]}
        r['data'][0].update(payouts=[0,1000000],transaction_hash='',resolved_block=95228370)
        self.assertEqual(q.validate_resolution(task,gamma,r,'2026-10-22T00:00:00Z',event)['outcome'],'Yes')
        event['markets'][0]['conditionId']='0x'+'c'*64
        self.assertEqual(q.validate_resolution(task,gamma,r,'2026-10-22T00:00:00Z',event)['status'],'identity_mismatch')


