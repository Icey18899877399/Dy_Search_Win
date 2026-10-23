import unittest
from copy import deepcopy
from dynamic_retrieval.matching import typed_relevance, normalize_task
from dynamic_retrieval.core import fact_key

def task(q):
    return dict(question=q,outcomes=['Yes','No'],cutoff='2026-05-15T23:59:59Z',matching_policy='typed_v4')

class SemanticV4Tests(unittest.TestCase):
    def test_opposite_disarmament_is_relevant_without_mutating_fact(self):
        t=task('Will Hamas agree to disarm by June 30?')
        f=dict(subject='hamas',action='refuses to disarm and rejects ceasefire disarmament requirement')
        before=deepcopy(f);identity=fact_key(f)
        score,trace=typed_relevance(f,t)
        self.assertGreaterEqual(score,.4)
        self.assertIn('object',trace['matched'])
        self.assertEqual(f,before);self.assertEqual(fact_key(f),identity)
        self.assertEqual(trace['relation'],'same_event_opposing_or_related_statement')

    def test_military_alias_and_progress_not_completion(self):
        t=task('Will Russia capture Kostyantynivka by May 31?')
        f=dict(subject='russian forces',action='advanced near and are penetrating into',object='kostyantynivka',time='as of early may 2026')
        score,trace=typed_relevance(f,t)
        self.assertGreaterEqual(score,.4)
        self.assertEqual(trace['relation'],'military_progress_not_capture')
        self.assertIn('subject',trace['matched'])

    def test_other_settlement_rejected_even_with_actor_and_time(self):
        t=task('Will Russia capture Kostyantynivka by May 31?')
        f=dict(subject='russian forces',action='captured',object='illinivka near kostyantynivka',time='April 29, 2026')
        score,trace=typed_relevance(f,t)
        self.assertEqual(score,0)
        self.assertIn('object_mismatch',trace['blockers'])

    def test_wrong_actor_and_minister_not_country(self):
        for q,f in [
            ('Will Hamas agree to disarm by June 30?',dict(subject='hezbollah',action='refuses to disarm',time='April 2026')),
            ('Ukraine recognizes Russian sovereignty over its territory by December 31, 2026?',dict(subject="ukraine's foreign minister",action='recognize',object='Russian sovereignty over its territory',time='April 2026')),
        ]:
            score,trace=typed_relevance(f,task(q))
            self.assertEqual(score,0);self.assertIn('subject_mismatch',trace['blockers'])

    def test_released_note_cross_field_projection(self):
        t=task('Epstein suicide note released by May 31?')
        f=dict(subject='jeffrey epstein',action='alleged suicide note released')
        score,trace=typed_relevance(f,t)
        self.assertGreaterEqual(score,.4)
        self.assertIn('object',trace['matched'])
        f['subject']='some other person'
        self.assertEqual(typed_relevance(f,t)[0],0)

    def test_alias_does_not_turn_attack_into_invasion(self):
        t=task('Will the U.S. invade Iran before 2027?')
        f=dict(subject='united states',action='launched airstrikes',object='iran',time='April 2026')
        self.assertEqual(typed_relevance(f,t)[0],0)

    def test_explicit_event_time_outside_interval_blocks(self):
        t=task('Will Hamas agree to disarm by June 30?')
        for when in ('April 2025','July 2026','May 20, 2026','2027-01-01'):
            f=dict(subject='hamas',action='refused to disarm',time=when)
            score,trace=typed_relevance(f,t)
            self.assertEqual(score,0,when)
            self.assertIn('event_time_outside_interval',trace['blockers'])

    def test_unknown_time_is_not_invented_from_publication(self):
        f=dict(subject='hamas',action='refused to disarm',time='last Wednesday')
        score,trace=typed_relevance(f,task('Will Hamas agree to disarm by June 30?'))
        self.assertGreaterEqual(score,.4);self.assertNotIn('time',trace['matched'])
        self.assertEqual(trace['time_check']['status'],'unknown')

    def test_before_year_uses_deadline_not_year_equality(self):
        t=task('Will the U.S. invade Iran before 2027?')
        f=dict(subject='United States',action='invade',object='Iran',time='April 2026')
        score,trace=typed_relevance(f,t)
        self.assertEqual(score,1)
        self.assertEqual(trace['time_check']['operator'],'before')
        self.assertEqual(trace['time_check']['deadline'],'2027-01-01')

    def test_legacy_policy_unchanged(self):
        t=task('Will Hamas agree to disarm by June 30?');t['matching_policy']='typed_v3'
        self.assertEqual(typed_relevance(dict(subject='hamas',action='refuses to disarm'),t)[0],.25)

    def test_support_and_raw_elements_unchanged_through_extraction(self):
        from dynamic_retrieval.evidence import extract
        t=task('Will Hamas agree to disarm by June 30?')
        t['target_elements']={'subject':'Hamas'}
        ann={'d':dict(reviewed=True,elements={'subject':'hamas','action':'refused to disarm'},support=[-1,1],quote='Hamas refused to disarm.')}
        d=dict(id='d',text=ann['d']['quote'])
        row=extract(d,t,ann)
        self.assertEqual(row['support'],[-1,1])
        self.assertEqual(row['elements'],ann['d']['elements'])
        self.assertGreaterEqual(row['relevance'],.4)
        self.assertEqual(row['matching_trace']['policy'],'typed_v4')

    def test_location_cannot_be_replaced_by_subject_and_action(self):
        t=task('Will Trump and Putin meet next in Russia?')
        f=dict(subject='Trump and Putin',action='meet',location='Beijing',time='April 2026')
        score,trace=typed_relevance(f,t)
        self.assertEqual(score,0)
        self.assertIn('location_mismatch',trace['blockers'])
        self.assertNotEqual(trace['target'].get('time'),'Russia')

    def test_end_of_year_target_still_checks_old_event(self):
        t=task('Will China invade Taiwan by end of 2026?')
        f=dict(subject='China',action='invade',object='Taiwan',time='April 2025')
        score,trace=typed_relevance(f,t)
        self.assertEqual(score,0)
        self.assertIn('event_time_outside_interval',trace['blockers'])

    def test_other_disarming_party_cannot_be_projected_away(self):
        t=task('Will Hamas agree to disarm by June 30?')
        for action,obj in [('calls on Israel to disarm','Israeli disarmament'),
                           ('demands disarmament of Israel','disarmament of Israel')]:
            f=dict(subject='Hamas',action=action,object=obj,time='April 2026')
            score,trace=typed_relevance(f,t)
            self.assertEqual(score,0)
            self.assertEqual(trace['comparison_elements']['object'],obj)

    def test_unambiguous_old_iso_dates_block(self):
        t=task('Will Hamas agree to disarm by June 30?')
        for when in ('2025-04','2025-04-20T00:00:00Z'):
            f=dict(subject='Hamas',action='refused to disarm',time=when)
            score,trace=typed_relevance(f,t)
            self.assertEqual(score,0)
            self.assertEqual(trace['time_check']['status'],'outside')

    def test_missing_object_does_not_hide_third_party_in_action(self):
        t=task('Will Hamas agree to disarm by June 30?')
        for action in ('demands disarmament of Israel','demands Israel disarm'):
            score,trace=typed_relevance(dict(subject='Hamas',action=action,time='April 2026'),t)
            self.assertEqual(score,0)
            self.assertNotIn('object',trace['comparison_elements'])
