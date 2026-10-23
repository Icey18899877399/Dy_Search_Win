"""Behavior contracts: source time, task conditions and nonterminal progress."""
import unittest
from copy import deepcopy
from test_patent_evidence_v2 import task, cease, count
try:
 from dynamic_retrieval import patent_evidence_v4 as p
except ImportError:
 from dynamic_retrieval import patent_evidence_v3 as p

class TemporalProgressTests(unittest.TestCase):
 def ev(self,s,t=None,quote=None,ann=None):
  return p.evaluate({},t or task(),quote=quote or s,text=s,original_support=[1,-1],annotation=ann)
 def test_passed_preliminary_stage_supports_progress_without_conflicting_no(self):
  s='The Knesset passed a preliminary dissolution bill on May 28, 2026.'
  e,r,d,tr=self.ev(s);self.assertEqual(d,[1,0]);self.assertNotEqual(e['action'],'dissolve')
  self.assertEqual(tr['support']['evidence_class'],'nonterminal_progress');self.assertFalse(tr['support']['outcome_determined'])
 def test_rejected_bill_supports_setback_without_claiming_impossible(self):
  self.assertEqual(self.ev('The Knesset rejected a preliminary dissolution bill on May 28, 2026.')[2],[0,1])
 def test_actual_bilateral_negotiations_are_progress_not_agreement(self):
  s='Russia and Ukraine began formal negotiations for a general ceasefire on May 28, 2026.'
  e,r,d,tr=self.ev(s,cease());self.assertEqual(d,[1,0]);self.assertNotEqual(e['action'],'agree ceasefire');self.assertGreaterEqual(r,.5)
 def test_suspended_negotiations_are_setback_not_task_failure(self):
  s='Russia and Ukraine suspended formal negotiations for a general ceasefire on May 28, 2026.'
  self.assertEqual(self.ev(s,cease())[2],[0,1])
 def test_reverse_outcomes_preserve_named_progress_direction(self):
  t=task();t['outcomes']=['No','Yes'];self.assertEqual(self.ev('The Knesset passed a preliminary dissolution bill on May 28, 2026.',t)[2],[0,1])
 def test_progress_missing_old_future_dates_neutral(self):
  for end in ['', ' on May 28, 2025', ' on July 28, 2026']:
   self.assertEqual(self.ev('The Knesset passed a preliminary dissolution bill'+end+'.')[2],[0,0])
 def test_linked_vote_date_is_attached_to_action(self):
  s='The Knesset passed a preliminary dissolution bill. This vote took place on May 28, 2026.'
  e,r,d,tr=self.ev(s);self.assertEqual(e.get('time'),'2026-05-28');self.assertEqual(d,[1,0])
  for ws in tr['normalization']['witnesses'].values():
   for w in ws:self.assertEqual(s[w['start']:w['end']],w['text'])
 def test_another_vote_date_not_borrowed(self):
  s='The Knesset passed a preliminary dissolution bill. Another vote took place on May 28, 2026.'
  self.assertNotIn('time',self.ev(s)[0]);self.assertEqual(self.ev(s)[2],[0,0])
 def test_relative_time_not_replaced_with_task_or_publication_date(self):
  e,r,d,tr=self.ev('The Knesset passed a preliminary dissolution bill on Wednesday.')
  self.assertNotIn('time',e);self.assertEqual(d,[0,0])
 def test_negated_hypothetical_and_unrelated_actions_cannot_be_progress(self):
  for s in ['The Knesset may pass a preliminary dissolution bill on May 28, 2026.', 'It is false that the Knesset passed a preliminary dissolution bill on May 28, 2026.', 'The Knesset did not pass a preliminary dissolution bill on May 28, 2026.', 'The Knesset passed a preliminary tax bill on May 28, 2026.', 'France passed a preliminary dissolution bill on May 28, 2026.']:
   with self.subTest(s=s):self.assertEqual(self.ev(s)[2],[0,0])
 def test_progress_denial_in_same_context_abstains(self):
  a='The Knesset passed a preliminary dissolution bill on May 28, 2026.'
  self.assertEqual(self.ev(a+' This vote was denied as false.',quote=a)[2],[0,0])
 def test_excerpt_does_not_supply_hidden_progress_date(self):
  a='The Knesset passed a preliminary dissolution bill.'
  self.assertEqual(self.ev(a+' This vote took place on May 28, 2026.',quote=a,ann={'excerpt':a})[2],[0,0])
 def test_day_only_assertion_cannot_establish_visible_before_midday(self):
  self.assertEqual(self.ev('The Knesset was dissolved on June 1, 2026.',task(cutoff='2026-06-01T10:00:00Z'))[2],[0,0])
 def test_timestamp_near_et_deadline_is_compared_as_instant(self):
  t=task(cutoff='2026-08-02T12:00:00Z')
  self.assertEqual(self.ev('The Knesset was dissolved on 2026-08-01T03:30:00Z.',t)[2],[1,-1])
  self.assertEqual(self.ev('The Knesset was dissolved on 2026-08-01T04:30:00Z.',t)[2],[0,0])
 def test_day_only_deadline_boundary_does_not_claim_exact_timezone(self):
  self.assertEqual(self.ev('The Knesset was dissolved on July 31, 2026.',task(cutoff='2026-08-02T00:00:00Z'))[2],[0,0])
 def test_agreement_and_effective_dates_are_separate(self):
  s='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026. This ceasefire takes effect on July 2, 2026.'
  e,r,d,tr=self.ev(s,cease());self.assertEqual(d,[1,-1]);self.assertEqual(e['time'],'2026-05-28')
  self.assertEqual(tr['support']['time_check']['effective_start'],'2026-07-02')
 def test_framework_requires_explicit_effective_start(self):
  a='Russia and Ukraine publicly announced a mutually agreed general ceasefire agreement on May 28, 2026 as part of a political framework.'
  self.assertEqual(self.ev(a,cease())[2],[0,0])
  self.assertEqual(self.ev(a+' This ceasefire takes effect on July 2, 2026.',cease())[2],[1,-1])
 def test_additional_task_duration_condition_is_not_silently_ignored(self):
  t=cease();t['description']+=' The ceasefire must last at least 30 days.'
  self.assertEqual(self.ev('Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.',t)[2],[0,0])
 def test_conflicting_question_description_deadlines_abstain(self):
  t=task('Israeli parliament dissolved by July 30, 2026?')
  self.assertEqual(self.ev('The Knesset was dissolved on May 28, 2026.',t)[2],[0,0])
 def test_count_market_proxy_stays_neutral(self):
  self.assertEqual(self.ev('Elon Musk will post 1000 tweets in April 2026 according to market odds.',count())[2],[0,0])
 def test_explicit_dates_with_other_actors_do_not_supply_progress(self):
  s='Russia and Ukraine began formal negotiations for a general ceasefire on May 28, 2026.'
  self.assertEqual(self.ev(s.replace('Ukraine','Iran'),cease())[2],[0,0])
 def test_dated_progress_and_completion_have_distinct_exact_keys(self):
  a=self.ev('The Knesset passed a preliminary dissolution bill on May 28, 2026.')
  b=self.ev('The Knesset was dissolved on May 28, 2026.')
  self.assertNotEqual(a[3]['fact_group']['key'],b[3]['fact_group']['key'])
if __name__=='__main__':unittest.main()

class ProgressEngineIntegrationTests(unittest.TestCase):
 def test_engine_uses_progress_without_changing_exact_overlap(self):
  from dynamic_retrieval.engine import run
  from dynamic_retrieval.models import Config
  t=cease();d=dict(id='progress',title='',text='Russia and Ukraine began formal negotiations for a general ceasefire on May 28, 2026.',source_id='wire',published_at='2026-05-29T00:00:00Z',observed_at='2026-05-29T01:00:00Z')
  out=run(t,[d],Config(mode='fixed',rounds=1),evidence_policy='patent_elements_v4')
  self.assertEqual(out['diagnostics']['admitted_documents'],1)
  self.assertEqual(out['result']['supporting_evidence_count'],1)
  self.assertGreater(out['result']['probabilities'][0],.5)

class TemporalProgressReviewTests(unittest.TestCase):
 ev=TemporalProgressTests.ev
 def test_multiple_attached_event_dates_conflict(self):
  s='On May 27, 2026, the Knesset was dissolved on May 28, 2026.'
  self.assertEqual(self.ev(s)[2],[0,0])
 def test_unimplemented_mandatory_condition_blocks_terminal(self):
  t=cease();t['description']+=' The agreement must be ratified by both national parliaments.'
  self.assertEqual(self.ev('Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.',t)[2],[0,0])
 def test_linked_hypothetical_vote_blocks_progress(self):
  a='The Knesset passed a preliminary dissolution bill on May 28, 2026.'
  self.assertEqual(self.ev(a+' This vote was hypothetical.',quote=a)[2],[0,0])
 def test_elapsed_deadline_negative_retained(self):
  self.assertEqual(self.ev('The Knesset had not been dissolved by July 31, 2026.',task(cutoff='2026-08-02T00:00:00Z'))[2],[-1,1])
 def test_future_effective_date_not_uncertain_past_agreement(self):
  a='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.'
  self.assertEqual(self.ev(a+' This ceasefire will take effect on July 2, 2026.',cease())[2],[1,-1])
 def test_corrected_progress_keeps_distinct_fact_identity(self):
  a='The Knesset passed a preliminary dissolution bill on May 28, 2026.'
  self.assertNotEqual(self.ev(a)[3]['fact_group']['key'],self.ev(a+' This bill was denied as false.',quote=a)[3]['fact_group']['key'])
 def test_inline_and_linked_effective_dates_conflict(self):
  a='Russia and Ukraine publicly announced a mutually agreed general ceasefire agreement on May 28, 2026 as part of a political framework, effective on July 2, 2026.'
  self.assertEqual(self.ev(a+' This ceasefire takes effect on July 3, 2026.',cease())[2],[0,0])

class MoreTemporalReviewTests(unittest.TestCase):
 ev=TemporalProgressTests.ev
 def test_unrelated_clause_cannot_supply_event_date(self):
  for s,t in [('The Knesset was dissolved; France passed a bill on May 28, 2026.',task()),('Russia and Ukraine publicly announced a mutually agreed general ceasefire; Armenia and Azerbaijan signed an agreement on May 28, 2026.',cease())]:
   e,r,d,tr=self.ev(s,t);self.assertEqual(d,[0,0]);self.assertNotIn('time',e)
 def test_inline_effective_without_on_conflicts_and_is_recognized(self):
  a='Russia and Ukraine publicly announced a mutually agreed general ceasefire agreement on May 28, 2026, effective July 2, 2026, as part of a political framework.'
  self.assertEqual(self.ev(a,cease())[2],[1,-1])
  self.assertEqual(self.ev(a+' This ceasefire takes effect on July 3, 2026.',cease())[2],[0,0])
 def test_unknown_exclusion_is_not_ignored(self):
  t=cease();t['description']+=' Agreements without ratification by both national parliaments do not qualify.'
  self.assertEqual(self.ev('Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.',t)[2],[0,0])
 def test_conditionally_valid_progress_abstains(self):
  a='The Knesset passed a preliminary dissolution bill on May 28, 2026.'
  self.assertEqual(self.ev(a+' This vote is conditional on final judicial validation.',quote=a)[2],[0,0])
 def test_equivalent_future_effective_forms_share_fact_key(self):
  a='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.'
  self.assertEqual(self.ev(a+' This ceasefire will take effect on July 2, 2026.',cease())[3]['fact_group']['key'],self.ev(a+' This ceasefire takes effect on July 2, 2026.',cease())[3]['fact_group']['key'])

class RealProgressCoverageTests(unittest.TestCase):
 ev=TemporalProgressTests.ev
 def test_frozen_knesset_vote_recognized_but_missing_date_abstains(self):
  # Verbatim quote from frozen development doc 3250b8d6, not an independent label.
  s='The 120-member Knesset voted in a preliminary reading on the proposal to disband itself, with 110 lawmakers supporting the measure and no votes cast against it or recorded abstentions.'
  e,r,d,tr=self.ev(s);self.assertEqual(d,[0,0]);self.assertNotIn('time',e)
  self.assertEqual(tr['support'].get('progress_candidate'),'advance')
  self.assertIn('event_time_unresolved',tr['support']['blockers'])
 def test_favorable_vote_requires_explicit_majority_not_just_voting(self):
  s='The 120-member Knesset voted in a preliminary reading on the proposal to disband itself, with 10 lawmakers supporting the measure and no votes cast against it or recorded abstentions.'
  self.assertIsNone(self.ev(s)[3]['support'].get('progress_candidate'))
 def test_pending_remaining_stages_do_not_erase_dated_completed_progress(self):
  a='The Knesset passed a preliminary dissolution bill on May 28, 2026.'
  self.assertEqual(self.ev(a+' This bill must still pass further stages before becoming law.')[2],[1,0])
