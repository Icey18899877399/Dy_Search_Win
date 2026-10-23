"""Behavioral regressions for two bounded comparison-only procedural templates."""
import copy
import importlib.util
import unittest

class MatchingV6Tests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('dynamic_retrieval.matching_v6'), 'V6 comparison extension missing')
        from dynamic_retrieval import matching_v6
        self.v6=matching_v6
        self.task={'question':'Israeli parliament dissolved by July 31?', 'cutoff':'2026-05-31T23:59:59Z'}
        self.elements={'subject':'Israeli Knesset','action':'gave initial approval to dissolution bill','time':'May 20, 2026','location':'Israel'}
        self.quote='On May 20, 2026, the Knesset gave initial approval to a bill to dissolve parliament.'

    def evaluate(self, quote=None, elements=None, task=None, context=None, rationale='Observed procedural development'):
        quote=self.quote if quote is None else quote
        return self.v6.evaluate(elements or self.elements,task or self.task,quote=quote,
                               context=quote if context is None else context,rationale=rationale)

    def test_completed_preliminary_approval_is_not_dissolution(self):
        elements=copy.deepcopy(self.elements);task=copy.deepcopy(self.task)
        score,trace=self.evaluate(elements=elements,task=task)
        self.assertGreaterEqual(score,.4)
        self.assertEqual(trace['relation'],'procedural_step')
        self.assertEqual(trace['stage'],'preliminary_approval')
        self.assertFalse(trace['establishes_outcome'])
        self.assertEqual(elements,self.elements);self.assertEqual(task,self.task)

    def test_frozen_explicit_submission_quote_is_only_procedural_context(self):
        quote='The Likud party of Prime Minister Benjamin Netanyahu submitted a proposal to dissolve the Israeli parliament on Wednesday, May 13, 2026, following threats of a coalition collapse.'
        elements={'subject':'Likud party of Prime Minister Benjamin Netanyahu', 'action':'submitted a proposal to dissolve the Israeli parliament','object':'the 25th Knesset','time':'Wednesday, May 13, 2026','location':'Israel'}
        score,trace=self.evaluate(quote,elements)
        self.assertGreaterEqual(score,.4)
        self.assertEqual(trace['stage'],'proposal_submission')
        self.assertFalse(trace['establishes_outcome'])

    def test_article_header_date_is_not_event_date(self):
        quote='Israel’s parliament has given initial approval to a bill to dissolve the Knesset, moving the country closer to a snap election.'
        score,trace=self.evaluate(quote,context='May 20, 2026\n'+quote)
        self.assertEqual(score,0.)
        self.assertIn('event_date_not_grounded_in_event_statement',trace['blockers'])

    def test_date_in_other_event_sentence_cannot_bind(self):
        context='On May 20, 2026, the Knesset hosted a ceremony. '+self.quote.replace('On May 20, 2026, ','')
        score,trace=self.evaluate(self.quote.replace('On May 20, 2026, ',''),context=context)
        self.assertEqual(score,0.)

    def test_forecast_conditional_negation_and_conflict_abstain(self):
        for quote in (
            'On May 20, 2026, the Knesset is expected to give initial approval to a bill to dissolve parliament.',
            'On May 20, 2026, if the Knesset gave initial approval to a bill to dissolve parliament, elections could follow.',
            'On May 20, 2026, the Knesset did not give initial approval to a bill to dissolve parliament.',
        ):
            self.assertEqual(self.evaluate(quote)[0],0.)
        self.assertEqual(self.evaluate(rationale='Reports of approval were denied and conflicting.')[0],0.)

    def test_past_cycle_future_date_and_fabricated_date_abstain(self):
        for date in ('May 20, 2025','June 20, 2026'):
            elements=copy.deepcopy(self.elements);elements['time']=date
            self.assertEqual(self.evaluate(self.quote.replace('May 20, 2026',date),elements)[0],0.)
        self.assertEqual(self.evaluate(self.quote.replace('May 20, 2026','May 19, 2026'))[0],0.)

    def test_wrong_parliament_or_missing_quote_binding_abstain(self):
        self.assertEqual(self.evaluate(self.quote.replace('Knesset','French parliament'))[0],0.)
        self.assertEqual(self.evaluate(context='Nothing here')[0],0.)

    def test_committee_stage_is_not_full_senate_confirmation(self):
        task={'question':'Will Kevin Warsh be confirmed as Fed Chair?','cutoff':'2026-04-30T23:59:59Z'}
        quote='On April 29, 2026, the Senate Banking Committee approved Kevin Warsh’s nomination as Federal Reserve Chair.'
        elements={'subject':'Kevin Warsh','action':'nomination approved','time':'April 29, 2026'}
        score,trace=self.evaluate(quote,elements,task)
        self.assertGreaterEqual(score,.4)
        self.assertEqual(trace['stage'],'committee_approval')
        self.assertEqual(trace['relation'],'procedural_step')
        self.assertFalse(trace['establishes_outcome'])
        self.assertEqual(self.evaluate(quote.replace('approved','is expected to approve'),elements,task)[0],0.)

    def test_full_senate_observation_has_distinct_stage(self):
        task={'question':'Will Kevin Warsh be confirmed as Fed Chair?','cutoff':'2026-04-30T23:59:59Z'}
        elements={'subject':'Kevin Warsh','action':'confirmed','time':'April 29, 2026'}
        quote='On April 29, 2026, the full Senate confirmed Kevin Warsh as Federal Reserve Chair.'
        score,trace=self.evaluate(quote,elements,task)
        self.assertGreaterEqual(score,.4)
        self.assertEqual(trace['stage'],'full_senate_confirmation_statement')
        self.assertFalse(trace['establishes_outcome'])
        self.assertEqual(self.evaluate(quote.replace('Kevin Warsh','Jerome Powell'),elements,task)[0],0.)

    def test_unrelated_nominee_and_scheduled_vote_abstain(self):
        task={'question':'Will Kevin Warsh be confirmed as Fed Chair?','cutoff':'2026-04-30T23:59:59Z'}
        elements={'subject':'Kevin Warsh','action':'vote scheduled','time':'April 29, 2026'}
        for quote in ('On April 29, 2026, the Senate Banking Committee scheduled a vote on Kevin Warsh as Federal Reserve Chair.',
                      'On April 29, 2026, the Senate Banking Committee approved Jerome Powell as Federal Reserve Chair.'):
            self.assertEqual(self.evaluate(quote,elements,task)[0],0.)

    def test_target_mentioned_in_other_role_does_not_ground_legislative_approval(self):
        quote='On May 20, 2026, the opposition party gave initial approval to a bill to dissolve the Knesset.'
        self.assertEqual(self.evaluate(quote)[0],0.)

    def test_office_and_dissolution_patient_bind_to_the_completed_action(self):
        task={'question':'Will Kevin Warsh be confirmed as Fed Chair?','cutoff':'2026-04-30T23:59:59Z'}
        elements={'subject':'Kevin Warsh','action':'nomination approved','time':'April 29, 2026'}
        quote='On April 29, 2026, the Senate Banking Committee approved Kevin Warsh nomination as Treasury Secretary, while a separate Federal Reserve Chair vacancy remained open.'
        self.assertEqual(self.evaluate(quote,elements,task)[0],0.)
        quote='On May 20, 2026, the Knesset gave initial approval to a bill to dissolve the French parliament.'
        self.assertEqual(self.evaluate(quote)[0],0.)

    def test_same_sentence_unrelated_event_date_does_not_ground_vote(self):
        quote='The Knesset gave initial approval to a bill to dissolve parliament after its opening ceremony on May 20, 2026.'
        self.assertEqual(self.evaluate(quote)[0],0.)

    def test_other_task_keeps_v5_decision(self):
        from dynamic_retrieval.matching_v5 import evaluate
        task={'question':'Will Trump visit China by April 30?','cutoff':'2026-04-17T23:59:59Z'}
        elements={'subject':'Trump','action':'visit','object':'China','time':'April 10, 2026'}
        quote='Trump visited China on April 10, 2026.'
        expected=evaluate(elements,task,quote=quote,context=quote,rationale='Observed')
        actual=self.v6.evaluate(elements,task,quote=quote,context=quote,rationale='Observed')
        self.assertEqual(actual,expected)

if __name__=='__main__':unittest.main()


