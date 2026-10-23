import unittest
from dynamic_retrieval.evidence import prepare_task, extract


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.task=prepare_task({'market_id':'1','question':'Will Alice win the election in 2026?',
            'outcomes':['Yes','No'],'target_elements':{'subject':'Alice','action':'win','object':'election','time':'2026'},
            'element_aliases':{'action':['won','wins']},
            'positive_patterns':[r'Alice won the election'], 'negative_patterns':[r'Alice lost the election']})

    def doc(self,text):
        return {'id':'d','text':text,'title':text,'source_id':'paper','published_at':'2026-01-01T00:00:00+00:00'}

    def test_direct_rule_support_and_traceable_elements(self):
        row=extract(self.doc('Alice won the election in 2026.'),self.task)
        self.assertEqual(row['support'],[1,-1])
        self.assertEqual(row['elements']['action'],'win')
        self.assertIn('Alice won',row['quote'])
        self.assertEqual(row['relevance'],1.)

    def test_speculation_is_not_a_completed_result(self):
        row=extract(self.doc('What if Alice won the election in 2026?'),self.task)
        self.assertEqual(row['support'],[0,0])

    def test_default_unreviewed_rules_abstain_on_support(self):
        task=prepare_task({'market_id':'1','question':'Will Alice win the election in 2026?','outcomes':['Yes','No']})
        row=extract(self.doc('Alice won the election in 2026.'),task)
        self.assertEqual(row['support'],[0,0])
        self.assertEqual(row['extraction_method'],'lexical_v1')

    def test_annotations_require_real_quote_and_valid_support(self):
        d=self.doc('Alice won the election in 2026.')
        row=extract(d,self.task,{'d':{'reviewed':True,'elements':{'subject':'Alice','action':'win','object':'election','time':'2026'},
                                  'support':[1,-1],'quote':'Alice won'}})
        self.assertEqual(row['extraction_method'],'reviewed_annotation')
        with self.assertRaises(ValueError):
            extract(d,self.task,{'d':{'reviewed':True,'elements':{'subject':'Alice'},'support':[1,0],'quote':'fabricated'}})

    def test_only_explicit_boolean_true_enables_reviewed_annotation(self):
        task=prepare_task({'question':'Will Alice win the election?','outcomes':['Yes','No']})
        doc=self.doc('Alice won the election.')
        annotation={'elements':{'subject':'Alice'},'support':[1,-1],'quote':'Alice won'}
        for marker in ('missing',None,False,'false','true',1,0):
            entry=dict(annotation)
            if marker!='missing':entry['reviewed']=marker
            with self.subTest(marker=marker):
                row=extract(doc,task,{'d':entry})
                self.assertEqual(row['extraction_method'],'lexical_v1')
                self.assertEqual(row['support'],[0,0])
        annotation['reviewed']=True
        self.assertEqual(extract(doc,task,{'d':annotation})['support'],[1,-1])

    def test_binary_fallback_not_allowed_for_multiclass(self):
        with self.assertRaises(ValueError): prepare_task({'question':'Who wins?','outcomes':['A','B','C']})

    def test_reversed_yes_no_order_preserves_support_alignment(self):
        raw=dict(self.task);raw['outcomes']=['No','Yes']
        row=extract(self.doc('Alice won the election in 2026.'),prepare_task(raw))
        self.assertEqual(row['support'],[-1,1])

    def test_model_annotation_is_validated_and_never_labeled_human_reviewed(self):
        from dynamic_retrieval.semantic import validate_semantic
        doc=self.doc('Alice won the election in 2026.')
        task=dict(self.task,cutoff='2026-06-20T00:00:00Z')
        data={'elements':{'subject':'Alice','action':'win','object':'election'},
              'support':[1,-1],'quote':'Alice won the election in 2026.',
              'rationale':'The supplied sentence states the outcome.',
              'factual_status':'asserted','time_scope':'target_compatible'}
        entry=validate_semantic(data,task,doc,{'model':'deepseek-flash','excerpt':doc.get('title','')+'\n'+doc['text']})
        row=extract(doc,task,{'d':entry})
        self.assertEqual(row['support'],[1,-1])
        self.assertEqual(row['extraction_method'],'model_validated_unreviewed')
        self.assertIs(row['human_reviewed'],False)
        self.assertIs(entry['reviewed'],False)
        changed=dict(doc,text='A different body.')
        with self.assertRaises(ValueError):extract(changed,task,{'d':entry})


if __name__=='__main__':unittest.main()
