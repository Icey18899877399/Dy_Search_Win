import unittest
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config


TASK={'market_id':'demo','event_id':'e','question':'Will Alice win the election?', 'outcomes':['Yes','No'],
      'cutoff':'2026-06-20T00:00:00+00:00',
      'target_elements':{'subject':'alice','action':'win','object':'election'}}


def document(i,date,source='paper'):
    return {'id':i,'event_id':'e','source_id':source,'provider':'archive','title':'Alice election update',
            'text':'Alice won the election.','published_at':date+'T00:00:00+00:00',
            'observed_at':'2026-06-19T00:00:00+00:00','canonical_url':'https://example.test/'+i}


def annotations(docs):
    return {d['id']:{'reviewed':True,'elements':{'subject':'alice','action':'win','object':'election'},
                    'support':[1,-1], 'quote':'Alice won'} for d in docs}


class EngineTests(unittest.TestCase):
    def config(self,**kw):
        v=dict(rounds=5,total_budget=100,round_budget=20,initial_window_days=5,earliest_days=30,
               min_window_days=2,band_days=5,grid_days=5,high_loss=.1,low_loss=0,
               band_fraction=.3,recovery_fraction=.4,stable_distance=0)
        v.update(kw);return Config(**v)

    def test_recovery_updates_current_round_and_prevents_duplicates(self):
        docs=[document('old','2026-06-12')]
        result=run(TASK,docs,self.config(),annotations(docs))
        recovered=[r for r in result['rounds'] if r['recovered_ids']]
        self.assertTrue(recovered)
        self.assertGreater(recovered[0]['probabilities'][0],.9)
        self.assertEqual(recovered[0]['volume'],1)
        self.assertEqual(len({x['id'] for x in result['evidence']}),len(result['evidence']))
        self.assertGreaterEqual(recovered[0]['delta'],1)

    def test_future_publication_and_future_version_excluded_defensively(self):
        docs=[document('future','2026-06-21'),document('late','2026-06-19')]
        docs[1]['observed_at']='2026-06-21T00:00:00+00:00'
        result=run(TASK,docs,self.config(),annotations(docs))
        self.assertEqual(result['evidence'],[])
        self.assertEqual(result['result']['probabilities'],[.5,.5])

    def test_budget_never_overspent_and_reproducible(self):
        docs=[document(str(i),'2026-06-18',str(i%3)) for i in range(30)]
        cfg=self.config(total_budget=3.1,round_budget=3.1)
        a=run(TASK,docs,cfg,annotations(docs));b=run(TASK,docs,cfg,annotations(docs))
        self.assertEqual(a,b)
        self.assertLessEqual(a['result']['spent'],3.1+1e-9)
        self.assertGreaterEqual(a['result']['remaining_budget'],-1e-9)

    def test_contraction_skips_convergence(self):
        docs=[document('a','2026-06-18'),document('b','2026-06-19')]
        result=run(TASK,docs,self.config(low_loss=.01,epsilon=10,convergence=.01,source_exhaustion=.02),annotations(docs))
        contracted=[r for r in result['rounds'] if r['action']=='contract']
        self.assertTrue(contracted)
        self.assertTrue(all(r['convergence_skipped'] for r in contracted))

    def test_fixed_window_does_not_move(self):
        docs=[document('a','2026-06-18')]
        out=run(TASK,docs,self.config(mode='fixed'),annotations(docs))
        self.assertTrue(all(r['action']=='hold' for r in out['rounds']))
        self.assertEqual(out['result']['termination_reason'],'round_limit')

    def test_zero_history_not_reported_as_exhausted(self):
        docs=[document('a','2026-06-18')]
        out=run(TASK,docs,self.config(),annotations(docs))
        self.assertTrue(all(r['source_states']['paper']['phi']==0 for r in out['rounds']))

    def test_config_rejects_invalid_quota_and_nan(self):
        with self.assertRaises(ValueError):Config(gamma=1)
        with self.assertRaises(ValueError):Config(total_budget=float('nan'))
        with self.assertRaises(ValueError):Config.from_dict({'enable_uncertainty_expansion':'false'})

    def test_cache_avoids_duplicate_body_read_charges_across_stages(self):
        docs=[document('old','2026-06-12')]
        result=run(TASK,docs,self.config(),annotations(docs))
        self.assertEqual(result['diagnostics']['body_reads'],1)
        self.assertEqual(sum(r['body_reads'] for r in result['rounds']),1)

    def test_latest_visible_version_compares_timezone_instants(self):
        docs=[document('early','2026-06-18'),document('late','2026-06-18')]
        docs[0]['observed_at']='2026-06-19T10:00:00+14:00'
        docs[1]['observed_at']='2026-06-19T01:00:00+00:00'
        docs[1]['canonical_url']=docs[0]['canonical_url']
        result=run(TASK,docs,self.config(),annotations(docs))
        self.assertEqual([r['id'] for r in result['evidence']],['late'])

    def test_recovery_only_source_has_same_round_exposure(self):
        docs=[document('old'+str(i),'2026-06-14',str(i)) for i in range(7)]
        docs += [document('new'+str(i),'2026-06-18',str(i)) for i in range(2)]
        cfg=self.config(rounds=1,round_budget=15.5,band_days=10,grid_days=10,
                        band_fraction=.1,recovery_fraction=.7)
        r=run(TASK,docs,cfg,annotations(docs))['rounds'][0]
        self.assertEqual(r['action'],'expand')
        for source,budget in r['source_budgets'].items():
            if budget>0:self.assertEqual(r['source_states'][source]['observed_days'],1.)

    def test_cooldown_does_not_reuse_old_positive_gain_for_expansion(self):
        docs=[document('a','2026-06-12'),document('b','2026-06-07'),document('c','2026-06-03')]
        result=run(TASK,docs,self.config(rounds=10),annotations(docs))
        expansions=[r['round'] for r in result['rounds'] if r['action']=='expand']
        self.assertTrue(expansions)
        self.assertTrue(all(b-a>3 for a,b in zip(expansions,expansions[1:])))


if __name__=='__main__':unittest.main()
