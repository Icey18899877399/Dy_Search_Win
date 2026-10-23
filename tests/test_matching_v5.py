import unittest
from dynamic_retrieval.matching import normalize_task
from dynamic_retrieval.matching_v5 import evaluate

def task(q):return dict(question=q,outcomes=['Yes','No'],cutoff='2026-08-28T23:59:59Z',matching_policy='typed_v5')
def check(q,e,quote,context='',rationale=''):
    return evaluate(e,task(q),quote=quote,context=context or quote,rationale=rationale)

class MatchingV5Tests(unittest.TestCase):
    def test_compound_announcement(self):
        t=normalize_task(task('US announces end of Iranian blockade by September 21, 2026?'))
        self.assertEqual(t['target_elements']['subject'],'US');self.assertEqual(t['target_elements']['action'],'announce_termination')
        self.assertEqual(t['target_elements']['time'],'September 21, 2026')
    def test_fed_entity_is_not_time(self):
        t=normalize_task(task('Will there be no change in Fed interest rates after the September 2026 meeting?'))
        self.assertEqual(t['target_elements']['subject'],'Federal Reserve');self.assertEqual(t['target_elements']['time'],'September 2026')
    def test_passive_and_unsupported(self):
        for q,verb in [('Will Trump be impeached by end of 2026?','impeach'),('Bab el-Mandeb Strait effectively closed by December 31?','close'),('Will Russia test a nuclear weapon by September 30 2026?','test'),('Will Reza Pahlavi lead Iran in 2026?','lead')]:
            self.assertEqual(normalize_task(task(q))['target_elements']['action'],verb)
        self.assertEqual(normalize_task(task('Something unpredictable?'))['task_parse']['status'],'unsupported')
    def test_wealth_tax_conditions(self):
        t=normalize_task(task('Billionaire one-time wealth tax passes in California election 2026?'))
        self.assertEqual(t['target_elements']['action'],'pass');self.assertEqual(t['target_elements']['location'],'California')
    def test_negated_agreement_is_related_not_completed(self):
        e=dict(subject='Iran',action='has not agreed to surrender enriched uranium',object='enriched uranium stockpile',time='August 27, 2026')
        s,tr=check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',e,'Iran has not agreed to surrender its enriched uranium stockpile.')
        self.assertGreaterEqual(s,.4);self.assertEqual(tr['relation'],'opposing_state');self.assertFalse(tr['establishes_outcome'])
    def test_third_party_or_different_stockpile_rejected(self):
        for subject,obj in [('Iraq','enriched uranium stockpile'),('Iran','missile stockpile')]:
            s,tr=check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',dict(subject=subject,action='agreed to surrender',object=obj,time='August 27, 2026'),subject+' agreed to surrender its '+obj+'.')
            self.assertEqual(s,0)
    def test_conflicting_claim_rejected(self):
        s,tr=check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',dict(subject='Iran',action='agreed to surrender',object='enriched uranium stockpile',time='August 27, 2026'),'Iran agreed in principle to surrender its enriched uranium.','Iran agreed in principle to surrender its enriched uranium. Iranian officials disputed the claim.','However Iranian officials publicly disputed the claims.')
        self.assertEqual(s,0);self.assertIn('conflicting_claims',tr['blockers'])
    def test_wrong_strait_pronoun(self):
        e=dict(subject='Bab el-Mandeb Strait',action='virtually closed',time='August 20, 2026')
        s,tr=check('Bab el-Mandeb Strait effectively closed by December 31?',e,'The strait has been virtually closed.','Oman and Iran discussed the Strait of Hormuz. The strait has been virtually closed.')
        self.assertEqual(s,0);self.assertIn('place_coreference_conflict',tr['blockers'])
    def test_named_strait_related_disruption(self):
        e=dict(subject='Bab el-Mandeb Strait transit',action='disrupted',time='July 2026')
        s,tr=check('Bab el-Mandeb Strait effectively closed by December 31?',e,'Transit through the Bab el-Mandeb Strait was disrupted.')
        self.assertGreaterEqual(s,.4);self.assertEqual(tr['relation'],'disruption_context');self.assertFalse(tr['establishes_outcome'])
    def test_prediction_and_bets_are_not_facts(self):
        e=dict(subject='Federal Reserve',action='leave interest rates unchanged',object='target federal funds rate',time='September 2026')
        s,tr=check('Will there be no change in Fed interest rates after the September 2026 meeting?',e,'Policymakers are likely to leave rates unchanged.',rationale='Traders added to bets for no change.')
        self.assertEqual(s,0);self.assertIn('forecast_or_market_basis',tr['blockers'])
    def test_submission_is_not_impeachment(self):
        e=dict(subject='Al Green',action='filed articles of impeachment against',object='President Trump',time='August 24, 2026')
        s,tr=check('Will Trump be impeached by end of 2026?',e,'Al Green filed articles of impeachment against President Trump.')
        self.assertGreaterEqual(s,.4);self.assertEqual(tr['relation'],'procedural_step');self.assertFalse(tr['establishes_outcome'])
    def test_wrong_impeachment_target(self):
        e=dict(subject='Al Green',action='filed articles of impeachment against',object='President Biden',time='August 24, 2026')
        s,tr=check('Will Trump be impeached by end of 2026?',e,'Al Green filed articles of impeachment against President Biden.')
        self.assertEqual(s,0)
    def test_certification_date_separate_from_election(self):
        e=dict(subject='2026 Billionaire Tax Act',action='certified for ballot',object='California ballot',time='certified June 25, 2026; election November 3, 2026',location='California')
        s,tr=check('Billionaire one-time wealth tax passes in California election 2026?',e,'California certified the one-time billionaire wealth tax for the November 3, 2026 ballot on June 25, 2026.')
        self.assertGreaterEqual(s,.4);self.assertEqual(tr['time_check']['event_interval'],['2026-06-25','2026-06-25']);self.assertEqual(tr['relation'],'qualification_step')
    def test_foreign_election_not_rewritten(self):
        e=dict(subject='billionaire wealth tax',action='certified for ballot',time='June 25, 2026',location='Washington')
        s,tr=check('Billionaire one-time wealth tax passes in California election 2026?',e,'Washington certified its billionaire wealth tax for the ballot.')
        self.assertEqual(s,0)
    def test_future_and_relative_times_fail_closed(self):
        for when in ['September 2, 2026','2027-01-01','Monday','March 2025']:
            s,tr=check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',dict(subject='Iran',action='agreed to surrender',object='enriched uranium stockpile',time=when),'Iran agreed to surrender enriched uranium.')
            self.assertEqual(s,0)
    def test_range_time_and_airspace_scope(self):
        q='Israel closes its airspace by September 30?'
        e=dict(subject='Israel',action='closure of Israeli airspace',time='March 1-2, 2026')
        s,tr=check(q,e,'Israel announced closure of all civilian airspace.')
        self.assertGreaterEqual(s,.4);self.assertEqual(tr['time_check']['event_interval'],['2026-03-01','2026-03-02'])
        s,tr=check(q,e,'SKY Express cancelled its flights from Athens due to closure of Israeli airspace.')
        self.assertEqual(s,0);self.assertIn('closure_scope_unverified',tr['blockers'])
    def test_unsupported_never_passes_actor_only(self):
        s,tr=check('Something unpredictable?',dict(subject='Something unpredictable',time='August 20, 2026'),'Something unpredictable happened.')
        self.assertEqual(s,0);self.assertIn('unsupported_task',tr['blockers'])

    def test_actor_cannot_be_invented_by_annotation(self):
        e=dict(subject='Iran',action='agreed to surrender',object='enriched uranium stockpile',time='August 27, 2026')
        score,trace=check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',e,'Iraq agreed to surrender its enriched uranium stockpile.')
        self.assertEqual(score,0);self.assertIn('actor_not_grounded',trace['blockers'])
    def test_third_party_request_is_not_irans_agreement(self):
        e=dict(subject='Iran',action='agreed to surrender',object='enriched uranium stockpile',time='August 27, 2026')
        score,trace=check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',e,'The United States urged Iran to surrender its enriched uranium stockpile.')
        self.assertEqual(score,0);self.assertIn('claim_relation_not_grounded',trace['blockers'])
    def test_foreign_body_must_not_borrow_quote_entity(self):
        e=dict(subject='Iran',action='agreed to surrender',object='enriched uranium stockpile',time='August 27, 2026')
        score,trace=check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',e,'Iraq agreed to surrender its enriched uranium stockpile.','Iran held talks. Iraq agreed to surrender its enriched uranium stockpile.')
        self.assertEqual(score,0)

    def test_nuclear_actor_requires_source_grounding(self):
        e=dict(subject='Russia',action='tested',object='nuclear weapon',time='August 20, 2026')
        score,trace=check('Will Russia test a nuclear weapon by September 30 2026?',e,'China tested a nuclear weapon on August 20, 2026.')
        self.assertEqual(score,0)
    def test_v5_preserves_input_elements(self):
        from copy import deepcopy
        e=dict(subject='Iran',action='has not agreed to surrender',object='enriched uranium stockpile',time='August 27, 2026')
        before=deepcopy(e)
        check('Iran agrees to surrender enriched uranium stockpile by December 31, 2026?',e,'Iran has not agreed to surrender enriched uranium.')
        self.assertEqual(e,before)

    def test_legacy_before_after_boundaries_preserved(self):
        for operator,when in [('after','April 30, 2026'),('before','May 1, 2026')]:
            q='Will Russia capture Kyiv '+operator+' May 1, 2026?'
            e=dict(subject='Russia',action='captured',object='Kyiv',time=when)
            score,trace=check(q,e,'Russia captured Kyiv.')
            self.assertEqual(score,0)

if __name__=='__main__':unittest.main()
