"""Bounded model extraction, frozen evidence replay and label-blind task selection.

Model annotations are structurally validated machine outputs, never human truth.
The extraction bill is reported separately from simulated retrieval budgets.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re

from .automatic import automatic_rules
from .call_cost import CallCostLedger, CallCostError
from .cli import market_directory, save_run, write_json
from .data.store import utc_iso
from .engine import run
from .evaluation import summarize_comparison
from .evidence import prepare_task
from .models import Config
from .preparation import prepare_cohort
from .reviewpack import page, validate_output
from .semantic import DeepSeekClient, build_evidence_messages, validate_semantic, PROMPT_VERSION, CONTEXT_FIELDS

ROOT = Path(__file__).resolve().parents[2]
MODES = ('fixed', 'basic', 'enhanced')
SELECTION_POLICY = 'subject_phrase_then_question_title_overlap_then_publication_recency_then_observation_recency_then_id_v1'
LIMITATIONS = [
    'Model-generated, structurally validated annotations are not human-reviewed truth or verified outcomes.',
    'This is a bounded selected-document pilot, not an extraction run over the full available corpus.',
    'Historical backtests may contain model future knowledge even when prompts restrict answers to supplied evidence.',
    'Retrieval budgets are simulated units. Actual LLM preprocessing tokens are separate and are not free cost savings.',
    'Price proxy comparison is not official settlement evaluation; this run establishes no prediction-quality claim.',
    'Source timestamps and semantic deadline eligibility are not independently verified.',
]


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def select_documents(task, documents, max_documents=10):
    """Select without labels, model outputs or directional support scores."""
    cutoff = utc_iso(task['cutoff'])
    tokens = set(re.findall(r'\w+', task['question'].casefold()))
    subject = str(task['target_elements'].get('subject', '')).casefold()
    candidates = []
    for document in documents:
        try:
            published = utc_iso(document['published_at'])
            observed = utc_iso(document['observed_at'])
        except (ValueError, TypeError, KeyError):
            continue
        if published > cutoff or observed > cutoff:
            continue
        if task.get('event_id') and document.get('event_id') != task['event_id']:
            continue
        title = str(document.get('title', '')).casefold()
        phrase = bool(subject and re.search(r'(?<!\w)' + re.escape(subject) + r'(?!\w)', title))
        overlap = len(tokens & set(re.findall(r'\w+', title)))
        timestamps = [datetime.fromisoformat(t.replace('Z', '+00:00')).timestamp()
                      for t in (published, observed)]
        candidates.append(((-int(phrase), -overlap, -timestamps[0], -timestamps[1], str(document['id'])), document))
    return [row for _, row in sorted(candidates, key=lambda value: value[0])[:max_documents]]


def _extract_one(client, task, document, max_chars):
    try:
        messages = build_evidence_messages(task, document, max_chars=max_chars)
    except ValueError:
        if task.get('evidence_context_policy')!='fact_window_v1':raise
        return None,dict(document_id=document['id'],status='failed',metadata={},error_type='ValueError',error='source_context_preflight_failed',model_request_made=False)
    context=json.loads(messages[1]['content'])['evidence']
    excerpt=context['excerpt']
    context_metadata={k:context[k] for k in CONTEXT_FIELDS if k in context}
    trace = dict(document_id=document['id'], prompt_sha256=_digest(messages),
                 selected_excerpt=excerpt, status='failed', metadata={})
    if context_metadata:trace['excerpt_context']=context_metadata
    try:
        response = client.complete_json(messages, max_tokens=1800)
        metadata = response['metadata']
        trace['metadata'] = {key: metadata[key] for key in (
            'model', 'requested_model', 'usage', 'request_id', 'cache_key', 'cache_hit',
            'finish_reason', 'attempts') if key in metadata}
        trace['parsed_response'] = response['data']
        annotation = validate_semantic(response['data'], task, document,
                                       dict(metadata, excerpt=excerpt, **context_metadata))
        trace['status'] = 'validated'
        return annotation, trace
    except CallCostError:
        raise
    except Exception as exc:
        # Exception messages from transports or injected clients can contain keys.
        # Preserve classification only; never serialize exception repr or args.
        trace['error_type'] = type(exc).__name__
        trace['error'] = 'request_or_structural_validation_failed'
        return None, trace


def _usage(traces):
    counts = dict(requested_documents=len(traces), validated_documents=0,
                  failed_documents=0, cached_calls=0, uncached_responses=0,
                  prompt_tokens=0, completion_tokens=0, total_tokens=0,
                  uncached_prompt_tokens=0, uncached_completion_tokens=0,
                  uncached_total_tokens=0, returned_models=[])
    models = set()
    for trace in traces:
        counts['validated_documents' if trace['status'] == 'validated' else 'failed_documents'] += 1
        metadata = trace['metadata']
        if metadata.get('model'):
            models.add(metadata['model'])
        cached = metadata.get('cache_hit') is True
        counts['cached_calls'] += int(cached)
        counts['uncached_responses'] += int(bool(metadata) and not cached)
        for field in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
            value = metadata.get('usage', {}).get(field, 0)
            if type(value) is int and value >= 0:
                counts[field] += value
                if not cached:
                    counts['uncached_' + field] += value
    counts['returned_models'] = sorted(models)
    counts['accounting_note'] = ('Token totals describe returned responses, including reused cache responses. '
        'Uncached token totals exclude local cache hits; transport failures/retries without returned usage '
        'may still incur unreported charges. Monetary cost is not estimated.')
    return counts


def execution_modes(execution, config):
    """One explicit policy contract, with enhanced-only grids removed for baselines."""
    from .web_jobs import validated_execution
    canonical=validated_execution(execution,replace(config,mode='enhanced'))
    modes={}
    for mode in MODES:
        value=dict(canonical)
        if mode!='enhanced':value.pop('grid_policy',None)
        modes[mode]=validated_execution(value,replace(config,mode=mode))
    return canonical,modes


def run_semantic_pipeline(store, data_root, cutoff, output, count=5, min_documents=5,
                          max_metadata_age_days=7, seed='patent-v1', config=None,
                          max_documents=10, workers=3, max_chars=12000,
                          model='deepseek-flash', cache=None, client=None, prepared_cohort=None, repair_policies=False,
                          matching_policy='typed_v3', observer=None, execution=None, extraction_mode='shared'):
    """Run a frozen three-mode comparison with shared or mode-specific extraction."""
    for name, value in (('count', count), ('min_documents', min_documents),
                        ('max_documents', max_documents), ('workers', workers), ('max_chars', max_chars)):
        if type(value) is not int or value < 1:
            raise ValueError(name + ' must be a positive integer')
    if max_chars>12000:raise ValueError('max_chars must not exceed 12000')
    if matching_policy not in ('typed_v3','typed_v4','typed_v5'):raise ValueError('Unsupported matching policy')
    if extraction_mode not in ('shared','on_demand'):raise ValueError('Unknown extraction_mode')
    config=config or Config()
    execution,mode_execution=execution_modes(execution,config)
    output = validate_output(output, data_root)
    data_root = Path(data_root).resolve()
    cache = Path(cache or ROOT / 'artifacts/deepseek-cache').resolve()
    if cache.is_relative_to(data_root):
        raise ValueError('Cache must be outside the read-only raw data directory')
    if cache.is_relative_to(output) or output.is_relative_to(cache):
        raise ValueError('Cache and output must be separate, non-nested directories')
    if cache.exists() and not cache.is_dir():
        raise ValueError('Cache must be a directory')
    cutoff = utc_iso(cutoff)
    config = config or Config()
    frozen_plan = None
    selection_policy = SELECTION_POLICY
    if prepared_cohort is None:
        cohort = prepare_cohort(store, data_root, cutoff, count, min_documents, max_metadata_age_days, seed)
    else:
        from .expansion import load_expansion
        cohort, frozen_plan = load_expansion(prepared_cohort, cutoff, config)
        if frozen_plan.get('execution',{})!=execution or frozen_plan.get('extraction_mode','shared')!=extraction_mode:
            raise ValueError('Frozen execution mismatch')
        count = len(cohort['selected'])
        if not count: raise ValueError('Frozen cohort is empty')
        max_documents = frozen_plan['target_documents_per_task']
        selection_policy = frozen_plan['policy']
        write_json(output / 'inputs/pre-model-plan.json', frozen_plan)
    prepared_tasks=[]
    for item in cohort['selected']:
        task = dict(item['task'])
        try:
            rules = automatic_rules(task)
            rules = {key: rules[key] for key in ('target_elements', 'element_aliases')}
            targets_origin = 'supported_family_target_elements_only'
        except ValueError:
            rules = {key: task.get(key, {}) for key in ('target_elements', 'element_aliases')}
            targets_origin = 'prepared_task_targets'
        task.update(rules)
        for field in ('positive_patterns', 'negative_patterns'):
            task.pop(field, None)
        task = prepare_task(task)
        if repair_policies:
            from .matching import normalize_task
            task=normalize_task(task,policy=matching_policy)
            task.update(scheduler_policy='grid_credit_v2',semantic_policy='fact_v3')
            targets_origin=task['task_extraction']
        prepared_tasks.append((task,targets_origin))
    # Validate every task and every mode against the full selected source metadata
    # before creating a model client. These offline results are discarded.
    selected_documents=[]
    for item,(task,_) in zip(cohort['selected'],prepared_tasks):
        docs=item['documents'] if frozen_plan is not None else select_documents(task,item['documents'],max_documents)
        selected_documents.append(docs)
        if execution:
            for mode in MODES:
                run(task,docs,replace(config,mode=mode),{},**mode_execution[mode])
    if repair_policies:
        write_json(output/'inputs/effective-tasks.json',[x[0] for x in prepared_tasks])
    inputs = {key: value for key, value in cohort.items() if key != 'selected'}
    inputs['status'] = 'automatic_machine_annotation_pilot'
    inputs['provenance']['selection_status'] = 'automatic_metadata_candidates'
    inputs['provenance']['limitations'] = LIMITATIONS
    inputs['selected'] = []
    write_json(output / 'inputs/extraction-protocol.json', dict(
        requested_model=model, prompt_version='evidence-semantics-v3' if repair_policies else PROMPT_VERSION, max_chars=max_chars,
        repair_policies=repair_policies,execution=execution,extraction_mode=extraction_mode,
        comparison_inputs='shared_validated_annotations' if extraction_mode=='shared' else 'shared_candidate_corpus_mode_specific_model_reads',
        max_tokens=1800, temperature=0, thinking='disabled',
        response_format='json_object', validated_subset_only=True))
    summaries, all_traces, pending = [], [], []
    progress=dict(completed_documents=0,validated_documents=0,failed_documents=0,completed_runs=0,
                  total_documents=sum(map(len,selected_documents))*(3 if extraction_mode=='on_demand' else 1))
    def emit(**event):
        if observer is not None:
            from copy import deepcopy
            observer(deepcopy(dict(progress,**event)))
    mode_ledgers=[]
    if cohort['selected'] and client is None and extraction_mode=='shared':
        client = DeepSeekClient(cache_dir=cache, model=model,max_attempts=1,
            cost_ledger=CallCostLedger(output/'model-call-attempts.jsonl'))
    for number, item in enumerate(cohort['selected'], 1):
        task,targets_origin=prepared_tasks[number-1]
        docs = selected_documents[number-1]
        available_count = item.get('available_documents', len(item['documents']))
        name = market_directory(task['market_id'])
        folder = output / 'runs' / name
        input_folder = output / 'inputs/tasks' / name
        write_json(input_folder / 'task.json', task)
        write_json(input_folder / 'target-elements.json', dict({key:task.get(key,{}) for key in ('target_elements','element_aliases')}, origin=targets_origin))
        write_json(input_folder / 'sampled-documents.json', docs)
        if extraction_mode=='on_demand':
            # The engine provenance covers every candidate, including unread and
            # failed reads. Keep that exact corpus for verified offline replay.
            write_json(input_folder/'documents.json',docs)
        write_json(input_folder / 'eligibility.json', item['eligibility'])
        sample = dict(market_id=task['market_id'], event_id=task['event_id'],
                      available_documents=available_count, sampled_documents=len(docs),
                      selected_ids=[doc['id'] for doc in docs], policy=selection_policy,
                      max_documents=max_documents, max_chars=max_chars,
                      frozen_sampling=item.get('sampling'))
        write_json(input_folder / 'sampling.json', sample)
        inputs['selected'].append(sample)
        print(f"Semantic extraction {number}/{len(cohort['selected'])}: {task['market_id']}, "
              f"{len(docs)}/{available_count} documents", flush=True)
        emit(stage='extracting',market_id=task['market_id'])
        policy_error=None
        if extraction_mode=='shared':
            extracted=[None]*len(docs)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures={executor.submit(_extract_one,client,task,doc,max_chars):i for i,doc in enumerate(docs)}
                for future in as_completed(futures):
                    pair=future.result()
                    extracted[futures[future]]=pair
                    progress['completed_documents']+=1
                    progress['validated_documents' if pair[0] is not None else 'failed_documents']+=1
                    with (output/'partial-extraction.jsonl').open('a',encoding='utf-8') as stream:
                        stream.write(json.dumps(dict(pair[1],market_id=task['market_id']),ensure_ascii=False)+'\n')
                    emit(stage='extracting',market_id=task['market_id'],model_usage=_usage(all_traces+[x[1] for x in extracted if x is not None]))
            annotations = {doc['id']: annotation for doc, (annotation, _) in zip(docs, extracted)
                           if annotation is not None}
            traces = [trace for _, trace in extracted]
            valid_docs = [doc for doc in docs if doc['id'] in annotations]
            write_json(folder / 'machine-annotations.json', annotations)
            write_json(folder / 'extraction-trace.json', traces)
            write_json(input_folder / 'forecast-documents.json', valid_docs)
            all_traces.extend(traces)
            results = {}
            if execution.get('source_cost_profile') is not None and {d['source_id'] for d in valid_docs}!={d['source_id'] for d in docs}:
                policy_error='source_cost_profile_source_set_changed_after_extraction'
            else:policy_error=None
            # A failed document never enters the engine as a made-up zero-support row.
            if valid_docs and policy_error is None:
                for mode in MODES:
                    result = run(task, valid_docs, replace(config, mode=mode), annotations,**mode_execution[mode],
                        observer=(lambda row: emit(stage='running_engine',market_id=task['market_id'],mode=mode,
                            completed_rounds=row['round'],last_round=row)) if observer else None)
                    result['provenance'].update(extraction_mode=extraction_mode,execution=mode_execution[mode])
                    result['diagnostics'].update(
                        data_kind='real_archive_model_semantic_pilot', human_reviewed=False,
                        semantic_validation='structural_only_not_human_truth',
                        available_documents=available_count, sampled_documents=len(docs),
                        model_validated_documents=len(valid_docs), failed_documents=len(docs)-len(valid_docs),
                        source_budget_units='simulation', llm_preprocessing_cost_in_source_budget=False,
                        model_knowledge_contamination_possible=True)
                    save_run(result, folder / mode)
                    results[mode] = result
                    progress['completed_runs']+=1
                    emit(stage='saving',market_id=task['market_id'],mode=mode)
        else:
            from copy import copy
            from .on_demand import run_on_demand
            results={};traces=[];annotations={}
            for mode in MODES:
                mode_folder=folder/mode
                ledger=CallCostLedger(mode_folder/'model-call-attempts.jsonl')
                if client is None:
                    mode_client=DeepSeekClient(cache_dir=cache,model=model,max_attempts=1,cost_ledger=ledger)
                else:
                    mode_client=copy(client)
                    mode_client.cost_ledger=ledger
                result=run_on_demand(task,docs,replace(config,mode=mode),mode_client,max_chars=max_chars,
                    **mode_execution[mode],observer=(lambda row: emit(stage='running_engine',
                        market_id=task['market_id'],mode=mode,completed_rounds=row['round'],last_round=row)) if observer else None)
                mode_traces=result['extraction_trace']
                traces.extend(dict(trace,mode=mode) for trace in mode_traces)
                accounting=ledger.snapshot()
                write_json(mode_folder/'model-call-ledger.json',accounting)
                mode_ledgers.append(dict(market_id=task['market_id'],mode=mode,
                    accounting={k:v for k,v in accounting.items() if k!='events'},
                    accounting_status='measured_client_ledger' if client is None or isinstance(client,DeepSeekClient) else 'unavailable_injected_client',
                    usage=_usage(mode_traces)))
                progress['completed_documents']+=len(mode_traces)
                progress['validated_documents']+=sum(t['status']=='validated' for t in mode_traces)
                progress['failed_documents']+=sum(t['status']!='validated' for t in mode_traces)
                result['provenance'].update(extraction_mode=extraction_mode,execution=mode_execution[mode])
                result['diagnostics'].update(data_kind='real_archive_model_semantic_pilot',human_reviewed=False,
                    semantic_validation='structural_only_not_human_truth',source_budget_units='simulation',
                    llm_preprocessing_cost_in_source_budget=False,model_knowledge_contamination_possible=True)
                save_run(result,mode_folder)
                results[mode]=result
                progress['completed_runs']+=1
                emit(stage='saving',market_id=task['market_id'],mode=mode,model_usage=_usage(all_traces+traces))
            valid_ids={t['document_id'] for t in traces if t['status']=='validated'}
            valid_docs=[d for d in docs if d['id'] in valid_ids]
            all_traces.extend(traces)
            write_json(folder/'extraction-trace.json',traces)
            write_json(input_folder/'forecast-documents.json',valid_docs)
        failed_ids={t['document_id'] for t in traces if t['status']!='validated'}
        attempted_ids={t['document_id'] for t in traces}
        summary = dict(market_id=task['market_id'], event_id=task['event_id'], question=task['question'],
            cutoff=cutoff, available_documents=available_count, sampled_documents=len(docs),
            validated_documents=len(valid_docs), failed_documents=len(failed_ids),unread_documents=len(docs)-len(attempted_ids),
            directional_documents=sum(any(a['support']) for a in annotations.values()) if extraction_mode=='shared' else None,
            execution_error=policy_error,extraction_mode=extraction_mode,
            completed_runs=len(results), human_reviewed=False, llm_preprocessing=_usage(traces),
            eligibility=item['eligibility'], directory='runs/' + name)
        summaries.append(summary)
        pending.append((summary, results, folder))
        print(f"Semantic extraction {number}/{len(cohort['selected'])}: "
              f"{len(valid_docs)} validated, {len(failed_ids)} failed; {len(results)} runs saved", flush=True)
    # All forecasts for all tasks are frozen before the first label access.
    for summary, results, folder in pending:
        if results:
            comparison = summarize_comparison(results, store.labels(summary['market_id']))
            write_json(folder / 'comparison.json', comparison)
            summary['comparison'] = comparison
    usage = _usage(all_traces)
    completed = sum(row['completed_runs'] == 3 for row in summaries)
    if usage['failed_documents']:
        status = 'partial_model_failures'
    elif len(summaries) != count or completed != count:
        status = 'incomplete_candidate_count'
    else:
        status = 'completed_semantic_experiment'
    summary = dict(status=status, requested_tasks=count, selected_tasks=len(summaries),
        completed_tasks=completed, completed_runs=sum(row['completed_runs'] for row in summaries),
        available_documents=sum(row['available_documents'] for row in summaries),
        sampled_documents=sum(row['sampled_documents'] for row in summaries), validated_documents=usage['validated_documents'],
        expected_calls=progress['total_documents'],
        frozen_target_tasks=frozen_plan['target_tasks'] if frozen_plan else None,
        requested_model=model, human_reviewed=False, official_outcomes_verified=False,
        semantic_validation='model_generated_structurally_validated_not_human_truth',
        source_budget_units='simulation', llm_preprocessing=usage,execution=execution,extraction_mode=extraction_mode,
        mode_execution=mode_execution,model_request_upper_bound=progress['total_documents'],mode_model_accounting=mode_ledgers,
        max_documents=max_documents, workers=workers, max_chars=max_chars,
        selection_policy=selection_policy, tasks=summaries, limitations=LIMITATIONS)
    write_json(output / 'inputs/cohort.json', inputs)
    ledger=getattr(client,'cost_ledger',None) if extraction_mode=='shared' else None
    if ledger is not None:
        accounting=ledger.snapshot()
        write_json(output/'model-call-ledger.json',accounting)
        summary['model_call_accounting']={k:v for k,v in accounting.items() if k!='events'}
    else:
        summary['model_call_accounting']={'status':'separate_mode_ledgers' if extraction_mode=='on_demand' else 'unavailable_injected_client'}
    write_json(output / 'summary.json', summary)
    _write_report(output, summary, pending)
    files = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(output.rglob('*')) if p.is_file()}
    code_files = list((ROOT / 'src').rglob('*.py')) + [ROOT / 'run_deepseek.py']
    code = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(code_files) if p.is_file()}
    write_json(output / 'manifest.json', dict(artifact_type='semantic_pipeline', format_version=1,
        files=files, code_sha256=code, status=status, requested_model=model,
        returned_models=usage['returned_models'],execution=execution,extraction_mode=extraction_mode))
    emit(stage='completed' if status=='completed_semantic_experiment' else 'partial',model_usage=usage)
    return summary


def _write_report(output, summary, pending):
    rows = []
    for task_summary, results, _ in pending:
        for mode, result in results.items():
            names = [str(value).casefold() for value in result['task']['outcomes']]
            probabilities = result['result']['probabilities']
            yes_no = [probabilities[names.index(label)] for label in ('yes', 'no')]
            rows.append('<tr><td>' + html.escape(task_summary['question']) + '</td><td><a href="' +
                task_summary['directory'] + '/' + mode + '/report.html">' + mode + '</a></td><td>' +
                ' / '.join(f'{value:.3f}' for value in yes_no) + '</td><td>' +
                f"{result['result']['spent']:.2f}" + '</td><td>' +
                str(result['result']['supporting_evidence_count']) + '</td></tr>')
    body = '<div class="note">模型生成、结构校验通过的机器标注，未经过人工审核，也不是真值。历史回测中的模型可能携带未来知识，即使提示词限定只使用所给证据。此运行不构成预测质量结论。</div>'
    body += '<p>状态：' + html.escape(summary['status']) + '；完成 ' + str(summary['completed_tasks']) + '/' + str(summary['requested_tasks']) + ' 个任务，' + str(summary['completed_runs']) + ' 次方案运行。</p>'
    body += '<p>全量可用正文 ' + str(summary['available_documents']) + ' 篇；实际抽样 ' + str(summary['sampled_documents']) + ' 篇；成功校验 ' + str(summary['validated_documents']) + ' 篇。'+('三个方案共享这些成功校验的固定输入。' if summary.get('extraction_mode','shared')=='shared' else '按需运行中的校验次数可包含多个模式对同一文档的读取。')+'</p>'
    if summary.get('extraction_mode')=='on_demand':
        body+='<p>按需抽取：三种模式共享候选正文，分别调用模型并记录独立用量；各模式实际读取的输入可能不同，不能视为共享标注对照。模型请求上限 '+str(summary['model_request_upper_bound'])+'，缓存复用不保证零账单。</p>'
    if summary.get('extraction_mode','shared')=='shared':
        directional = sum(task['directional_documents'] or 0 for task in summary['tasks'])
        body += '<p>抽样中非零机器支持 ' + str(directional) + ' 篇；它们仍需通过窗口与相关性准入，不能等同于最终纳入的有向证据。下表列出最终窗口的实际支持数；没有有效方向性证据时概率保持 0.5 / 0.5。</p>'
    body += '<p>来源检索消耗为模拟单位；LLM 预处理 token 独立记录，不能当作免费成本收益。价格代理标签不等于官方结算结果。</p>'
    body += '<p><a href="summary.json">完整汇总及模型用量</a> · <a href="inputs/cohort.json">固定候选与抽样记录</a></p>'
    body += '<details><summary>LLM 预处理用量与失败数</summary><pre>' + html.escape(json.dumps(summary['llm_preprocessing'], ensure_ascii=False, indent=2)) + '</pre></details>'
    body += '<table><thead><tr><th>题目</th><th>方案</th><th>Yes / No</th><th>模拟消耗</th><th>有向证据</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
    (output / 'index.html').write_text(page('事件预测 · DeepSeek 自动语义试验', body), encoding='utf-8')
