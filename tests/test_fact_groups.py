import copy
import importlib.util
import unittest


class FactGroupingTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec('dynamic_retrieval.fact_groups')
        self.assertIsNotNone(spec, 'Conservative fact grouping module is not implemented')
        from dynamic_retrieval import fact_groups
        self.f = fact_groups

    def row(self, id='a', source='wire-a', **changes):
        row = dict(id=id, source_id=source, published_at='2026-04-10T12:00:00Z',
            elements=dict(subject='United States', action='signed', object='agreement',
                          time='April 10, 2026', location='Paris'), support=[1,-1],
            quote='United States signed agreement in Paris on April 10, 2026.',
            text='United States signed agreement in Paris on April 10, 2026.')
        row.update(changes)
        return row

    def test_safe_spelling_date_alias_grouping_retains_raw_values(self):
        a=self.row(); b=self.row('b','wire-b')
        b.update(elements=dict(subject='U.S.',action='  SIGNED ',object='agreement',time='2026-04-10',location='Paris'),
                 text='U.S. SIGNED agreement in Paris on 2026-04-10.', quote='U.S. SIGNED agreement in Paris on 2026-04-10.')
        rows=[a,b]; saved=copy.deepcopy(rows)
        report=self.f.group_facts(rows)
        self.assertEqual(len(report['groups']),1)
        self.assertEqual(self.f.independent_fact_weights(rows,.5),{'a':1.,'b':.5})
        self.assertEqual(rows,saved)
        self.assertEqual(self.f.row_key(a),self.f.row_key(b))
        self.assertEqual(report,self.f.group_facts(list(reversed(rows))))
        self.assertTrue(report['groups'][0]['eligible'])

    def test_missing_time_or_location_stay_separate_even_when_identical(self):
        for field in ('subject','action','object','time','location'):
            a=self.row(); b=self.row('b'); del a['elements'][field]; del b['elements'][field]
            self.assertEqual(self.f.independent_fact_weights([a,b],.5),{'a':1.,'b':1.})

    def test_ungrounded_element_or_unbound_quote_cannot_coalesce(self):
        for changes in ({'quote':'fabricated'}, {'text':'unrelated'},
                        {'elements':dict(subject='United States', action='rejected',object='agreement',time='April 10, 2026',location='Paris')}):
            a=self.row(**changes); b=copy.deepcopy(a); b['id']='b'
            self.assertNotEqual(self.f.row_key(a),self.f.row_key(b))

    def test_contradiction_and_qualified_facts_remain_distinct(self):
        a=self.row(); b=self.row('b',support=[-1,1]); c=self.row('c')
        c['elements']['action']='conditionally signed'; c['quote']=c['text']='United States conditionally signed agreement in Paris on April 10, 2026.'
        self.assertEqual(len(self.f.group_facts([a,b,c])['groups']),3)

    def test_same_source_duplicates_have_zero_additional_weight(self):
        rows=[self.row('a'),self.row('b'),self.row('c','wire-b'),self.row('d','wire-c')]
        self.assertEqual(self.f.independent_fact_weights(rows,.5),{'a':1.,'b':0.,'c':.5,'d':.25})
        group=self.f.group_facts(rows)['groups'][0]
        self.assertEqual(group['same_source_duplicates'],{'wire-a':['b']})
        self.assertEqual(group['independent_source_count'],3)

    def test_unknown_sources_do_not_claim_independence(self):
        for source in ('',None):
            rows=[self.row('a',source),self.row('b',source)]
            self.assertEqual(len(self.f.group_facts(rows)['groups']),2)

    def test_date_precision_and_uncertainty_are_preserved(self):
        for value in ('April 2026','before April 10, 2026','April 10, 2026 or later','2026-04-10T12:00:00Z'):
            a=self.row(); b=self.row('b'); b['elements']['time']=value
            b['text']=b['quote']='United States signed agreement in Paris on '+value+'.'
            self.assertNotEqual(self.f.row_key(a),self.f.row_key(b))
        a=self.row(); b=self.row('b'); a['elements']['time']=b['elements']['time']='unknown'
        a['text']=a['quote']=b['text']=b['quote']='United States signed agreement in Paris on unknown.'
        self.assertNotEqual(self.f.row_key(a),self.f.row_key(b))

    def test_hidden_qualifier_cannot_be_erased_by_same_elements(self):
        a=self.row(); b=self.row('b')
        b['text']=b['quote']='United States conditionally signed agreement in Paris on April 10, 2026.'
        self.assertNotEqual(self.f.row_key(a),self.f.row_key(b))
        b['text']=b['quote']='United States has not signed agreement in Paris on April 10, 2026.'
        self.assertNotEqual(self.f.row_key(a),self.f.row_key(b))

    def test_may_date_is_not_the_modal_verb(self):
        a=self.row(); b=self.row('b','wire-b')
        for row in (a,b):
            row['elements']['time']='May 10, 2026'
            row['text']=row['quote']='United States signed agreement in Paris on May 10, 2026.'
        self.assertEqual(self.f.independent_fact_weights([a,b],.5),{'a':1.,'b':.5})

    def test_invalid_gamma_and_duplicate_ids_fail_explicitly(self):
        for gamma in (0,1,-1,float('nan')):
            with self.assertRaises(ValueError):self.f.independent_fact_weights([self.row()],gamma)
        with self.assertRaises(ValueError):self.f.group_facts([self.row(),self.row()])

if __name__=='__main__':unittest.main()


