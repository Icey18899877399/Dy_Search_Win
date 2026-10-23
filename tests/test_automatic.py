import importlib
import unittest

from dynamic_retrieval.evidence import extract, prepare_task


QUESTIONS = {
    'regime': 'Will the Iranian regime fall by June 30?',
    'nomination': 'Will Matt Gaetz win the 2028 Republican presidential nomination?',
    'president': 'Will Élisabeth Borne win the 2027 French presidential election?',
    'nobel': 'Will UNRWA win the Nobel Peace Prize in 2026?',
    'pm': 'Will Ayelet Shaked be the next Prime Minister of Israel?',
}


class AutomaticRuleTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('dynamic_retrieval.automatic')
        except ModuleNotFoundError:
            self.fail('Missing automatic deterministic rules')

    def task(self, category):
        base = dict(question=QUESTIONS[category], outcomes=['Yes', 'No'])
        return prepare_task(dict(base, **self.module().automatic_rules(base)))

    def support(self, category, text):
        return extract(dict(id='d1', title='', text=text), self.task(category))['support']

    def test_directional_features_are_category_specific(self):
        cases = [
            ('regime', 'The Iranian regime has collapsed.', [1, -1]),
            ('regime', 'The Iranian regime remains in power.', [-1, 1]),
            ('nomination', 'Matt Gaetz announced his candidacy for the Republican presidential nomination.', [1, -1]),
            ('nomination', 'Matt Gaetz withdrew from the presidential race.', [-1, 1]),
            ('president', 'Élisabeth Borne won the French presidential election.', [1, -1]),
            ('president', 'Élisabeth Borne was disqualified from the presidential election.', [-1, 1]),
            ('nobel', 'UNRWA was nominated for the Nobel Peace Prize.', [1, -1]),
            ('nobel', 'UNRWA was stripped of the Nobel Peace Prize.', [-1, 1]),
            ('pm', 'Ayelet Shaked was appointed Prime Minister of Israel.', [1, -1]),
            ('pm', 'Ayelet Shaked withdrew from the race for Prime Minister of Israel.', [-1, 1]),
        ]
        for category, text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(self.support(category, text), want)

    def test_speculation_conflict_negation_and_other_entities_abstain(self):
        cases = [
            ('nobel', 'UNRWA could win the Nobel Peace Prize.'),
            ('nobel', 'UNRWA was not nominated for the Nobel Peace Prize.'),
            ('nobel', 'UNRWA was nominated for the Nobel Peace Prize. UNRWA was stripped of the Nobel Peace Prize.'),
            ('nomination', 'Matt Gaetz praised John Smith, who won the Republican presidential nomination.'),
            ('president', 'Élisabeth Borne was delighted by the French presidential election.'),
            ('regime', 'The Iranian regime says the Syrian regime has collapsed.'),
            ('pm', 'Ayelet Shaked said another candidate was appointed Prime Minister of Israel.'),
            ('nobel', 'The report denied that UNRWA won the Nobel Peace Prize.'),
            ('nomination', 'Matt Gaetz announced his candidacy for governor.'),
        ]
        for category, text in cases:
            with self.subTest(text=text):
                self.assertEqual(self.support(category, text), [0, 0])

    def test_patterns_are_whitelisted_and_policy_does_not_claim_outcome_truth(self):
        task = dict(question=QUESTIONS['nobel'])
        rules = self.module().automatic_rules(task)
        self.assertEqual(set(rules), {'target_elements', 'element_aliases', 'positive_patterns', 'negative_patterns'})
        self.assertNotIn('time', rules['target_elements'])
        policy = self.module().describe_automatic_policy(task)
        self.assertEqual(policy['category'], 'nobel_peace_prize')
        self.assertEqual(policy['support_semantics'], 'mechanical_directional_features_not_outcome_truth')

    def test_unknown_task_rejected(self):
        with self.assertRaises(ValueError):
            self.module().automatic_rules(dict(question='Will Bitcoin exceed 100000?'))


if __name__ == '__main__':
    unittest.main()
