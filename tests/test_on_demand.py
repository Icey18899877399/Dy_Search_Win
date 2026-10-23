import copy
import unittest
from dynamic_retrieval.engine import run
from dynamic_retrieval.evidence import prepare_task
from dynamic_retrieval.models import Config
from dynamic_retrieval.semantic import validate_semantic
from test_engine import TASK, document


def machine(task, doc):
    excerpt = doc['title'] + '\n' + doc['text']
    return validate_semantic(dict(elements={'subject':'alice','action':'win','object':'election'},
        support=[1,-1], quote='Alice won the election.', rationale='Reported event fact.',
        factual_status='reported', time_scope='target_compatible'), task, doc,
        dict(model='fixture', excerpt=excerpt))


class OnDemandTests(unittest.TestCase):
    def setUp(self):
        self.task=prepare_task(TASK)
        self.docs=[document(str(i),'2026-06-18') for i in range(5)]
        self.cfg=Config(mode='fixed',rounds=1,total_budget=2,round_budget=2)

    def test_only_retrieved_visible_documents_trigger_provider(self):
        docs=self.docs+[document('future','2026-06-22')]
        calls=[]
        def provider(task,doc):
            calls.append(doc['id']);return machine(task,doc)
        result=run(self.task,docs,self.cfg,annotation_provider=provider)
        read={d for r in result['rounds'] for d in r['retrieved_ids']}
        self.assertEqual(set(calls),read)
        self.assertEqual(len(calls),1)
        self.assertNotIn('future',calls)
        self.assertEqual(set(result['provenance']['annotations']),read)
        self.assertEqual(result['diagnostics']['annotation_failures'],[])

    def test_same_annotations_give_same_schedule_and_predictions(self):
        marks={d['id']:machine(self.task,d) for d in self.docs}
        eager=run(self.task,self.docs,self.cfg,marks)
        lazy=run(self.task,self.docs,self.cfg,annotation_provider=lambda task,doc:marks[doc['id']])
        for field in ('rounds','result','evidence'):
            self.assertEqual(eager[field],lazy[field])

    def test_failures_never_fall_back_to_lexical_evidence_or_repeat(self):
        calls=[]
        def fail(task,doc):
            calls.append(doc['id']);raise RuntimeError('SECRET must never be exported')
        result=run(self.task,self.docs,Config(mode='fixed',rounds=4),annotation_provider=fail)
        self.assertEqual(len(calls),len(set(calls)))
        self.assertEqual(result['evidence'],[])
        self.assertEqual(result['result']['probabilities'],[.5,.5])
        self.assertEqual(len(result['diagnostics']['annotation_failures']),5)
        self.assertNotIn('SECRET',str(result))

    def test_invalid_or_foreign_model_annotation_is_rejected(self):
        annotation=machine(self.task,self.docs[0])
        result=run(self.task,self.docs,self.cfg,annotation_provider=lambda t,d:dict(annotation,body_sha256='foreign'))
        self.assertEqual(result['evidence'],[])
        self.assertEqual(len(result['diagnostics']['annotation_failures']),1)

    def test_conflicting_input_modes_and_unknown_policy_rejected_before_calls(self):
        with self.assertRaises(ValueError):
            run(self.task,self.docs,self.cfg,{},annotation_provider=lambda t,d:None)
        with self.assertRaises(ValueError):
            run(self.task,self.docs,self.cfg,fact_policy='unknown')

    def test_provider_cannot_mutate_engine_task_or_corpus(self):
        original=copy.deepcopy(self.docs)
        def provider(task,doc):
            valid=machine(task,doc)
            task['outcomes'].reverse();doc['title']='changed'
            return valid
        result=run(self.task,self.docs,self.cfg,annotation_provider=provider)
        self.assertEqual(self.docs,original)
        self.assertEqual(result['task']['outcomes'],['Yes','No'])
        self.assertEqual(result['evidence'][0]['title'],original[0]['title'])

class SourceParameterTests(unittest.TestCase):
    def test_source_coverage_scales_affect_silence_separately(self):
        docs=[document('a','2026-06-18','one'),document('b','2026-06-18','two')]
        cfg=Config(mode='fixed',rounds=2)
        # Model-validated zero support still has matched evidence, but on round 2
        # both old sources have the same query spend and no new fact.
        marks={d['id']:machine(prepare_task(TASK),d) for d in docs}
        out=run(TASK,docs,cfg,marks,source_parameters={
            'one':{'coverage_scale':1.,'cost_per_day':.1},
            'two':{'coverage_scale':10.,'cost_per_day':.2}})
        states=out['rounds'][1]['source_states']
        self.assertGreater(states['one']['silence'],states['two']['silence'])
        self.assertEqual(out['provenance']['source_parameters']['two']['coverage_scale'],10.)
        self.assertEqual(out['diagnostics']['parameter_status'],'explicit_source_overrides_not_all_parameters_calibrated')

    def test_source_parameter_validation_before_any_provider_call(self):
        for profile in ({'paper':{'coverage_scale':0}}, {'paper':{'cost_per_day':float('nan')}},
                        {'paper':{'currency_cost':1}}, {'absent':{'coverage_scale':1}}):
            calls=[]
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                run(TASK,[document('a','2026-06-18')],source_parameters=profile,
                    annotation_provider=lambda t,d:calls.append(d))
            self.assertEqual(calls,[])

    def test_explicit_default_source_parameters_preserve_rounds(self):
        docs=[document('a','2026-06-18')]
        cfg=Config(rounds=3)
        marks={d['id']:machine(prepare_task(TASK),d) for d in docs}
        ordinary=run(TASK,docs,cfg,marks)
        explicit=run(TASK,docs,cfg,marks,source_parameters={'paper':{
            'coverage_scale':cfg.coverage_scale,'cost_per_day':cfg.cost_per_day}})
        self.assertEqual(ordinary['rounds'],explicit['rounds'])
        self.assertEqual(ordinary['result'],explicit['result'])

class ProviderIsolationTests(unittest.TestCase):
    def test_provider_never_receives_labels_prices_or_unlisted_metadata(self):
        task=dict(TASK,resolved_outcome='LEAK',outcome_prices=[.9,.1],final_prices=[1,0],
                  private_evaluation={'label':'LEAK'})
        seen=[]
        def provider(t,d):
            seen.append(t);return machine(t,d)
        out=run(task,[document('a','2026-06-18')],Config(mode='fixed',rounds=1),annotation_provider=provider)
        self.assertEqual(len(seen),1)
        self.assertNotIn('LEAK',str(seen))
        self.assertNotIn('outcome_prices',seen[0])
        self.assertEqual(out['result']['supporting_evidence_count'],1)
