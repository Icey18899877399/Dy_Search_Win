"""Single-run on-demand model extraction with a separate measured call ledger.

The source-budget scheduler remains a simulation. Metadata routing is local and
free; only documents actually read enter this provider. Cache reuse is explicit.
"""
from copy import deepcopy
import hashlib
import json
import time
from .call_cost import CallCostLedger, CallCostError
from .engine import run
from .semantic import build_evidence_messages, validate_semantic, DATA_FIELDS, CONTEXT_FIELDS


class ModelAnnotationProvider:
    def __init__(self, client, max_chars=12000):
        if type(max_chars) is not int or not 1 <= max_chars <= 12000:
            raise ValueError('max_chars must be between 1 and 12000')
        self.client=client
        self.max_chars=max_chars
        self.traces=[]

    def __call__(self, task, document):
        messages=build_evidence_messages(task,document,max_chars=self.max_chars)
        context=json.loads(messages[1]['content'])['evidence']
        excerpt=context['excerpt']
        context_metadata={k:context[k] for k in CONTEXT_FIELDS if k in context}
        trace=dict(document_id=document['id'],status='failed',metadata={},
            selected_excerpt=excerpt,prompt_sha256=hashlib.sha256(json.dumps(
                messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        if context_metadata:trace['excerpt_context']=context_metadata
        self.traces.append(trace)
        start=time.perf_counter()
        try:
            result=self.client.complete_json(messages,max_tokens=1800)
            metadata=result['metadata']
            trace['metadata']={k:deepcopy(metadata[k]) for k in (
                'model','requested_model','usage','request_id','cache_key','cache_hit',
                'finish_reason','attempts') if k in metadata}
            # Preserve contract fields even if validation fails, without exporting
            # arbitrary extra fields such as a provider's private reasoning.
            raw=result['data']
            trace['parsed_response']={k:deepcopy(raw[k]) for k in DATA_FIELDS if isinstance(raw,dict) and k in raw}
            trace['parsed_response_fields_filtered']=not isinstance(raw,dict) or bool(set(raw)-DATA_FIELDS)
            trace['response_sha256']=hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            annotation=validate_semantic(result['data'],task,document,dict(metadata,excerpt=excerpt,**context_metadata))
            trace['status']='validated'
            return annotation
        except Exception as exc:
            trace.update(error_type=type(exc).__name__,error='request_or_structural_validation_failed')
            raise
        finally:
            trace['elapsed_seconds']=time.perf_counter()-start


def run_on_demand(task, documents, config, client, *, max_chars=12000,
                  fact_policy='legacy', source_parameters=None, observer=None, comparison_policy=None,
                  decision_trace=False, runtime_policy=None, recovery_policy=None, budget_policy=None,
                  grid_policy=None, source_cost_profile=None, retrieval_policy=None, evidence_policy=None):
    """A fresh ledger per run prevents attributing another run's bill to this one.

    Reuse the disk cache explicitly across runs, never a populated call ledger.
    Fatal telemetry errors propagate so subsequent calls cannot go unrecorded.
    """
    ledger=getattr(client,'cost_ledger',None)
    if not isinstance(ledger,CallCostLedger) or ledger.snapshot()['events']:
        raise ValueError('On-demand execution requires a fresh CallCostLedger')
    provider=ModelAnnotationProvider(client,max_chars)
    start=time.perf_counter()
    result=run(task,documents,config,annotation_provider=provider,
        fact_policy=fact_policy,source_parameters=source_parameters,observer=observer,comparison_policy=comparison_policy,
        decision_trace=decision_trace,runtime_policy=runtime_policy,recovery_policy=recovery_policy,budget_policy=budget_policy,
        grid_policy=grid_policy,source_cost_profile=source_cost_profile,retrieval_policy=retrieval_policy,evidence_policy=evidence_policy)
    result['extraction_trace']=deepcopy(provider.traces)
    result['diagnostics'].update(model_calls=ledger.snapshot(),
        on_demand_elapsed_seconds=time.perf_counter()-start,
        model_cost_in_simulated_budget=False,monetary_cost=None,
        model_accounting_note='Returned usage is observed, not invoice-verified. Missing usage remains unknown; cached usage is historical. In-flight attempts lost to process termination may be absent.')
    return result
