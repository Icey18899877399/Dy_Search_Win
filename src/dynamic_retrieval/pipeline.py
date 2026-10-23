"""Automatic offline experiment: frozen candidates -> rules -> three modes -> report."""
from dataclasses import replace
import hashlib
import html
from pathlib import Path

from .automatic import automatic_rules, describe_automatic_policy
from .cli import save_run, write_json, market_directory
from .engine import run
from .evidence import extract, prepare_task
from .evaluation import summarize_comparison
from .models import Config
from .preparation import prepare_cohort
from .reviewpack import save_cohort, validate_output, page

ROOT=Path(__file__).resolve().parents[2]


def run_pipeline(store,data_root,cutoff,output,count=5,min_documents=5,
                 max_metadata_age_days=7,seed='patent-v1',config=None):
    output=validate_output(output,data_root)
    config=config or Config()
    cohort=prepare_cohort(store,data_root,cutoff,count,min_documents,max_metadata_age_days,seed)
    save_cohort(cohort,output/'inputs')
    summaries=[];table=[]
    for item in cohort['selected']:
        task=dict(item['task']);docs=item['documents'];name=market_directory(task['market_id'])
        try:
            rules=automatic_rules(task);policy=describe_automatic_policy(task)
        except ValueError as exc:
            rules={'target_elements':task['target_elements'],'element_aliases':{},
                   'positive_patterns':[],'negative_patterns':[]}
            policy={'version':'unsupported-abstain-v1','category':'unsupported','reason':str(exc)}
        task.update(rules)
        task['automatic_policy']=policy
        task['semantic_validation']='unvalidated_automatic_rules'
        prepared=prepare_task(task)
        extracted=[extract(doc,prepared) for doc in docs]
        directional=[{key:row.get(key) for key in ('id','title','source_id','source_file',
                       'published_at','observed_at','quote','elements','support','relevance','extraction_method')}
                     for row in extracted if any(row['support'])]
        taskdir=output/'runs'/name
        write_json(taskdir/'automatic-rules.json',rules)
        write_json(taskdir/'automatic-policy.json',policy)
        write_json(taskdir/'automatic-directional-evidence.json',directional)
        results={}
        for mode in ('fixed','basic','enhanced'):
            result=run(task,docs,replace(config,mode=mode))
            result['diagnostics'].update(data_kind='real_archive_automatic_rules_experiment',
                                         human_reviewed=False,automatic_policy=policy)
            save_run(result,taskdir/mode);results[mode]=result
            final=result['result']
            outcome_names=[str(x).casefold() for x in task['outcomes']]
            yes_no=[final['probabilities'][outcome_names.index(label)] for label in ('yes','no')]
            table.append('<tr><td>'+html.escape(task['market_id'])+'<br><small>'+html.escape(task['question'])+
                         '</small></td><td><a href="runs/'+name+'/'+mode+'/report.html">'+mode+'</a></td><td>'+
                         ' / '.join(f'{p:.3f}' for p in yes_no)+'</td><td>'+f"{final['spent']:.2f}"+
                         '</td><td>'+str(final['evidence_count'])+' / '+str(final['supporting_evidence_count'])+
                         '</td><td>'+html.escape(final['termination_reason'])+'</td></tr>')
        # Labels enter only after prediction; they never choose candidates or rules.
        comparison=summarize_comparison(results,store.labels(task['market_id']))
        write_json(taskdir/'comparison.json',comparison)
        summaries.append(dict(market_id=task['market_id'],event_id=task['event_id'],question=task['question'],
                              cutoff=task['cutoff'],visible_documents=len(docs),
                              automatic_directional_documents=len(directional),human_reviewed=False,
                              eligibility=item['eligibility'],policy=policy,comparison=comparison))
    complete=len(summaries)==count
    summary=dict(status='completed_automatic_rules_experiment' if complete else 'incomplete_candidate_count',
                 requested_tasks=count,completed_tasks=len(summaries),completed_runs=3*len(summaries),
                 human_reviewed=False,semantic_model='deterministic_event_rules',
                 official_outcomes_verified=False,tasks=summaries,
                 limitations=['Automatic directional signals are unvalidated features, not verified outcomes.',
                              'Metadata gates do not prove semantic deadline validity.',
                              'Costs are simulated; proxy labels are not official settlement truth.'])
    write_json(output/'summary.json',summary)
    note='<div class="note">全流程自动运行，无人工审核。支持度来自确定性事件规则，属于未经语义验证的方向特征；不代表新闻已证明未来结果。未匹配或有歧义时弃权。成本为模拟单位，代理标签不等于官方结算。</div>'
    note+='<p>流程：截止时元数据筛选 → 不同事件候选 → 版本正文 → 自动五要素与支持规则 → 三方案调度 → 对比与报告。</p>'
    note+='<p>完成 '+str(len(summaries))+' / '+str(count)+' 个事件，'+str(3*len(summaries))+' 次运行。<a href="summary.json">完整汇总</a> · <a href="inputs/cohort.json">候选筛选与指纹</a></p>'
    note+='<section class="card"><h2>自动抽取覆盖</h2><ul>'
    for item in summaries:
        name=market_directory(item['market_id'])
        note+='<li>'+html.escape(item['market_id'])+'：'+str(item['visible_documents'])+' 篇可见正文，'+str(item['automatic_directional_documents'])+' 篇命中方向规则；<a href="runs/'+name+'/automatic-directional-evidence.json">命中原文与支持度</a></li>'
    note+='</ul><p>规则未覆盖、检索未命中有向证据或证据被窗口排除，都可能导致最终概率为 0.5 / 0.5；系统不会为制造变化而填充支持度。</p></section>'
    note+='<div class="card" style="overflow:auto"><table><thead><tr><th>市场 / 题目</th><th>方案报告</th><th>Yes / No 概率</th><th>模拟消耗</th><th>最终证据 / 有向</th><th>终止原因</th></tr></thead><tbody>'+''.join(table)+'</tbody></table></div>'
    (output/'index.html').write_text(page('事件预测 · 自动全流程实验',note),encoding='utf-8')
    files={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(output.rglob('*')) if p.is_file()}
    code={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted((ROOT/'src').rglob('*.py'))}
    for name in ('run_pipeline.py','prepare_experiment.py'):
        if (ROOT/name).is_file():code[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    write_json(output/'manifest.json',dict(artifact_type='automatic_pipeline',format_version=1,
                                         files=files,code_sha256=code,status=summary['status']))
    return summary
