"""Inspect frozen semantic experiments; collect labels only after freezing evaluation."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import html
import json

from .cli import write_json, market_directory
from .official import collect, GAMMA, RESOLUTIONS, EVENTS, CLOB
from .quality import event_split, coverage_diagnostic, validate_resolution, binary_metrics, yes_probability, validate_final_winner
from .reviewpack import page, validate_output

ROOT=Path(__file__).resolve().parents[2]
RAW=Path(r'D:\agents-main\agents\polymarket\data')
MODES=('fixed','basic','enhanced')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source(source):
    manifest=read(source/'manifest.json')
    if manifest.get('artifact_type')!='semantic_pipeline':
        raise ValueError('Require frozen semantic experiment')
    for name, expected in manifest['files'].items():
        p=(source/name).resolve()
        if not p.is_relative_to(source) or not p.is_file() or sha(p)!=expected:
            raise ValueError('Frozen experiment changed')
    return manifest


def build_quality_report(experiment, output, fetch=False, collector=None, seed='patent-quality-v1', allow_final_winner=False):
    source=Path(experiment).resolve()
    output=Path(output).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Evaluation and source directories must be separate')
    manifest=verify_source(source)
    source_manifest_sha=sha(source/'manifest.json')
    output=validate_output(output,RAW)
    summary=read(source/'summary.json')
    if (summary['status'] not in ('completed_semantic_experiment','partial_model_failures')
        or summary['completed_tasks']!=summary['selected_tasks']
        or summary['completed_runs']!=3*summary['selected_tasks']
        or summary['selected_tasks']<1):
        raise ValueError('Require frozen predictions for all selected tasks')
    frozen=[]
    for item in summary['tasks']:
        name=market_directory(item['market_id'])
        inputs=source/'inputs/tasks'/name
        task=read(inputs/'task.json')
        docs=read(inputs/'forecast-documents.json')
        annotations=read(source/'runs'/name/'machine-annotations.json')
        results={mode:read(source/'runs'/name/mode/'result.json') for mode in MODES}
        if len({(r['provenance']['input_sha256'],r['provenance']['annotation_sha256']) for r in results.values()})!=1:
            raise ValueError('Modes do not share frozen inputs')
        if any(r['diagnostics']['label_access'] is not False for r in results.values()):
            raise ValueError('Prediction accessed labels')
        frozen.append((task,docs,annotations,results))
    pre_model_path=source/'inputs/pre-model-plan.json'
    pre_model=read(pre_model_path) if pre_model_path.is_file() else None
    split=pre_model['split'] if pre_model else event_split([x[0] for x in frozen],seed)
    if set(split['assignments']) != {x[0]['market_id'] for x in frozen}:
        raise ValueError('Pre-model split task mismatch')
    if pre_model and set(pre_model['excluded_events']) & {x[0]['event_id'] for x in frozen}:
        raise ValueError('Prior event leaked into new cohort')
    plan=dict(created_at=datetime.now(timezone.utc).isoformat(),
              source_experiment=str(source),source_manifest_sha256=source_manifest_sha,
              split=split,config_by_market={t['market_id']:{m:r['config'] for m,r in runs.items()} for t,d,a,runs in frozen},
              prediction_files={n:h for n,h in manifest['files'].items() if n.endswith('/result.json')},
              semantic_preprocessing=summary['llm_preprocessing'],
              source_extraction_status=summary['status'],
              failed_semantic_documents=summary['llm_preprocessing']['failed_documents'],
              label_protocol='official_terminal_winner_v1_or_payout' if allow_final_winner else 'official_api_resolved_binary_payout_after_cutoff',
              independent_holdout_claim=False,parameter_optimization=False,
              pre_model_split_used=pre_model is not None,
              event_disjoint_from_prior_runs=pre_model is not None,
              pre_model_plan_sha256=sha(pre_model_path) if pre_model else None)
    # Persist the fixed cohort, parameter snapshots and predictions BEFORE fetching labels.
    write_json(output/'evaluation-plan.json',plan)
    rows=[]
    collector=collector or (lambda task:collect(task,allow_final_winner=allow_final_winner))
    for task,docs,annotations,results in frozen:
        if fetch:
            snapshot=collector(task)
            try:
                gamma=snapshot['gamma'];resolution=snapshot['resolution']
                expected_urls=[GAMMA+str(task['market_id']),RESOLUTIONS+gamma['conditionId']]
                if snapshot.get('event') is not None:expected_urls.append(EVENTS+str(task['event_id']))
                if allow_final_winner and snapshot.get('clob') is not None:expected_urls.append(CLOB+gamma['conditionId'])
                if snapshot['urls']!=expected_urls:raise ValueError('Source URL mismatch')
                label=validate_resolution(task,gamma,resolution,snapshot['fetched_at'],snapshot.get('event'))
                if allow_final_winner and snapshot.get('clob') is not None:
                    label=validate_final_winner(task,gamma,resolution,snapshot['clob'],snapshot['fetched_at'],snapshot.get('event'))
            except (KeyError,TypeError,ValueError):
                label=dict(status='fetch_failed',outcome=None,
                           error_type=snapshot.get('label',{}).get('error_type','InvalidSnapshot'))
        else:
            snapshot=dict(fetch_requested=False)
            label=dict(status='not_fetched',outcome=None)
        name=market_directory(task['market_id'])
        write_json(output/'official'/f'{name}.json',dict(snapshot=snapshot,validated_label=label))
        modes={}
        for mode,result in results.items():
            coverage=coverage_diagnostic(task,docs,annotations,result['config'])
            coverage.update(body_reads=result['diagnostics']['body_reads'],
                            admitted_documents=result['diagnostics']['admitted_documents'],
                            final_supporting_evidence=result['result']['supporting_evidence_count'])
            modes[mode]=dict(p_yes=yes_probability(result),simulated_spent=result['result']['spent'],
                             coverage=coverage)
        rows.append(dict(market_id=task['market_id'],event_id=task['event_id'],question=task['question'],
                         split=split['assignments'][task['market_id']],label=label,modes=modes))
        print(f"Quality {len(rows)}/{len(frozen)}: {task['market_id']} {label['status']}",flush=True)
    # A concurrently edited source cannot quietly be scored against different predictions.
    verify_source(source)
    if sha(source/'manifest.json')!=source_manifest_sha:raise ValueError('Source manifest changed')
    metrics={}
    for partition in ('all','validation','test'):
        group=[r for r in rows if partition=='all' or r['split']==partition]
        verified=[r for r in group if r['label']['status']=='official_resolved']
        metrics[partition]={mode:binary_metrics([(r['modes'][mode]['p_yes'],int(r['label']['outcome']=='Yes')) for r in verified]) for mode in MODES}
        metrics[partition]['uniform_baseline']=binary_metrics([(.5,int(r['label']['outcome']=='Yes')) for r in verified])
        metrics[partition]['eligible_tasks']=len(group)
        metrics[partition]['excluded_tasks']=len(group)-len(verified)
    resolved=sum(r['label']['status']=='official_resolved' for r in rows)
    failed=sum(r['label']['status']=='fetch_failed' for r in rows)
    report=dict(status='partial_official_fetch' if failed else 'completed_diagnostics',
                quality_status='no_verified_outcomes' if not resolved else 'retrospective_small_sample',
                tasks=rows,requested_tasks=len(rows),official_resolved_tasks=resolved,
                source_extraction_status=summary['status'],
                failed_semantic_documents=summary['llm_preprocessing']['failed_documents'],
                failed_fetches=failed,metrics=metrics,independent_holdout_claim=False,
                budget_units='simulation',llm_new_requests=0,label_protocol=plan['label_protocol'],
                evidence_grade_counts={grade:sum(r['label'].get('verification')==grade for r in rows) for grade in sorted({r['label'].get('verification') for r in rows if r['label'].get('verification')})},
                pre_model_split_used=pre_model is not None,
                event_disjoint_from_prior_runs=pre_model is not None,
                limitations=[('New events are disjoint from prior saved runs, but historical-model contamination remains possible.' if pre_model else 'Already-inspected pilot is not a new independent test set.'),
                             'Official API payout evidence is not an independent blockchain audit.',
                             'No parameter tuning or forced nonzero evidence is performed.',
                             'Historical LLM knowledge and semantic interpretation remain unverified.',
                             'Missing official outcomes never use price proxies.'])
    write_json(output/'report.json',report)
    table=[]
    for row in rows:
        c=row['modes']['enhanced']['coverage']
        table.append('<tr><td>'+html.escape(row['question'])+'</td><td>'+row['split']+'</td><td>'+
            html.escape(row['label']['status'])+'</td><td>'+str(c['initial_window'])+' / '+
            str(c['initial_transition_band'])+' / '+str(c['older_than_initial_reach'])+'</td><td>'+
            str(c['directional_documents'])+' / '+str(c['final_supporting_evidence'])+'</td></tr>')
    body='<p>完成覆盖诊断与评价配置冻结。官方可评分 '+str(resolved)+'/'+str(len(rows))+'；获取失败 '+str(failed)+'。没有真值的指标为 null。</p>'
    body+='<div class="note">'+('本队列排除既有运行事件，划分已在模型调用前冻结；仍为历史回测，不能排除模型未来知识。' if pre_model else '这些事件已在开发中查看过，本次划分仅用于开发评价，不是新独立测试集。')+'检索预算为模拟单位；本次评价没有新增模型请求。</div>'
    body+='<p>语义来源状态：'+html.escape(summary['status'])+'；失败文档 '+str(summary['llm_preprocessing']['failed_documents'])+' 篇，均已排除。各方案使用相同的有效子集。</p>'
    if allow_final_winner:
        body+='<p>本次启用补充协议：官方 CLOB 明确 winner + Data API resolved + Gamma 身份/终局交叉核验。属于终局元数据验证，不等同于链上赔付审计；不读取价格作为标签。</p>'
    body+='<table><tr><th>任务</th><th>集合</th><th>结算核验</th><th>初始窗 / 过渡带 / 更早</th><th>抽取有向 / 最终有向</th></tr>'+''.join(table)+'</table>'
    body+='<p><a href="evaluation-plan.json">冻结评价配置</a> · <a href="report.json">完整诊断、分母及指标</a></p>'
    body+='<p>更早的新闻可能被后续扩窗发现，初始不可达不等于永久不可达。覆盖诊断与零支持分别列出，不据此修改原预测。</p>'
    (output/'index.html').write_text(page('Task 7 · 正式评价准备与覆盖诊断',body),encoding='utf-8')
    files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
    code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}
    code['run_quality.py']=sha(ROOT/'run_quality.py')
    write_json(output/'manifest.json',dict(artifact_type='quality_evaluation',files=files,code_sha256=code,
               source_experiment=str(source),source_manifest_sha256=source_manifest_sha))
    return report
