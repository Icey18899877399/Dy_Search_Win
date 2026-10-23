from pathlib import Path
import json,sys,hashlib,html,collections
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.dont_write_bytecode=True
from dynamic_retrieval.quality import binary_metrics
from dynamic_retrieval.evidence import extract
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
state=read(ROOT/'docs/matching-v5-evaluation-status.json')
plan=read(ROOT/'artifacts/independent-v5-bundle-20261022/bundle-plan.json')
assert state['status']=='completed_diagnostics'
# This is a read-only aggregation of frozen experiments, not a new prediction or label fetch.
for name,h in plan['code_sha256'].items():
    if sha(ROOT/name)!=h:
        assert sha(ROOT/'artifacts/code-archive'/(h+'.py'))==h,name
        assert Path(name).name not in ('evidence.py','semantic.py','matching.py','matching_v4.py','matching_v5.py','core.py'), 'Diagnostic extractor changed; use historical version'
all_tasks=[];origins=[];directional=[];failures=[];grade=collections.Counter()
for b in state['batches']:
    base=Path(b['output']);quality=Path(b['quality']);q=read(quality/'report.json')
    for folder in [base,quality]:
        manifest=read(folder/'manifest.json')
        for name,h in manifest['files'].items():assert sha(folder/name)==h,(folder,name)
    origins.append(dict(cutoff=b['cutoff'],events=b['events'],documents=b['documents'],validated=b['validated'],scoreable=b['scoreable'],prediction_manifest_sha256=sha(base/'manifest.json'),quality_manifest_sha256=sha(quality/'manifest.json'),quality_report=str(quality/'index.html'),evaluation_created_at=read(quality/'evaluation-plan.json')['created_at']))
    grade.update(q['evidence_grade_counts'])
    for task in q['tasks']:
        task=dict(task,cutoff=b['cutoff']);all_tasks.append(task)
        mid=task['market_id'];folder=base/'runs'/mid
        run=read(folder/'enhanced/result.json');documents=read(base/'inputs/tasks'/mid/'forecast-documents.json');ann=read(folder/'machine-annotations.json')
        rounds=read(folder/'enhanced/rounds.json');read_ids={i for r in rounds for k in ['retrieved_ids','recovered_ids'] for i in r.get(k,[])}
        final={x['id'] for x in run['evidence'] if x.get('in_final_window')}
        admitted={x['id'] for x in run['evidence']}
        for d in documents:
            if d['id'] not in ann or not any(ann[d['id']]['support']):continue
            e=extract(d,run['task'],ann);t=e.get('matching_trace',{})
            directional.append(dict(market_id=mid,document_id=d['id'],title=d.get('title',''),read=d['id'] in read_ids,passes=e['relevance']>=run['config']['admission'],admitted=d['id'] in admitted,final=d['id'] in final,relation=t.get('relation'),blockers=t.get('blockers',[]),task_kind=t.get('task_parse',{}).get('kind'),time_status=t.get('time_check',{}).get('status')))
        for tr in read(folder/'extraction-trace.json'):
            if tr['status']!='validated':failures.append(dict(market_id=mid,document_id=tr['document_id'],status=tr['status'],error=tr.get('error')))
assert len(all_tasks)==18 and len({t['event_id'] for t in all_tasks})==18
metrics={}
for split in ['all','validation','test']:
    selected=[t for t in all_tasks if split=='all' or t['split']==split]
    eligible=[t for t in selected if t['label']['status']=='official_resolved']
    metrics[split]=dict(selected=len(selected),scored=len(eligible),excluded=len(selected)-len(eligible))
    for mode in ['fixed','basic','enhanced','uniform_baseline']:
        pairs=[(.5 if mode=='uniform_baseline' else t['modes'][mode]['p_yes'],int(t['label']['outcome'].lower()=='yes')) for t in eligible]
        metrics[split][mode]=binary_metrics(pairs)
assert metrics['all']['scored']==17
# Verify aggregation against source reports' sample-weighted means.
for mode in ['fixed','basic','enhanced']:
    weighted=sum(read(Path(b['quality'])/'report.json')['metrics']['all'][mode]['brier']*b['scoreable'] for b in state['batches'])/17
    assert abs(metrics['all'][mode]['brier']-weighted)<1e-12
stats={k:sum(bool(d[k]) for d in directional) for k in ['passes','read','admitted','final']}
blockers=collections.Counter(x for d in directional for x in d['blockers'])
nonuniform={mode:sum(abs(t['modes'][mode]['p_yes']-.5)>1e-12 for t in all_tasks) for mode in ['fixed','basic','enhanced']}
report=dict(status='verified_frozen_aggregation',generated_at=datetime.now(timezone.utc).isoformat(),model='deepseek-flash',events=18,documents=358,validated=356,failed=2,prediction_runs=54,model_requests_in_this_aggregation=0,original_uncached_tokens=sum(b['model_usage']['uncached_total_tokens'] for b in state['batches']),prior_events_excluded=plan['prior_events_excluded'],independent_holdout_claim=False,evidence_grade_counts=dict(grade),metrics=metrics,nonuniform=nonuniform,directional_documents=len(directional),directional_stats=stats,blocker_counts=dict(blockers),directional=directional,extraction_failures=failures,origins=origins,tasks=all_tasks,limitations=['Retrospective event-disjoint experiment; model future-knowledge contamination remains possible.','Only one event moved away from 0.5; all 11 scored test events remain uniform.','Current post-result diagnosis makes these samples development data for future versions.','Source budgets are simulated; preprocessing all selected documents already incurred model usage.','Source publication and archive clocks do not prove exact first public availability.'])
(ROOT/'docs/matching-v5-independent-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
esc=lambda x:html.escape(str(x))
mode_names={'fixed':'固定窗口','basic':'基础动态','enhanced':'增强动态','uniform_baseline':'均匀基线'}
metric_rows=''.join(f'<tr><td>{esc(split)}</td><td>{metrics[split]["scored"]}/{metrics[split]["selected"]}</td>'+''.join(f'<td>{metrics[split][m]["brier"]:.6f}</td>' for m in mode_names)+'</tr>' for split in metrics)
task_rows=''.join('<tr>'+''.join(f'<td>{esc(x)}</td>' for x in [t['market_id'],t['question'],t['split'],t['label']['status'],f"{t['modes']['enhanced']['p_yes']:.6f}",t['modes']['enhanced']['coverage']['directional_documents'],t['modes']['enhanced']['coverage']['admitted_documents'],t['modes']['enhanced']['coverage']['final_supporting_evidence']])+'</tr>' for t in all_tasks)
links=''.join(f'<li><a href="{esc(Path(b["quality_report"]).relative_to(ROOT).as_posix().replace("artifacts/","../artifacts/",1))}">{esc(b["cutoff"][:10])}：{b["events"]} 事件 / {b["documents"]} 文档 / {b["scoreable"]} 可评分</a></li>' for b in origins)
page=f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V5 冻结评价与离线演示交付</title><style>body{{margin:0;background:#f4f6fa;color:#172638;font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1180px;margin:auto;padding:32px 24px}}h1{{font-size:30px}}h2{{margin-top:34px}}.hero,section{{background:white;border:1px solid #dce3ec;border-radius:12px;padding:24px;margin-bottom:20px}}.kpis{{display:flex;gap:16px;flex-wrap:wrap}}.kpis b{{font-size:26px;color:#176b75}}.kpis div{{min-width:140px}}.note{{border-left:4px solid #cc8a25;padding:12px;background:#fff8e9}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #dce3ec;vertical-align:top}}th{{background:#edf3f8}}.scroll{{overflow:auto}}a{{color:#145db0}}code{{background:#edf3f8;padding:2px 5px}}small{{color:#4d6074}}</style><main><div class="hero"><small>专利离线演示 / 冻结评价 / typed_v5</small><h1>链路已跑通，测试集效果尚未改善</h1><div class="kpis"><div><b>18</b><br>新于历史开发的事件</div><div><b>356 / 358</b><br>抽取校验通过</div><div><b>54</b><br>三策略预测</div><div><b>17 / 18</b><br>可评分事件</div></div><p>模型 deepseek-flash；原批次返回用量 {report['original_uncached_tokens']:,} tokens。本报告仅聚合冻结结果，新增模型请求 0。</p><p class="note">总体 Brier 的改善全部来自验证集中的 1 个事件。11 个可评分测试事件仍输出 0.5。不能据此声称普遍预测优势或真实 API 成本节省。</p><a href="http://127.0.0.1:8765/">打开本地工作台</a> · <a href="matching-v5-independent-summary.json">完整数据与来源指纹</a> · <a href="offline-demo-acceptance.md">专利验收与剩余事项</a></div><section><h2>同输入三策略评价</h2><p>Brier 越低越好。直接汇总逐事件概率和官方标签计算；不平均各批 ECE。validation 为验证分区，test 为冻结测试分区，all 为合计。</p><div class="scroll"><table><tr><th>分区</th><th>评分 / 入选</th><th>固定</th><th>基础</th><th>增强</th><th>均匀</th></tr>{metric_rows}</table></div><p>一个事件因 invalid_final_update_time 排除评分，未用价格代理补齐。已保存官方标签证据等级：{esc(dict(grade))}。</p></section><section><h2>证据流诊断</h2><p>增强策略的方向性文档共 {len(directional)} 篇；离线匹配通过 {stats['passes']}，实际读取 {stats['read']}，实际准入 {stats['admitted']}，进入最终窗口 {stats['final']}。这些数字不是正确率。</p><p>多个阻断原因可同时出现在同一文档：{esc(dict(blockers))}。</p><p>方向性来自冻结机器标注，未经人工复核；拒绝可能正确，也可能是任务解析或关系/时间匹配的误拒。后续修改不得为追求概率变化强行放行。</p></section><section><h2>逐事件结果</h2><div class="scroll"><table><tr><th>市场</th><th>问题</th><th>分区</th><th>标签状态</th><th>增强 P(Yes)</th><th>方向文档</th><th>准入文档</th><th>最终方向证据</th></tr>{task_rows}</table></div></section><section><h2>冻结批次与范围</h2><ul>{links}</ul><p>按事件排除 69 个历史事件；保持来源和时间覆盖门槛后，目标 30 个事件实际保留 18 个。正文及 URL 去重不等于现实事实独立。</p><p>批次执行脚本先完成四批预测，再调用官方结算评价。原结果和标注未改写；本次查看后的失败样本归后续版本的开发回归集。历史模型可能含未来知识，不能称为无污染前瞻实验。</p><p><a href="matching-v5-validation.md">V5 修复与验证说明</a> · <a href="implementation-plan.md">开发计划</a></p></section></main></html>"""
(ROOT/'docs/matching-v5-summary.html').write_text(page,encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','events','validated','original_uncached_tokens','directional_documents','directional_stats','nonuniform','blocker_counts']},ensure_ascii=False))
