"""Offline round engine implementing S101–S107 and S201–S703.

All prediction data is frozen at cutoff. Logical round time is simulated in days;
it does not make later archive snapshots visible. Budget is a declared simulator.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from collections import defaultdict
from statistics import median
import math
import re
import hashlib
import json
from .models import Config
from .evidence import prepare_task, extract, evidence_rules
from .core import (independent_weights, probabilities, coverage, exhaustion, loss_ratio,
                   transition_cells, can_stop, total_variation, uncertainty)


def day(value):
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Timestamps must include timezone')
    return parsed.timestamp()/86400


def iso(value):
    return datetime.fromtimestamp(value*86400,timezone.utc).isoformat()


def run(task, documents, config=None, annotations=None, *, observer=None,
        annotation_provider=None, fact_policy='legacy', source_parameters=None, comparison_policy=None,
        decision_trace=False, runtime_policy=None, recovery_policy=None, budget_policy=None,
        grid_policy=None, source_cost_profile=None, retrieval_policy=None, evidence_policy=None):
    if evidence_policy not in (None, "patent_elements_v1", "patent_elements_v2", "patent_elements_v3", "patent_elements_v4"):
        raise ValueError("Unknown evidence policy")
    if evidence_policy is not None and (comparison_policy is not None or fact_policy != "legacy"):
        raise ValueError("Patent evidence policy requires exact grouping and no comparison policy")
    if budget_policy not in (None, 'patent_budget_v1'):
        raise ValueError('Unknown budget policy')
    patent_budget=budget_policy=='patent_budget_v1'
    if patent_budget and recovery_policy is None:recovery_policy='patent_full_band_v1'
    if type(decision_trace) is not bool:
        raise ValueError('decision_trace must be boolean')
    if recovery_policy not in (None,'patent_full_band_v1'):
        raise ValueError('Unknown recovery policy')
    full_band_policy=recovery_policy=='patent_full_band_v1'
    if full_band_policy:decision_trace=True
    if comparison_policy not in (None,'typed_v6'):
        raise ValueError('Unknown comparison policy')
    if annotation_provider is not None and (annotations is not None or not callable(annotation_provider)):
        raise ValueError('On-demand provider must be callable and cannot be mixed with frozen annotations')
    if fact_policy not in ('legacy', 'conservative_v1'):
        raise ValueError('Unknown fact policy')
    weights_for = independent_weights
    if fact_policy == 'conservative_v1':
        from .fact_groups import independent_fact_weights
        weights_for = independent_fact_weights
    provider_annotations = {}
    annotation_failures = []
    cfg=config or Config()
    if grid_policy is not None:
        from .grid_budget import validate_grid_policy, plan_grid_budget
        if not patent_budget or cfg.mode!='enhanced':
            raise ValueError('grid policy requires enhanced mode and patent_budget_v1')
        grid_policy=validate_grid_policy(grid_policy,cfg)
    if source_cost_profile is not None and (not patent_budget or source_parameters is not None):
        raise ValueError('source cost profile requires patent budget and cannot mix source overrides')
    if full_band_policy and cfg.enable_uncertainty_expansion:
        raise ValueError('patent_full_band_v1 cannot be combined with uncertainty expansion')
    if runtime_policy is not None:
        from .runtime_policy import validate_runtime_policy, runtime_parameters
        runtime_policy=validate_runtime_policy(runtime_policy,cfg)
        decision_trace=True
    from .retrieval_policy import validate_retrieval_policy, ScopedBM25
    retrieval_preflight=validate_retrieval_policy(retrieval_policy,cfg,budget_policy,grid_policy)
    guarded=retrieval_policy is not None
    if guarded:decision_trace=True
    task=prepare_task(task)
    if evidence_policy is not None:
        evidence_rules(evidence_policy).validate_support_rules(task)
    ranker=ScopedBM25(task) if retrieval_policy=='bm25_read_guard_v1' else None
    cutoff=day(task['cutoff']); boundary=cutoff-cfg.initial_window_days
    earliest=cutoff-cfg.earliest_days
    # Fail closed on missing/invalid times and foreign-event evidence.
    candidates=[];excluded=0;urls=set();eligible=[]
    for original in documents:
        try:
            published=day(original['published_at']);observed=day(original['observed_at'])
        except (ValueError,KeyError,TypeError,OverflowError):excluded+=1;continue
        if published>cutoff or observed>cutoff or (task.get('event_id') and original.get('event_id')!=task['event_id']):
            excluded+=1;continue
        eligible.append((observed,str(original['id']),published,original))
    for observed,_,published,original in sorted(eligible,key=lambda x:(x[0],x[1]),reverse=True):
        key=original.get('canonical_url') or original['id']
        if key in urls:continue
        urls.add(key)
        row=dict(original);row['_day']=published
        row['published_at']=iso(published);row['observed_at']=iso(observed);candidates.append(row)
    sources=sorted({d['source_id'] for d in candidates})
    from copy import deepcopy
    cost_configuration=None
    if source_cost_profile is not None:
        from .source_cost_profile import prepare_source_cost_profile
        cost_configuration=prepare_source_cost_profile(source_cost_profile,sources,task['cutoff'])
        source_parameters=cost_configuration['source_parameters']
    source_parameters=deepcopy(source_parameters)
    if source_parameters is not None:
        if not isinstance(source_parameters,dict) or set(source_parameters)-set(sources):
            raise ValueError('Source overrides must refer to visible sources')
        for values in source_parameters.values():
            if (not isinstance(values,dict) or not values or
                    set(values)-{'coverage_scale','cost_per_day'} or any(
                        type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values.values())):
                raise ValueError('Source overrides require positive finite coverage_scale/cost_per_day in simulation units')
    def source_parameter(source,key):
        return (source_parameters or {}).get(source,{}).get(key,getattr(cfg,key))
    by_source={s:[] for s in sources}
    query_tokens=set(re.findall(r'\w+',task['question'].lower()))
    for d in candidates:by_source[d['source_id']].append(d)
    for pool in by_source.values():
        pool.sort(key=lambda d:(-len(query_tokens & set(re.findall(r'\w+',d.get('title','').lower()))),-d['_day'],d['id']))
    included=set(sources[:cfg.initial_source_limit] if cfg.initial_source_limit else sources)
    source_states={s:dict(silence=0.,phi=0.,active=True,confirmations=0,publications=[],
                          observed_days=0.,new_count=0,last_new_round=None) for s in sources}
    known={};window_ids=set();attempted=defaultdict(set)
    history=[];rows=[];previous_volume=0.;previous_probs=[1/len(task['outcomes'])]*len(task['outcomes'])
    remaining=cfg.total_budget;state='continue';waiting_cap=None;waiting_spent=0.;cooldown_until=0
    return_ceiling=None;virtual_time=0.;gain_history=[];frozen_gain=None;reason='round_limit'
    extraction_cache={};admitted_ids=set()
    credit_policy=task.get('scheduler_policy')=='grid_credit_v2'
    grid_credits={};grid_signature=None

    baseline=cfg.total_budget/cfg.rounds if patent_budget else cfg.round_budget
    for round_no in range(1,cfg.rounds+1):
        if remaining < (1e-12 if patent_budget else cfg.query_cost-1e-12):reason='budget_exhausted';break
        current_boundary=boundary;start_state=state
        settings=dict(slow_multiplier=cfg.slow_multiplier,waiting_share=cfg.waiting_share,shared_quota=cfg.shared_quota)
        parameter_trace=dict(status='static_config',elapsed_days=virtual_time,parameters=dict(settings))
        if runtime_policy is not None:
            parameters,parameter_trace=runtime_parameters(runtime_policy,virtual_time,remaining,cfg)
            if parameter_trace['status']=='deadline_reached':reason='task_deadline_reached';break
            settings.update(parameters)
        shared_quota=settings['shared_quota'];waiting_share=settings['waiting_share']
        interval=cfg.round_interval_days*(settings['slow_multiplier'] if state=='slow' else 1)
        if runtime_policy is not None:
            interval=min(interval,runtime_policy['task_duration_days']-virtual_time)
        parameter_trace['applied_interval_days']=interval
        parameter_trace['slow_fraction']=cfg.slow_fraction
        source_start={s:(st['silence'],st['observed_days']) for s,st in source_states.items()}
        virtual_time+=interval
        effective=min(baseline,remaining)
        waiting_opening_cap=waiting_cap;waiting_opening_spent=waiting_spent
        if not patent_budget:
            if state=='slow':effective=min(effective,cfg.round_budget*cfg.slow_fraction, max(0.,waiting_cap-waiting_spent))
            if effective<cfg.query_cost-1e-12:reason='waiting_budget_exhausted' if state=='slow' else 'budget_exhausted';break
        ledger=dict(window=0.,probe=0.,recovery=0.,watch=0.)
        spent_by_source=defaultdict(float);fresh_sources=set();retrieved_ids=[];recovered_ids=[]
        read_start=len(extraction_cache)
        action='hold';convergence_skipped=False
        budget_blocked=False;credit_can_accumulate=False
        retrieval_events=[]
        read_execution=dict(requests_executed=0,skipped=[])

        def spent():return sum(ledger.values())

        def search(kind,start,end,budget,names,right_closed=False):
            nonlocal budget_blocked
            # Inclusive span cost has already been booked for every recovery source.
            # Body reads remain observable; charging them again would mix cost bases.
            prepaid=patent_budget and kind=='recovery'
            request_charge=0. if prepaid else cfg.query_cost
            # Integer request/read costs quantize the proportional allocation; rotate for fairness.
            if (credit_policy or guarded) and not prepaid:
                # Frozen archive metadata is a free local routing index, not an online source query.
                names=[s for s in names if any(start<=d['_day'] and
                    (d['_day']<=end if right_closed else d['_day']<end) and
                    d['id'] not in attempted[(kind,s)] for d in by_source[s])]
            names=sorted(names)
            if not names:return []
            if not prepaid and budget<cfg.query_cost-1e-12:
                budget_blocked=True
                return []
            offset=(round_no-1)%len(names);names=names[offset:]+names[:offset]
            rates={s:source_states[s]['new_count']/max(source_states[s]['observed_days'],interval) for s in names}
            rate_total=sum(rates.values())
            shares={s:cfg.min_source_share/len(names)+(1-cfg.min_source_share)*(rates[s]/rate_total if rate_total else 1/len(names)) for s in names}
            found=[];left=math.inf if prepaid else min(budget,effective-spent(),remaining-spent())
            for source in names:
                pool=by_source[source];rank_info={}
                if guarded:
                    pool=[d for d in pool if start<=d['_day'] and
                        (d['_day']<=end if right_closed else d['_day']<end) and
                        d['id'] not in attempted[(kind,source)]]
                    if not pool:continue
                if not guarded and not prepaid and left<cfg.query_cost-1e-12:break
                allocation=math.inf if prepaid else min(left,max(cfg.query_cost+cfg.read_cost,budget*shares[source]))
                if guarded and not prepaid:
                    minimum_read=min(0. if d['id'] in extraction_cache else cfg.read_cost for d in pool)
                    if allocation+1e-12<request_charge+minimum_read:
                        budget_blocked=True
                        read_execution['skipped'].append(dict(phase=kind,source_id=source,
                            reason='insufficient_request_and_read_budget',available=allocation,
                            required=request_charge+minimum_read,pending_documents=len(pool)))
                        continue
                if ranker is not None:pool,rank_info=ranker.rank(pool)
                if guarded:read_execution['requests_executed']+=1
                ledger[kind]+=request_charge;spent_by_source[source]+=request_charge;left-=request_charge
                allowance=allocation-request_charge
                for doc in pool:
                    t=doc['_day']
                    if t<start or (t>end if right_closed else t>=end):continue
                    if doc['id'] in attempted[(kind,source)]:continue
                    read_cost=0. if prepaid or doc['id'] in extraction_cache else cfg.read_cost
                    if allowance<read_cost-1e-12 or left<read_cost-1e-12:
                        if guarded:continue
                        break
                    allowance-=read_cost;left-=read_cost
                    ledger[kind]+=read_cost;spent_by_source[source]+=read_cost
                    attempted[(kind,source)].add(doc['id']);retrieved_ids.append(doc['id'])
                    if doc['id'] not in extraction_cache:
                        if annotation_provider is None:
                            extraction_cache[doc['id']]=extract(doc,task,annotations,comparison_policy=comparison_policy,evidence_policy=evidence_policy)
                        else:
                            # Failure is cached as an abstention, never a lexical fallback.
                            from copy import deepcopy
                            from .semantic import validate_model_annotation
                            try:
                                provider_task={k:task[k] for k in ('market_id','event_id','question',
                                    'description','outcomes','target_elements','cutoff','semantic_policy',
                                    'matching_policy','element_aliases','task_parse') if k in task}
                                if task.get('evidence_context_policy'):
                                    provider_task.update(evidence_context_policy=task['evidence_context_policy'],observed_at=task.get('observed_at'))
                                if evidence_policy is not None and 'support_rules' in task:
                                    provider_task['support_rules']=task['support_rules']
                                annotation=annotation_provider(deepcopy(provider_task),deepcopy(doc))
                                validate_model_annotation(annotation,task,doc)
                                evidence=extract(doc,task,{doc['id']:annotation},comparison_policy=comparison_policy,evidence_policy=evidence_policy)
                                provider_annotations[doc['id']]=deepcopy(annotation)
                                extraction_cache[doc['id']]=evidence
                            except Exception as exc:
                                from .call_cost import CallCostError
                                if isinstance(exc,CallCostError):raise
                                annotation_failures.append(dict(document_id=doc['id'],
                                    error_type=type(exc).__name__,reason='on_demand_annotation_failed'))
                                extraction_cache[doc['id']]=None
                    evidence=extraction_cache[doc['id']]
                    if decision_trace:
                        retrieval_events.append(dict(document_id=doc['id'],source_id=source,phase=kind,
                            read_cost=read_cost,relevance=None if evidence is None else evidence['relevance'],
                            status='extraction_failed' if evidence is None else
                                'admitted' if evidence['relevance']>=cfg.admission else 'rejected'))
                    if guarded and rank_info:
                        retrieval_events[-1]['candidate_rank']=rank_info[doc['id']]
                    if evidence is None:continue
                    if evidence['relevance']<cfg.admission:continue
                    known[doc['id']]=evidence;found.append(evidence)
                    if doc['id'] not in admitted_ids:
                        admitted_ids.add(doc['id']);fresh_sources.add(source)
                        st=source_states[source];st['publications'].append(t);st['new_count']+=1
                    if kind in ('window','watch','recovery'):
                        window_ids.add(doc['id'])
                        if kind=='recovery':recovered_ids.append(doc['id'])
            return found

        budget_plan=None;grid_plan=None
        if patent_budget:
            # [0103,0108-0113]: W is one expenditure, never a replacement for E.
            watch_reserve=(min(baseline*cfg.slow_fraction,effective,shared_quota*remaining,
                max(0.,waiting_cap-waiting_spent)) if state=='slow' else 0.)
            probe_reserve=0. if cfg.mode=='fixed' else min(baseline*cfg.band_fraction,
                max(0.,effective-watch_reserve))
            if grid_policy is not None:
                grid_plan=plan_grid_budget(boundary=boundary,earliest=earliest,band_days=cfg.band_days,
                    baseline=baseline,decay=cfg.grid_decay,policy=grid_policy,
                    available=max(0.,effective-watch_reserve))
                probe_reserve=grid_plan['total_allocated']
            recovery_reserve=0.
            if watch_reserve:search('watch',boundary,cutoff,watch_reserve,included,right_closed=True)
            budget_plan=dict(policy=budget_policy,regular_baseline=baseline,effective=effective,
                remaining_at_start=remaining,shared_limit=shared_quota*remaining,
                reserves=dict(probe=probe_reserve,watch=watch_reserve,recovery=0.,window=0.),
                probe_allocation='patent_0205_literal_per_cell' if grid_policy is not None else
                    'existing_normalized_grid_budget_not_paragraph_0205',
                reservation_order='watch_and_probe_then_full_band_then_regular_balance')
        else:
            active={s for s in included if source_states[s]['active']}
            recovery_reserve=0 if cfg.mode=='fixed' else min(effective*cfg.recovery_fraction,shared_quota*remaining)
            probe_reserve=0 if cfg.mode=='fixed' else effective*cfg.band_fraction
            regular_reserve=max(0.,effective-probe_reserve-recovery_reserve)
            if state=='slow':
                regular_reserve=min(regular_reserve,max(0.,shared_quota*remaining-recovery_reserve))
                search('watch',boundary,cutoff,regular_reserve,included,right_closed=True)
            else:
                # Keep exhausted sources reachable by a small watch allocation.
                inactive=included-active
                watch_budget=min(regular_reserve*.2, len(inactive)*(cfg.query_cost+cfg.read_cost)) if inactive else 0
                search('window',boundary,cutoff,regular_reserve-watch_budget,active,right_closed=True)
                search('watch',boundary,cutoff,watch_budget,inactive,right_closed=True)
        band_start=max(earliest,boundary-cfg.band_days)
        if cfg.mode!='fixed' and boundary>band_start:
            if grid_plan is not None:
                for cell in grid_plan['cells']:
                    allowance=cell['allocated_budget']
                    if allowance<=0:
                        if cell['reason']=='insufficient_round_budget':budget_blocked=True
                        continue
                    before=ledger['probe'];reads_before=len(extraction_cache)
                    search('probe',cell['search_start'],cell['search_end'],allowance,included)
                    cell['spent']=ledger['probe']-before
                    cell['body_reads']=len(extraction_cache)-reads_before
                    cell['reason']=('executed' if cell['body_reads'] else
                        'queried_without_new_body_reads' if cell['spent'] else
                        'below_request_cost' if allowance<cfg.query_cost else 'no_pending_metadata')
            elif cfg.mode=='enhanced':
                cells=transition_cells(boundary,boundary-band_start,cfg.grid_days,1.,cfg.grid_decay)
                mass=sum(c['budget'] for c in cells)
                if credit_policy:
                    signature=(band_start,boundary)
                    if signature!=grid_signature:grid_credits={};grid_signature=signature
                    for c in cells:
                        key=(c['start'],c['end'])
                        grid_credits[key]=grid_credits.get(key,0.)+probe_reserve*c['budget']/mass
                    probe_left=probe_reserve
                    for c in sorted(cells,key=lambda c:-grid_credits[(c['start'],c['end'])]):
                        key=(c['start'],c['end'])
                        allowance=min(probe_left,grid_credits[key])
                        if allowance<cfg.query_cost+cfg.read_cost-1e-12:
                            pending=any(c['start']<=d['_day']<c['end'] and
                                d['id'] not in attempted[('probe',source)]
                                for source in included for d in by_source[source])
                            if pending:
                                if probe_reserve>=cfg.query_cost+cfg.read_cost-1e-12:
                                    credit_can_accumulate=True
                                else:budget_blocked=True
                            continue
                        before=ledger['probe']
                        search('probe',c['start'],c['end'],allowance,included)
                        used=ledger['probe']-before
                        grid_credits[key]-=used;probe_left-=used
                else:
                    for c in cells:search('probe',c['start'],c['end'],probe_reserve*c['budget']/mass,included)
            else:search('probe',band_start,boundary,probe_reserve,included)

        def update_sources():
            for source in included:
                st=source_states[source]
                times=sorted(set(st['publications']))
                intervals=[b-a for a,b in zip(times,times[1:]) if b>a]
                wait=median(intervals) if intervals else cfg.default_wait_days
                st['phi']=exhaustion(intervals,st['silence'],wait,cfg.survival_alpha,cfg.mode)
                st['interval_samples']=intervals;st['wait_days']=wait

        def finalize_exposure():
            # Recompute from the round-opening snapshot; never advance elapsed time twice.
            for source in included:
                st=source_states[source];old_silence,old_observed=source_start[source]
                st['observed_days']=old_observed+(interval if spent_by_source[source]>0 else 0.)
                if source in fresh_sources:
                    st.update(silence=0.,active=True,confirmations=0,last_new_round=round_no)
                else:
                    st['silence']=old_silence+interval*(1. if cfg.mode=='basic' else coverage(spent_by_source[source],source_parameter(source,'coverage_scale')))
            update_sources()
        finalize_exposure()
        if patent_budget:
            # Probe observations precede reserving recovery; regular retrieval only
            # consumes the balance. Do not strand a partial reserve for an unaffordable band.
            reserve_sources={source for source in included if source_states[source]['active']
                and source_states[source]['phi']<cfg.source_exhaustion}
            requested_cost=cfg.band_days*sum(source_parameter(source,'cost_per_day') for source in reserve_sources)
            capacity=max(0.,min(effective-probe_reserve-watch_reserve,
                shared_quota*remaining-watch_reserve))
            horizon=boundary-earliest>=cfg.band_days-1e-9
            observed_band=any(band_start<=v['_day']<boundary for v in known.values())
            if (cfg.mode!='fixed' and observed_band and horizon and round_no>cooldown_until
                    and requested_cost<=capacity+1e-12):
                recovery_reserve=min(requested_cost,capacity)
            regular_reserve=max(0.,effective-probe_reserve-watch_reserve-recovery_reserve)
            budget_plan['reserves'].update(recovery=recovery_reserve,window=regular_reserve)
            budget_plan.update(recovery_capacity=capacity,reservation_requested_cost=requested_cost,
                reservation_sources=sorted(reserve_sources))
            # Non-slow source polling is regular retrieval, W=0 per [0112].
            search('window',boundary,cutoff,regular_reserve,included,right_closed=True)
            finalize_exposure()

        def measures(start):
            window=[known[k] for k in window_ids if known[k]['_day']>=start]
            band=[v for v in known.values() if max(earliest,start-cfg.band_days)<=v['_day']<start]
            if cfg.mode=='basic':
                w=weights_for(window,cfg.gamma);bw=weights_for(band,cfg.gamma)
            else:w=weights_for(list(known.values()),cfg.gamma);bw=w
            volume=sum(w[d['id']] for d in window)
            loss=sum(bw[d['id']]*d['relevance'] for d in band)
            return window,w,volume,loss,probabilities(window,w,len(task['outcomes']),cfg.omega)

        window,weights,volume,loss,probs=measures(boundary)
        ratio=loss_ratio(loss,volume);proposed_gain=None;mu=cfg.conversion_cap
        before_window_ids={d['id'] for d in window}
        observation=None
        if decision_trace:
            band_rows=[v for v in known.values() if max(earliest,boundary-cfg.band_days)<=v['_day']<boundary]
            observed_weights=weights_for(band_rows,cfg.gamma) if cfg.mode=='basic' else weights
            observation=dict(boundary=iso(boundary),band_start=iso(band_start),
                window_volume=volume,window_ids=sorted(before_window_ids),loss=loss,loss_ratio=ratio,
                band_evidence=[dict(document_id=v['id'],source_id=v['source_id'],published_at=v['published_at'],
                    weight=observed_weights[v['id']],relevance=v['relevance'],
                    contribution=observed_weights[v['id']]*v['relevance']) for v in sorted(band_rows,key=lambda v:v['id'])])
        if guarded:
            band_metadata=[d for source in included for d in by_source[source] if band_start<=d['_day']<boundary]
            unread=sum(d['id'] not in extraction_cache for d in band_metadata)
            observation.update(visible_band_documents=len(band_metadata),unread_band_documents=unread,
                failed_band_documents=sum(d['id'] in extraction_cache and extraction_cache[d['id']] is None for d in band_metadata),
                loss_scope='observed_admitted_evidence_only',
                unread_support='unknown_not_zero' if unread else 'no_unread_visible_documents')
        costs=sum(x[0] for x in gain_history[-cfg.conversion_window:])
        gains=sum(x[1] for x in gain_history[-cfg.conversion_window:])
        if gains>0:mu=min(cfg.conversion_cap,costs/gains)
        recovery_sources={s for s in included if source_states[s]['active'] and source_states[s]['phi']<cfg.source_exhaustion}
        if credit_policy and not patent_budget:
            recovery_sources={s for s in recovery_sources if any(band_start<=d['_day']<boundary
                              for d in by_source[s])}
        tentative_width=min(cfg.band_days,boundary-earliest)
        unit_cost=(cfg.cost_per_day*len(recovery_sources) if source_parameters is None else
                   sum(source_parameter(source,'cost_per_day') for source in recovery_sources))
        overhead=0. if patent_budget else cfg.query_cost*len(recovery_sources)
        read_reserve=0. if patent_budget else cfg.read_cost
        if patent_budget:
            # Regular polling may change eligibility. Reconcile against the final
            # source set, using only unspent regular allocation; never undo a debit.
            budget_plan['initial_reserves']=dict(budget_plan['reserves'])
            final_capacity=max(0.,min(effective-probe_reserve-watch_reserve-ledger['window'],
                shared_quota*remaining-watch_reserve))
            final_requested=unit_cost*cfg.band_days
            recovery_reserve=0.
            if (cfg.mode!='fixed' and loss>0 and horizon and round_no>cooldown_until
                    and final_requested<=final_capacity+1e-12):
                recovery_reserve=min(final_requested,final_capacity)
            budget_plan['reserves'].update(recovery=recovery_reserve,
                window=max(0.,effective-probe_reserve-watch_reserve-recovery_reserve))
            budget_plan.update(final_recovery_sources=sorted(recovery_sources),
                final_recovery_capacity=final_capacity,final_requested_cost=final_requested)
        allowed=min(recovery_reserve,effective-spent(),max(0.,shared_quota*remaining-ledger['watch']))
        # One read plus every eligible source request is a conservative reserve,
        # not a guarantee that all documents in the interval can be read.
        # Day timestamps lose a few ulps on subtraction. Use one absolute
        # tolerance for strict eligibility and its trace; real shortfalls fail.
        full_horizon_available=(tentative_width>=cfg.band_days or
            math.isclose(tentative_width,cfg.band_days,rel_tol=0.,abs_tol=1e-9))
        requested_width=cfg.band_days if full_band_policy else tentative_width
        full_required_budget=unit_cost*requested_width+overhead+read_reserve
        if full_band_policy:
            # The patent comparator never substitutes a clipped archive interval
            # for its nominal full band. Keep the horizon denial in the trace.
            width=cfg.band_days if (full_horizon_available and unit_cost and
                                    allowed+(1e-12 if patent_budget else 0.)>=full_required_budget) else 0.
        else:
            width=min(tentative_width,max(0.,(allowed-overhead-cfg.read_cost)/unit_cost)) if unit_cost else 0.
        gain_required=full_band_policy or cfg.mode!='basic'
        cooling=round_no<=cooldown_until
        recovery_trace=None
        if decision_trace:
            # Expose the literal gain basis without conflating the basic comparator's
            # full-band loss with evidence inside its budget-limited candidate span.
            candidate_span_loss=sum(observed_weights.get(v['id'],0)*v['relevance'] for v in known.values()
                                    if boundary-width<=v['_day']<boundary) if width else 0.
            candidate_loss=loss if (full_band_policy or cfg.mode=='basic') and width else candidate_span_loss
            candidate_cost=unit_cost*width
            candidate_gain=(frozen_gain if full_band_policy and cooling else
                            mu*candidate_loss-candidate_cost if width else None)
            if cfg.mode=='fixed':decision_reason='fixed_mode'
            elif not loss:decision_reason='no_observed_loss'
            elif ratio<cfg.high_loss:decision_reason='below_high_loss'
            elif not recovery_sources:decision_reason='no_recovery_sources'
            elif full_band_policy and not full_horizon_available:decision_reason='insufficient_archive_horizon'
            elif tentative_width<=0:decision_reason='earliest_boundary_reached'
            elif full_band_policy and cooling:decision_reason='cooldown'
            elif width<=0:decision_reason='insufficient_full_band_budget' if full_band_policy else 'insufficient_recovery_budget'
            elif cfg.mode!='basic' and cooling:decision_reason='cooldown'
            elif gain_required and candidate_gain<0:decision_reason='negative_net_gain'
            else:decision_reason='approved'
            recovery_trace=dict(reason=decision_reason,policy='legacy_budget_limited_partial_band',
                high_loss_threshold=cfg.high_loss,available_budget=allowed,
                limits=dict(recovery_reserve=recovery_reserve,round_remaining=effective-spent(),
                    shared_remaining=max(0.,shared_quota*remaining-ledger['watch'])),
                tentative_width_days=tentative_width,candidate_width_days=width,
                candidate_boundary=iso(boundary-width),unit_cost_per_day=unit_cost,
                query_overhead=overhead,read_reserve=read_reserve,candidate_span_cost=candidate_cost,
                candidate_covered_loss=candidate_loss,candidate_net_gain=candidate_gain,conversion=mu,
                loss_basis='full_band_basic_comparator' if cfg.mode=='basic' else 'candidate_span',
                candidate_span_observed_loss=candidate_span_loss,
                net_gain_required=gain_required,cooldown_until=cooldown_until,
                sources=[dict(source_id=source,eligible=source in recovery_sources,
                    active=source_states[source]['active'],exhaustion=source_states[source]['phi'],
                    has_band_metadata=any(band_start<=d['_day']<boundary for d in by_source[source]),
                    cost_per_day=source_parameter(source,'cost_per_day')) for source in sorted(included)])
            if full_band_policy:
                recovery_trace.update(policy=recovery_policy,effective_policy=recovery_policy,
                    nominal_band_days=cfg.band_days,requested_full_width_days=cfg.band_days,
                    available_archive_width_days=tentative_width,
                    full_required_budget=full_required_budget,
                    clipped_by_earliest_boundary=not full_horizon_available,
                    clipped_by_archive_horizon=not full_horizon_available,
                    nominal_full_band=full_horizon_available,horizon_tolerance_days=1e-9,
                    candidate_boundary=iso(max(earliest,boundary-width)),
                    loss_basis='full_transition_band',
                    block_reason=None if decision_reason=='approved' else decision_reason,
                    net_gain_status='frozen_during_cooldown' if cooling else
                        'evaluated' if width else 'not_evaluated_no_executable_span')
        contraction_trace=None
        if decision_trace:
            pending_probes=[d['id'] for s in included for d in by_source[s]
                if band_start<=d['_day']<boundary and d['id'] not in attempted.get(('probe',s),set())]
            contraction_upper=min(cutoff-cfg.min_window_days,return_ceiling if return_ceiling is not None else cutoff)
            contraction_step=min(cfg.band_days*cfg.shrink_fraction,max(0.,contraction_upper-boundary))
            if cfg.mode=='fixed':contraction_reason='fixed_mode'
            elif ratio>cfg.low_loss:contraction_reason='above_low_loss'
            elif credit_policy and pending_probes:contraction_reason='pending_transition_probes'
            elif contraction_step<=1e-12:contraction_reason='boundary_limit_reached'
            else:contraction_reason='approved'
            contraction_trace=dict(reason=contraction_reason,low_loss_threshold=cfg.low_loss,
                low_loss_passed=ratio<=cfg.low_loss,probe_completion_required=credit_policy,
                probe_complete=not pending_probes,pending_probe_count=len(pending_probes),
                pending_probe_ids=sorted(pending_probes),upper_boundary=iso(contraction_upper),
                min_window_boundary=iso(cutoff-cfg.min_window_days),
                return_ceiling=None if return_ceiling is None else iso(return_ceiling),
                candidate_step_days=contraction_step,candidate_boundary=iso(boundary+contraction_step))
        if cfg.mode!='fixed' and ratio>=cfg.high_loss and width>0 and ((cfg.mode=='basic' and not full_band_policy) or not cooling):
            recovery_cost=unit_cost*width
            # A partial step uses only measured evidence in the actually recovered subinterval.
            covered_loss=sum(weights.get(v['id'],0)*v['relevance'] for v in known.values()
                             if boundary-width<=v['_day']<boundary)
            if full_band_policy or cfg.mode=='basic':covered_loss=loss
            proposed_gain=mu*covered_loss-recovery_cost
            if not gain_required or proposed_gain>=0:
                old=boundary;boundary-=width;return_ceiling=old
                if full_band_policy:boundary=max(earliest,boundary)
                ledger['recovery']+=recovery_cost
                if patent_budget:
                    for source in recovery_sources:
                        spent_by_source[source]+=source_parameter(source,'cost_per_day')*width
                search('recovery',boundary,old,allowed-recovery_cost,recovery_sources)
                for s in fresh_sources:
                    source_states[s].update(silence=0.,active=True,confirmations=0,last_new_round=round_no)
                update_sources()
                action='expand';frozen_gain=proposed_gain;cooldown_until=round_no+cfg.confirmation_rounds
        elif cfg.mode!='fixed' and ratio<=cfg.low_loss and (not credit_policy or
            all(d['id'] in attempted[('probe',s)] for s in included for d in by_source[s]
                if band_start<=d['_day']<boundary)):
            upper=min(cutoff-cfg.min_window_days,return_ceiling if return_ceiling is not None else cutoff)
            step=min(cfg.band_days*cfg.shrink_fraction,max(0.,upper-boundary))
            if step>1e-12:
                boundary+=step;action='contract';convergence_skipped=True;history=[]

        # Optional embodiment: uncertainty expansion, only when no ordinary motion was selected.
        if cfg.enable_uncertainty_expansion and cfg.mode!='fixed' and action=='hold' and start_state=='continue' and uncertainty(probs)>=cfg.uncertainty_threshold and round_no>cooldown_until:
            if width>0:
                old=boundary;boundary-=width;return_ceiling=old
                ledger['recovery']+=unit_cost*width
                search('recovery',boundary,old,allowed-unit_cost*width,recovery_sources)
                for s in fresh_sources:source_states[s].update(silence=0.,active=True,confirmations=0,last_new_round=round_no)
                update_sources();action='uncertainty_expand';cooldown_until=round_no+cfg.confirmation_rounds
            # Uniform source cost in this simulator; unknown yields tie-break lexicographically.
            available=effective-spent()
            for s in sources:
                if s not in included and available>=cfg.query_cost+cfg.read_cost:
                    included.add(s);available-=cfg.query_cost+cfg.read_cost

        finalize_exposure()
        window,weights,volume,post_loss,probs=measures(boundary)
        delta=volume-previous_volume;distance=total_variation(probs,previous_probs)
        if not convergence_skipped:history.append(delta)
        history=history[-cfg.confirmation_rounds:]
        for source in included:
            st=source_states[source]
            if st['phi']>=cfg.source_exhaustion:
                st['confirmations']+=1
                if st['confirmations']>=cfg.source_confirmation_rounds:st['active']=False
            else:st['confirmations']=0
        phis=[source_states[s]['phi'] for s in sorted(included)]
        stop=cfg.mode!='fixed' and not convergence_skipped and can_stop(phis,history,cfg.convergence,cfg.epsilon,cfg.mode)
        if stop:state='stop';reason='evidence_converged'
        elif cfg.mode!='fixed':
            if start_state=='slow' and delta>cfg.epsilon:
                state='continue';waiting_cap=None;waiting_spent=0.
            elif distance<=cfg.stable_distance:
                state='slow'
                if waiting_cap is None:waiting_cap=max(0.,remaining-spent())*waiting_share;waiting_spent=0.
        cost=spent()
        if cost>effective+1e-8 or cost>remaining+1e-8:raise RuntimeError('Budget invariant violated')
        # S107 applies to executable phase allocations, not only their sum.
        # Empty metadata routes are not exhaustion; affordable future grid
        # credit must retain its opportunity to accumulate on later rounds.
        if cost==0 and budget_blocked and not credit_can_accumulate:
            state='stop'
            reason='waiting_budget_exhausted' if start_state=='slow' else 'budget_exhausted'
        remaining=max(0.,remaining-cost)
        if start_state=='slow':
            if not patent_budget:waiting_spent+=cost
            elif waiting_cap is not None:waiting_spent+=ledger['watch']
        if state!='stop' and start_state=='slow' and waiting_cap is not None and waiting_spent>=waiting_cap-1e-9:
            state='stop';reason='waiting_budget_exhausted'
        if runtime_policy is not None and state!='stop' and virtual_time>=runtime_policy['task_duration_days']:
            state='stop';reason='task_deadline_reached'
        source_snapshot={s:{k:v for k,v in source_states[s].items() if k!='publications'} for s in sorted(included)}
        rows.append(dict(round=round_no,state_before=start_state,state=state,action=action,
                         boundary_before=iso(current_boundary),boundary_after=iso(boundary),cutoff=task['cutoff'],
                         window_days=cutoff-boundary,volume=volume,delta=delta,probabilities=probs,
                         distance=distance,uncertainty=uncertainty(probs),loss=loss,loss_ratio=ratio,
                         post_loss=post_loss,net_gain=proposed_gain,frozen_net_gain=frozen_gain,
                         conversion=mu,cooldown_remaining=max(0,cooldown_until-round_no),
                         budget=ledger,spent=cost,remaining=remaining,virtual_days=virtual_time,
                         source_states=source_snapshot,source_budgets=dict(spent_by_source),
                         body_reads=len(extraction_cache)-read_start,
                         retrieved_ids=retrieved_ids,recovered_ids=sorted(set(recovered_ids)),
                         window_ids=sorted(d['id'] for d in window),convergence_skipped=convergence_skipped))
        if guarded:
            rows[-1]['read_execution']=read_execution
        if patent_budget:
            if ledger['watch']+ledger['recovery']>shared_quota*budget_plan['remaining_at_start']+1e-8:
                raise RuntimeError('Shared quota invariant violated')
            budget_plan['actual']=dict(ledger)
            budget_plan['unspent_reserved']=sum(budget_plan['reserves'].values())-cost
        if decision_trace:
            after_window_ids={d['id'] for d in window}
            contraction_trace['executed']=action=='contract'
            recovery_trace['executed']=action=='expand'
            recovery_trace['actual_recovered_ids']=sorted(set(recovered_ids))
            recovery_trace['uncertainty_expansion_executed']=action=='uncertainty_expand'
            if full_band_policy:
                recovery_trace['actual_recovery_step_days']=current_boundary-boundary if action=='expand' else 0.
            rows[-1]['decision_trace']=dict(loss_observation=observation,recovery=recovery_trace,contraction=contraction_trace,
                retrieval_events=retrieval_events,runtime_parameters=parameter_trace,
                waiting_budget=dict(locked_cap=waiting_cap,cumulative_spent=waiting_spent,
                    share_for_new_entry=waiting_share,shared_quota=shared_quota),
                boundary_adjustment=dict(action=action,before=iso(current_boundary),after=iso(boundary),
                    entered_ids=sorted(after_window_ids-before_window_ids),removed_ids=sorted(before_window_ids-after_window_ids),
                    low_loss_threshold=cfg.low_loss,high_loss_threshold=cfg.high_loss,
                    post_window_volume=volume,post_loss=post_loss,
                    loss_ratio_evaluated_before_boundary_adjustment=True))
        if patent_budget:
            rows[-1]['decision_trace']['budget_plan']=budget_plan
            if grid_plan is not None:rows[-1]['decision_trace']['grid_budget']=grid_plan
            rows[-1]['decision_trace']['waiting_budget'].update(opening_cap=waiting_opening_cap,
                opening_spent=waiting_opening_spent,charged_this_round=ledger['watch'])
        if credit_policy:
            rows[-1]['probe_credit_total']=sum(grid_credits.values())
            rows[-1]['routing_policy']='frozen_metadata_pending_documents'
        if guarded:
            rows[-1]['decision_trace']['read_execution']=rows[-1].pop('read_execution')
        if observer is not None:
            # Progress consumers receive an isolated snapshot, never live engine state.
            from copy import deepcopy
            observer(deepcopy(rows[-1]))
        gain_history.append((cost,delta));previous_volume=volume;previous_probs=probs
        if state=='stop':break
        if not patent_budget and remaining<cfg.query_cost-1e-12:reason='budget_exhausted';break
    final_window,final_weights,_,_,final_probs=measures(boundary) if rows else ([],{},0,0,previous_probs)
    exported=[]
    for d in sorted(known.values(),key=lambda x:x['id']):
        item={k:v for k,v in d.items() if not k.startswith('_') and k!='text'}
        item['weight']=final_weights.get(d['id'],0.)
        item['in_final_window']=d['id'] in {x['id'] for x in final_window}
        exported.append(item)
    unresolved=[s for s in sorted(included) if source_states[s]['phi']<cfg.source_exhaustion]
    input_records=[{k:d.get(k) for k in ('id','canonical_url','published_at','observed_at','source_file','source_id')}
                   | {'body_sha256':hashlib.sha256(d.get('text','').encode('utf-8')).hexdigest()}
                   for d in sorted(candidates,key=lambda x:x['id'])]
    visible_annotations={d['id']:annotations[d['id']] for d in candidates if annotations and d['id'] in annotations}
    if annotation_provider is not None:visible_annotations=provider_annotations
    def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
    output = dict(task={k:v for k,v in task.items() if k not in ('outcome_prices','final_prices','resolved_outcome')},
                provenance=dict(inputs=input_records,annotations=visible_annotations,
                                input_sha256=digest(input_records),annotation_sha256=digest(visible_annotations)),
                config=asdict(cfg),result=dict(probabilities=final_probs,termination_reason=reason,
                spent=cfg.total_budget-remaining,remaining_budget=remaining,rounds=len(rows),
                unresolved_sources=unresolved,final_boundary=iso(boundary),
                evidence_count=len(final_window),supporting_evidence_count=sum(any(d['support']) for d in final_window)),
                rounds=rows,evidence=exported,
                diagnostics=dict(excluded_temporal_or_foreign=excluded,visible_documents=len(candidates),
                body_reads=len(extraction_cache),
                extracted_documents=len(extraction_cache),admitted_documents=len(known),
                cost_model='simulated_request_read_and_recovery_units',clock='simulated_days_fixed_archive_cutoff',
                parameter_status='illustrative_uncalibrated',label_access=False,
                limitation='Lexical elements are heuristic; unconfigured support abstains. Observed archive is not exhaustive source output.'))

    if decision_trace:
        output['provenance']['decision_trace_version']='loss_recovery_parameters_v1'
    if full_band_policy:
        output['provenance']['recovery_policy']=recovery_policy
    if patent_budget:
        output['provenance']['budget_policy']=budget_policy
        output['diagnostics'].update(cost_model='patent_inclusive_recovery_span_budget_units',
            regular_round_baseline=baseline,recovery_cost_includes_request_and_read=True,
            legacy_round_budget_ignored=True,legacy_recovery_fraction_ignored=True,
            probe_budget_status='existing_normalized_total_cap_not_full_grid_formula')
    if guarded:
        output['provenance']['retrieval_policy']=retrieval_policy
        output['diagnostics']['retrieval_execution']=dict(preflight=retrieval_preflight,
            indexed_document_ids=sorted(ranker.indexed_ids) if ranker else [],
            indexed_chunks=ranker.chunk_count if ranker else 0,
            index_cost='offline_text_indexing_not_in_simulated_budget_not_measured_money',
            scoring_scope='same_source_and_authorized_time_interval',
            annotation_input='original_full_document_unchanged',
            request_count=sum(r['decision_trace']['read_execution']['requests_executed'] for r in rows),
            skipped_unaffordable_requests=sum(len(r['decision_trace']['read_execution']['skipped']) for r in rows))
    if grid_policy is not None:
        output['provenance']['grid_policy']=grid_policy
        output['diagnostics'].update(probe_budget_status='patent_0205_literal_per_cell',
            legacy_band_fraction_ignored=True,legacy_grid_days_ignored=True)
    if cost_configuration is not None:
        output['provenance']['source_cost_profile']=cost_configuration['provenance']
        output['diagnostics']['source_cost_profile']=cost_configuration['diagnostics']
    if grid_policy is not None or cost_configuration is not None:
        total_source_cost=sum(source_parameter(source,'cost_per_day') for source in included)
        output['diagnostics']['budget_feasibility']=dict(regular_baseline=baseline,
            source_cost_sum_per_day=total_source_cost,all_included_full_band_cost=total_source_cost*cfg.band_days,
            fits_whole_round=total_source_cost*cfg.band_days<=baseline,
            scope='opening_included_sources_upper_bound_not_actual_recovery_decision',
            cost_status='provided_profile' if cost_configuration else
                'explicit_overrides' if source_parameters is not None else 'uniform_uncalibrated_example')
    if runtime_policy is not None:
        output['provenance']['runtime_policy']=runtime_policy
        output['diagnostics']['runtime_policy_status']='explicit_supplied_table_not_empirical_calibration'
    if evidence_policy is not None:
        output['provenance']['evidence_policy']=evidence_policy
        output['diagnostics']['evidence_policy']='normalized_overlap_separate_explicit_support_rules_exact_fact_groups'
    if comparison_policy is not None:
        output['provenance']['comparison_policy']=comparison_policy
    if source_parameters is not None:
        output['provenance']['source_parameters']=source_parameters
        output['diagnostics']['parameter_status']='explicit_source_overrides_not_all_parameters_calibrated'
    if annotation_provider is not None:
        output['diagnostics'].update(extraction_mode='on_demand',
            annotation_failures=annotation_failures,validated_annotations=len(provider_annotations))
        output['provenance']['extraction_mode']='on_demand'
    if fact_policy != 'legacy':
        output['provenance']['fact_policy']=fact_policy
        # Full grouping trace is supplied by the experiment runner; weights above
        # are calculated on the actual admitted records of each round.
    return output
