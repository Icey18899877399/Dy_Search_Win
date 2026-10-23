"""Independent adversarial contract checks using the three frozen task inputs."""
import copy
import json
from pathlib import Path
import unittest

try:
    from dynamic_retrieval import patent_evidence_v2 as policy
except ImportError:
    from dynamic_retrieval import patent_evidence as policy


INPUTS = Path(__file__).resolve().parent / 'fixtures/task-contracts'


def task(identifier, cutoff=None):
    value = json.loads((INPUTS / f'{identifier}.json').read_text(encoding='utf-8'))
    if cutoff is not None:
        value['cutoff'] = cutoff
    return value


def evaluate(text, target, quote=None, raw=None, annotation=None):
    return policy.evaluate(raw or {}, target, quote=text if quote is None else quote,
                           text=text, original_support=[-1, 1], annotation=annotation)


class IndependentSemanticsV2ReviewTests(unittest.TestCase):
    def test_real_knesset_description_sets_cycle_start_without_mutating_task(self):
        target = task(2354063)
        before = copy.deepcopy(target)
        effective = policy.effective_task(target)
        self.assertEqual(target, before)
        self.assertEqual(effective.get('_patent_contract', {}).get('time_interval', {}).get('start'), '2026-01-27')
        self.assertEqual(evaluate('The Knesset was dissolved on May 28, 2026.', target)[2], [1, -1])

    def test_before_cycle_dissolution_is_not_yes_or_no(self):
        self.assertEqual(evaluate('The Knesset was dissolved on January 26, 2026.', task(2354063))[2], [0, 0])

    def test_title_date_cannot_supply_undated_body_event(self):
        text = 'May 28, 2026: Economic update\nThe Knesset was dissolved.'
        row = evaluate(text, task(2354063), quote='The Knesset was dissolved.',
                       raw={'subject': 'Knesset', 'action': 'dissolved', 'time': 'May 28, 2026'})
        self.assertEqual(row[2], [0, 0])
        self.assertNotEqual(row[0].get('time'), '2026-05-28')

    def test_same_sentence_other_event_date_cannot_date_dissolution(self):
        text = 'The Knesset was dissolved after an opening ceremony on May 28, 2026.'
        self.assertEqual(evaluate(text, task(2354063))[2], [0, 0])

    def test_raw_annotation_cannot_restore_date_rejected_as_unrelated(self):
        text = 'The Knesset was dissolved after an opening ceremony on May 28, 2026.'
        row = evaluate(text, task(2354063), raw={'subject': 'Knesset', 'action': 'dissolved', 'time': 'May 28, 2026'})
        self.assertEqual(row[2], [0, 0])

    def test_wrongly_attributed_partial_quote_cannot_become_yes(self):
        text = 'The opposition falsely claimed that the Knesset was dissolved on May 28, 2026.'
        self.assertEqual(evaluate(text, task(2354063), quote='the Knesset was dissolved on May 28, 2026.')[2], [0, 0])

    def test_old_cycle_denial_does_not_poison_current_dissolution(self):
        witness = 'The Knesset was dissolved on May 28, 2026.'
        text = witness + ' Officials denied that the Knesset was dissolved on May 28, 2025.'
        self.assertEqual(evaluate(text, task(2354063), quote=witness)[2], [1, -1])

    def test_closed_failure_waits_until_eastern_deadline(self):
        text = 'The Knesset had not been dissolved by July 31, 2026.'
        self.assertEqual(evaluate(text, task(2354063, '2026-08-01T02:00:00Z'))[2], [0, 0])
        self.assertEqual(evaluate(text, task(2354063, '2026-08-01T04:01:00Z'))[2], [-1, 1])

    def test_real_ceasefire_description_accepts_agreement_before_later_start(self):
        text = 'Russia and Ukraine publicly announced a mutually agreed general ceasefire agreement on April 28, 2026, effective July 2, 2026.'
        row = evaluate(text, task(1171663))
        self.assertEqual(row[2], [1, -1])
        self.assertEqual(row[0].get('time'), '2026-04-28')

    def test_informal_and_black_sea_agreements_are_neutral(self):
        for qualifier in ['informal general', 'Black Sea', 'energy infrastructure', 'humanitarian']:
            with self.subTest(qualifier=qualifier):
                text = f'Russia and Ukraine publicly announced a mutually agreed {qualifier} ceasefire agreement on April 28, 2026.'
                self.assertEqual(evaluate(text, task(1171663))[2], [0, 0])

    def test_announcement_of_future_agreement_is_not_completed_agreement(self):
        text = 'Russia and Ukraine publicly announced on April 28, 2026 that they will sign a mutually agreed general ceasefire agreement on July 2, 2026.'
        self.assertEqual(evaluate(text, task(1171663))[2], [0, 0])

    def test_general_pause_not_implied_by_mutual_energy_agreement(self):
        text = 'Russia and Ukraine publicly announced a mutually agreed ceasefire agreement on April 28, 2026, covering only energy infrastructure.'
        self.assertEqual(evaluate(text, task(1171663))[2], [0, 0])

    def test_count_is_not_closed_at_original_april_cutoff(self):
        text = "XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts."
        self.assertEqual(evaluate(text, task(1423716))[2], [0, 0])
        self.assertEqual(evaluate(text, task(1423716, '2026-05-02T00:00:00Z'))[2], [1, -1])

    def test_other_person_month_daily_count_cannot_assign_direction(self):
        target = task(1423716, '2026-05-02T00:00:00Z')
        for text in [
            "XTracker's final Post Counter for Alice Smith for the entire month of April 2026 was 1010 posts.",
            "XTracker's final Post Counter for Elon Musk for the entire month of March 2026 was 1010 posts.",
            "XTracker's final Post Counter for Elon Musk on April 15, 2026 was 1010 posts.",
            'Elon Musk posted 1010 tweets including all replies during the entire month of April 2026.',
        ]:
            with self.subTest(text=text):
                self.assertEqual(evaluate(text, target)[2], [0, 0])

    def test_background_old_count_cannot_replace_current_final_count(self):
        target = task(1423716, '2026-05-02T00:00:00Z')
        witness = "XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1040 posts."
        text = 'Elon Musk posted 1010 tweets during March 2026. ' + witness
        self.assertEqual(evaluate(text, target, quote=witness)[2], [-1, 1])

    def test_scope_negation_and_asserted_full_month_counts_keep_exact_facts(self):
        target = task(1423716, '2026-05-02T00:00:00Z')
        rows = []
        for value in (1000, 1039):
            text = f"XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was {value} posts."
            rows.append(evaluate(text, target))
        self.assertEqual([row[2] for row in rows], [[1, -1], [1, -1]])
        self.assertNotEqual(rows[0][3]['fact_group']['key'], rows[1][3]['fact_group']['key'])

    def test_annotation_and_raw_task_remain_unchanged_while_direction_changes(self):
        target = task(2354063)
        annotation = {'factual_status': 'reported', 'time_scope': 'target_compatible', 'support': [-1, 1], 'reviewed': False}
        raw = {'subject': 'model parliament phrase', 'action': 'model paraphrase'}
        before = copy.deepcopy((target, annotation, raw))
        row = evaluate('The Knesset was dissolved on May 28, 2026.', target, raw=raw, annotation=annotation)
        self.assertEqual(row[2], [1, -1])
        self.assertEqual((target, annotation, raw), before)
        self.assertEqual(row[3]['raw_elements'], raw)
        self.assertEqual(row[3]['original_support'], [-1, 1])

    def test_not_true_prefix_cannot_become_completed_positive(self):
        text = 'It is not true that the Knesset was dissolved on May 28, 2026.'
        self.assertEqual(evaluate(text, task(2354063))[2], [0, 0])

    def test_negated_mutual_ceasefire_does_not_become_positive(self):
        text = 'Russia and Ukraine publicly announced that they have not mutually agreed to a general ceasefire on April 29, 2026.'
        self.assertEqual(evaluate(text, task(1171663))[2], [0, 0])

    def test_tracker_named_but_explicitly_wrong_metric_is_not_valid_count(self):
        text = "XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts, including all ordinary replies."
        self.assertEqual(evaluate(text, task(1423716, '2026-05-02T00:00:00Z'))[2], [0, 0])

    def test_actual_agreement_participants_must_be_target_participants(self):
        text = 'Russia and Ukraine welcomed the news that Armenia and Azerbaijan publicly announced a mutually agreed general ceasefire on April 29, 2026.'
        self.assertEqual(evaluate(text, task(1171663))[2], [0, 0])

    def test_count_publisher_not_incidental_person_mention(self):
        text = "Elon Musk said XTracker's final Post Counter for Alice Smith for the entire month of April 2026 was 1010 posts."
        self.assertEqual(evaluate(text, task(1423716, '2026-05-02T00:00:00Z'))[2], [0, 0])

    def test_dissolution_date_not_first_incidental_date(self):
        text = 'After a ceremony on May 27, 2026, the Knesset was dissolved on May 28, 2026.'
        row = evaluate(text, task(2354063))
        self.assertEqual(row[2], [1, -1])
        self.assertEqual(row[0].get('time'), '2026-05-28')

    def test_matching_count_correction_blocks_positive(self):
        witness = "XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts."
        correction = ' Correction: the final Post Counter for Elon Musk for the entire month of April 2026 was 1040 posts.'
        self.assertEqual(evaluate(witness + correction, task(1423716, '2026-05-02T00:00:00Z'), quote=witness)[2], [0, 0])

    def test_unrelated_month_count_correction_does_not_poison_count(self):
        witness = "XTracker's final Post Counter for Elon Musk for the entire month of April 2026 was 1010 posts."
        correction = ' Officials denied that the Post Counter for Elon Musk for the entire month of March 2026 was 1040 posts.'
        self.assertEqual(evaluate(witness + correction, task(1423716, '2026-05-02T00:00:00Z'), quote=witness)[2], [1, -1])

    def test_distinct_procedural_stages_do_not_merge_exact_fact_keys(self):
        rows = [evaluate(text, task(2354063)) for text in [
            'The Knesset proposed a dissolution bill on May 28, 2026.',
            'The Knesset passed the first reading of a dissolution bill on May 28, 2026.',
            'The Knesset passed the second reading of a dissolution bill on May 28, 2026.',
        ]]
        self.assertEqual([row[2] for row in rows], [[0, 0], [0, 0], [0, 0]])
        self.assertEqual(len({tuple(row[3]['fact_group']['key']) for row in rows}), 3)

    def test_witness_offsets_and_text_reference_actual_source_after_semicolon(self):
        text = 'Economic note; The Knesset was dissolved on May 28, 2026.'
        row = evaluate(text, task(2354063))
        self.assertEqual(row[2], [1, -1])
        for witnesses in row[3]['normalization']['witnesses'].values():
            for witness in witnesses:
                self.assertEqual(witness['text'], text[witness['start']:witness['end']])

    def test_invisible_count_definition_cannot_authorize_generic_total(self):
        target = task(1423716, '2026-05-02T00:00:00Z')
        target['observed_at'] = '2026-05-03T00:00:00Z'
        text = 'Elon Musk posted a final total of 1010 tweets for the entire month of April 2026.'
        row = evaluate(text, target)
        self.assertFalse(row[3]['structured_contract']['description_cutoff_visible'])
        self.assertEqual(row[2], [0, 0])

    def test_neutral_denial_preserves_different_action_from_completed_assertion(self):
        examples = [
            (task(2354063), 'The Knesset was dissolved on May 28, 2026.',
             'Officials denied that the Knesset was dissolved on May 28, 2026.'),
            (task(1171663), 'Russia and Ukraine publicly announced a mutually agreed general ceasefire on April 29, 2026.',
             'Russia and Ukraine publicly announced that they have not mutually agreed to a general ceasefire on April 29, 2026.'),
        ]
        for target, positive, denied in examples:
            with self.subTest(denied=denied):
                yes = evaluate(positive, target)
                neutral = evaluate(denied, target)
                self.assertEqual(yes[2], [1, -1])
                self.assertEqual(neutral[2], [0, 0])
                self.assertNotEqual(neutral[0].get('action'), yes[0].get('action'))
                self.assertNotEqual(neutral[3]['fact_group']['key'], yes[3]['fact_group']['key'])

    def test_real_platform_owner_is_not_the_person_posting(self):
        text = "Melania Trump used Elon Musk's X, the site formally known as Twitter, to post her thoughts on Monday."
        row = evaluate(text, task(1423716), raw={'subject': 'Melania Trump', 'action': 'post'})
        self.assertNotEqual(row[0].get('subject'), 'elon musk')
        self.assertLess(row[1], 0.5)
        self.assertEqual(row[2], [0, 0])

    def test_daily_date_is_not_coarsened_to_target_month_for_admission(self):
        text = 'President Cyril Ramaphosa’s spokesperson, Vincent Magwenya, has delivered a sharp response to South Africa-born tech billionaire Elon Musk, after the Starlink owner hurled expletives at a senior diplomat on X (Twitter) on 12 April 2026.'
        row = evaluate(text, task(1423716), raw={'subject': 'Elon Musk', 'time': '12 April 2026'})
        self.assertNotEqual(row[0].get('time'), '2026-04')
        self.assertLess(row[1], 0.5)

    def test_missing_space_after_period_does_not_merge_distinct_event_sentences(self):
        text = 'On May 28, 2026, France held a ceremony.The Knesset was dissolved.'
        row = evaluate(text, task(2354063), quote='The Knesset was dissolved.')
        self.assertEqual(row[2], [0, 0])
        self.assertNotEqual(row[0].get('time'), '2026-05-28')

    def test_real_different_events_do_not_become_same_participant_only_fact(self):
        texts = [
            'Turkiye is making efforts to revive negotiations between Russia and Ukraine and bring together the leaders of the warring sides, Turkish President Recep Tayyip Erdogan has told NATO Secretary-General Mark Rutte.',
            "The Korea International Trade Association (KITA) will hold a seminar on trade with Russia for the first time since 2022 due to the country's war on Ukraine.",
            'Kherson was the scene of heavy fighting during the Russian invasion of Ukraine in 2022, and it was the first major city to fall to Russian forces.',
        ]
        admitted_keys = []
        for text in texts:
            with self.subTest(text=text):
                row = evaluate(text, task(1171663))
                self.assertEqual(row[2], [0, 0])
                if row[1] >= 0.5:
                    self.assertTrue(row[0].get('action'), 'Admitted target participant pair must describe its actual source action')
                    admitted_keys.append(tuple(row[3]['fact_group']['key']))
        self.assertEqual(len(set(admitted_keys)), len(admitted_keys))

    def test_bounded_bilateral_talks_retain_real_participants_and_stage(self):
        text = 'Russia and Ukraine held ceasefire talks on April 28, 2026.'
        row = evaluate(text, task(1171663))
        self.assertEqual(row[0].get('subject'), 'russia')
        self.assertEqual(row[0].get('object'), 'ukraine')
        self.assertTrue(row[0].get('action'))
        self.assertEqual(row[0].get('time'), '2026-04-28')
        self.assertGreaterEqual(row[1], 0.5)
        self.assertEqual(row[2], [0, 0])

    def test_real_month_abbreviation_and_us_initials_keep_complete_sentence(self):
        text = "U.S.-led talks to end Europe's deadliest conflict since World War II have stalled since the Iran war erupted on Feb. 28, and Russian and Ukrainian negotiators have not met since February in Geneva."
        row = evaluate(text, task(1171663))
        self.assertEqual(row[3]['normalization']['assertion']['text'], text)
        self.assertEqual(row[2], [0, 0])


if __name__ == '__main__':
    unittest.main()
