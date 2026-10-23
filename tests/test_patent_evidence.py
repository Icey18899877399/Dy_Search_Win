import unittest
from copy import deepcopy
from dynamic_retrieval.evidence import extract, prepare_task
from dynamic_retrieval.engine import run
from dynamic_retrieval.core import independent_weights
from dynamic_retrieval.models import Config


class PatentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.task = prepare_task(dict(question='Will Alice win the election in 2026?',
            cutoff='2026-10-01T00:00:00Z', outcomes=['Yes','No'],
            target_elements=dict(subject='Alice',action='win',object='election',time='2026'),
            element_aliases={'action':['won','wins']}))

    def document(self, text, identifier='d'):
        return dict(id=identifier,title='',text=text,source_id='paper',
            published_at='2026-09-30T00:00:00Z',observed_at='2026-09-30T00:00:00Z')

    def extracted(self, text, elements=None, task=None, support=None):
        task = task or self.task
        doc = self.document(text)
        annotations = None if elements is None else {'d':dict(reviewed=True,
            elements=elements,support=support or [-1,1],quote=text)}
        try:
            return extract(doc,task,annotations,evidence_policy='patent_elements_v1')
        except TypeError as error:
            self.fail(str(error))

    def test_partial_overlap_is_not_zeroed_by_support_gate(self):
        row = self.extracted('Alice discussed the election in 2026.',
            dict(subject='Alice',action='discussed',object='election',time='2026'))
        self.assertEqual(row['relevance'],.75)
        self.assertEqual(row['support'],[0,0])

    def test_default_closed_assertion_replaces_model_direction_and_keeps_raw_trace(self):
        raw = dict(subject='ALICE',action='won',object='election',time='2026')
        row = self.extracted('Alice won the election in 2026.', raw)
        self.assertEqual(row['support'],[1,-1])
        self.assertEqual(row['elements']['action'],'win')
        self.assertEqual(row['patent_evidence_trace']['raw_elements'], raw)
        self.assertEqual(row['patent_evidence_trace']['original_support'],[-1,1])
        self.assertTrue(row['patent_evidence_trace']['normalization']['witnesses']['action'])

    def test_unknown_and_different_identities_never_become_negative_support(self):
        for elements,text in [
            (dict(subject='Bob',action='won',object='election',time='2026'),'Bob won the election in 2026.'),
            (dict(subject='Alice',action='won',object='election',time='2025'),'Alice won the election in 2025.'),
            (dict(subject='Alice',action='won',object='election'),'Alice won the election.'),
            (dict(subject='Alice',action='won',object='election',time='2026'),'Alice might have won the election in 2026.'),
            (dict(subject='Alice',action='won',object='election',time='2026'),'Alice discussed the election. Bob won in 2026.')]:
            with self.subTest(text=text):
                self.assertEqual(self.extracted(text,elements)['support'],[0,0])

    def test_ungrounded_elements_removed_without_publication_time_substitution(self):
        row = self.extracted('Alice discussed the election.',dict(subject='Alice',action='won',object='election',time='2026'))
        self.assertEqual(row['relevance'],.5)
        self.assertNotIn('action',row['elements'])
        self.assertNotIn('time',row['elements'])
        self.assertFalse(row['patent_evidence_trace']['normalization']['publication_time_substituted'])

    def configured(self):
        task=deepcopy(self.task)
        task['support_rules']={'version':'patent_support_v1','rules':[{
            'id':'explicit-loss', 'requirements':dict(subject='Alice',action='lost',object='election',time='2026'),
            'assertion_pattern':r'(?P<subject>Alice) (?P<action>lost) the (?P<object>election) in (?P<time>2026)\.',
            'support':{'Yes':-1,'No':1}, 'reason':'Explicit completed loss for the same election.'}]}
        return task

    def test_only_explicit_conflicting_action_rule_can_produce_negative_support(self):
        text='Alice lost the election in 2026.'
        elements=dict(subject='Alice',action='lost',object='election',time='2026')
        self.assertEqual(self.extracted(text,elements)['support'],[0,0])
        row=self.extracted(text,elements,self.configured())
        self.assertEqual(row['support'],[-1,1])
        self.assertEqual(row['relevance'],.75)
        self.assertEqual(row['patent_evidence_trace']['support']['matched_rule_ids'],['explicit-loss'])

    def test_unsupported_question_abstains_despite_complete_overlap(self):
        task=deepcopy(self.task);task['question']='Will Alice have a chance to win the election in 2026?'
        row=self.extracted('Alice won the election in 2026.',dict(self.task['target_elements'],action='won'),task)
        self.assertEqual(row['relevance'],1.)
        self.assertEqual(row['support'],[0,0])

    def test_rules_validate_before_provider_and_reject_unbound_or_identity_changing_contracts(self):
        for change in ({'assertion_pattern':'.*'}, {'requirements':dict(subject='Bob',action='lost',object='election',time='2026')}):
            task=self.configured();task['support_rules']['rules'][0].update(change)
            calls=[]
            def provider(*args):calls.append(args);raise AssertionError('must not call')
            with self.assertRaises(ValueError):
                run(task,[self.document('Alice lost the election in 2026.')],annotation_provider=provider,evidence_policy='patent_elements_v1')
            self.assertEqual(calls,[])

    def test_exact_normalized_fact_groups_only_and_geometric_weights(self):
        rows=[]
        for identifier,action,time in [('a','won','2026'),('b','win','2026'),('c','won','2025')]:
            row=self.extracted('Alice won the election in '+time+'.',dict(subject='Alice',action=action,object='election',time=time))
            row['id']=identifier;rows.append(row)
        self.assertEqual(independent_weights(rows,.5),{'a':1.,'b':.5,'c':1.})

    def test_engine_applies_policy_and_preserves_legacy_default(self):
        doc=self.document('Alice won the election in 2026.')
        cfg=Config(rounds=1)
        legacy=run(self.task,[doc],cfg)
        self.assertEqual(legacy,run(self.task,[doc],cfg,evidence_policy=None))
        result=run(self.task,[doc],cfg,evidence_policy='patent_elements_v1')
        self.assertEqual(result['provenance']['evidence_policy'],'patent_elements_v1')
        self.assertEqual(result['evidence'][0]['support'],[1,-1])
        for options in ({'comparison_policy':'typed_v6'},{'fact_policy':'conservative_v1'}):
            with self.assertRaises(ValueError):run(self.task,[doc],cfg,evidence_policy='patent_elements_v1',**options)

    def test_model_binding_and_unreviewed_markers_preserved(self):
        from dynamic_retrieval.semantic import validate_semantic
        doc=self.document('Alice won the election in 2026.')
        data=dict(elements=dict(subject='Alice',action='won',object='election',time='2026'),
            support=[0,0],quote=doc['text'],rationale='A reported event.',factual_status='reported',time_scope='target_compatible')
        entry=validate_semantic(data,self.task,doc,dict(model='fixture',excerpt='\n'+doc['text']))
        original=deepcopy(entry)
        row=extract(doc,self.task,{'d':entry},evidence_policy='patent_elements_v1')
        self.assertEqual(row['support'],[1,-1])
        self.assertIs(row['human_reviewed'],False)
        self.assertEqual(entry,original)
        self.assertEqual(row['patent_evidence_trace']['original_support'],[0,0])


    def test_known_malformed_target_is_parsed_without_changing_binding_or_support_gate(self):
        task=prepare_task(dict(question='Israeli parliament dissolved by July 31?',
            cutoff='2026-07-01T00:00:00Z',outcomes=['Yes','No'],
            target_elements={'subject':'Israeli parliament dissolved by July 31','time':'July 31'}))
        original=deepcopy(task)
        row=self.extracted('The Israeli parliament debated a proposal.',
            {'subject':'Israeli parliament','action':'debated'},task)
        self.assertAlmostEqual(row['relevance'],1/3)
        self.assertEqual(row['support'],[0,0])
        trace=row['patent_evidence_trace']
        self.assertEqual(trace['task_parse']['status'],'supported_template')
        self.assertEqual(trace['effective_target']['action'],'dissolve')
        self.assertEqual(trace['original_target'],original['target_elements'])
        self.assertEqual(task,original)

    def test_unsupported_range_question_has_explicit_parse_diagnosis(self):
        task=prepare_task(dict(question='Will Elon Musk post 1000-1039 tweets in April 2026?',
            cutoff='2026-04-30T00:00:00Z',outcomes=['Yes','No'],
            target_elements={'subject':'Elon Musk post 1000-1039 tweets in April 2026','time':'April 2026'}))
        row=self.extracted('Elon Musk posted tweets in April 2026.',
            {'subject':'Elon Musk','action':'posted','object':'tweets','time':'April 2026'},task)
        self.assertEqual(row['patent_evidence_trace']['task_parse']['status'],'unsupported')
        self.assertIn('unsupported_task',row['patent_evidence_trace']['support']['blockers'])
        self.assertEqual(row['support'],[0,0])

    def test_unicode_and_date_normalization_preserve_original_witness_offsets(self):
        task=deepcopy(self.task);task['target_elements']['time']='2026-06-01'
        row=self.extracted('Alice won the election on June 1, 2026.',
            {'subject':'Ａｌｉｃｅ','action':'won','object':'election','time':'2026-06-01'},task)
        self.assertEqual(row['relevance'],1.)
        text='\nAlice won the election on June 1, 2026.'
        for entries in row['patent_evidence_trace']['normalization']['witnesses'].values():
            for entry in entries:self.assertEqual(text[entry['start']:entry['end']],entry['text'])

    def test_conflicting_configured_rules_abstain_with_both_ids_recorded(self):
        task=self.configured();other=deepcopy(task['support_rules']['rules'][0])
        other.update(id='opposite-contract',support={'Yes':1,'No':-1})
        task['support_rules']['rules'].append(other)
        row=self.extracted('Alice lost the election in 2026.',
            dict(subject='Alice',action='lost',object='election',time='2026'),task)
        self.assertEqual(row['support'],[0,0])
        self.assertEqual(row['patent_evidence_trace']['support']['resolution'],'conflicting_rules_abstain')
        self.assertEqual(len(row['patent_evidence_trace']['support']['matched_rule_ids']),2)

    def test_engine_admits_incomplete_relevant_record_but_keeps_support_neutral(self):
        doc=self.document('Alice discussed the election in 2026.')
        annotation=dict(reviewed=True,elements=dict(subject='Alice',action='discussed',object='election',time='2026'),
            support=[1,-1],quote=doc['text'])
        result=run(self.task,[doc],Config(rounds=1),{'d':annotation},evidence_policy='patent_elements_v1')
        self.assertEqual(result['diagnostics']['admitted_documents'],1)
        self.assertEqual(result['evidence'][0]['relevance'],.75)
        self.assertEqual(result['result']['probabilities'],[.5,.5])
        self.assertEqual(result['evidence'][0]['matching_trace']['matched'],['subject','object','time'])

    def test_lexical_extraction_uses_effective_target_for_known_malformed_task(self):
        task=prepare_task(dict(question='Israeli parliament dissolved by July 31?',cutoff='2026-07-01T00:00:00Z',
            outcomes=['Yes','No'],target_elements={'subject':'Israeli parliament dissolved by July 31','time':'July 31'}))
        row=self.extracted('The Israeli parliament debated a proposal.',task=task)
        self.assertAlmostEqual(row['relevance'],1/3)
        self.assertEqual(row['matching_trace']['target']['subject'],'israeli parliament')

    def test_future_event_year_month_day_and_timestamp_cannot_derive_support(self):
        cases=[('2026','2025-10-01T00:00:00Z'),('November 2026','2026-10-01T00:00:00Z'),
            ('2026-11','2026-10-01T00:00:00Z'),('2026-10-02','2026-10-01T00:00:00Z'),
            ('2026-10-01T12:00:00Z','2026-10-01T08:00:00Z'),('next year','2026-10-01T00:00:00Z')]
        for event_time,cutoff in cases:
            task=deepcopy(self.task);task['cutoff']=cutoff;task['target_elements']['time']=event_time
            requirements=deepcopy(task['target_elements'])
            import re
            task['support_rules']={'version':'patent_support_v1','rules':[dict(id='dated-winner',
                requirements=requirements,assertion_pattern=r'(?P<subject>Alice) (?P<action>won) the (?P<object>election) in (?P<time>'+re.escape(event_time)+r')\.',
                support={'Yes':1,'No':-1},reason='Same target event completed.') ]}
            with self.subTest(event_time=event_time):
                row=self.extracted('Alice won the election in '+event_time+'.',dict(requirements,action='won'),task)
                self.assertEqual(row['relevance'],1.)
                self.assertEqual(row['support'],[0,0])
                self.assertTrue(row['patent_evidence_trace']['support']['blockers'])

    def test_later_quote_negation_or_retraction_cannot_leave_initial_support(self):
        for suffix in (' Actually, Alice did not win the election in 2026.',
                ' This claim was denied.', ' This claim was retracted.', ' This report was false.'):
            with self.subTest(suffix=suffix):
                row=self.extracted('Alice won the election in 2026.'+suffix,dict(self.task['target_elements'],action='won'))
                self.assertEqual(row['relevance'],1.)
                self.assertEqual(row['support'],[0,0])

    def test_quote_substring_is_not_complete_original_sentence(self):
        from dynamic_retrieval.semantic import validate_semantic
        quote='Alice won the election in 2026.'
        for prefix in ('It is false that ', 'If Bob withdraws, ', 'The rumour claimed that '):
            doc=self.document(prefix+quote)
            data=dict(elements=dict(self.task['target_elements'],action='won'),support=[0,0],quote=quote,
                rationale='Extracted claim.',factual_status='reported',time_scope='target_compatible')
            entry=validate_semantic(data,self.task,doc,dict(model='fixture',excerpt='\n'+doc['text']))
            with self.subTest(prefix=prefix):
                row=extract(doc,self.task,{'d':entry},evidence_policy='patent_elements_v1')
                self.assertEqual(row['relevance'],1.)
                self.assertEqual(row['support'],[0,0])

    def test_retraction_outside_selected_quote_cannot_leave_initial_support(self):
        quote='Alice won the election in 2026.'
        doc=self.document(quote+' This claim was denied.')
        annotation=dict(reviewed=True,elements=dict(self.task['target_elements'],action='won'),support=[0,0],quote=quote)
        row=extract(doc,self.task,{'d':annotation},evidence_policy='patent_elements_v1')
        self.assertEqual(row['support'],[0,0])
