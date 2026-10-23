"""Label-free diagnosis of the frozen 200-document v4 batch. Never edits predictions."""
import hashlib,json,sys
from pathlib import Path
from collections import Counter
from dataclasses import replace
from html import escape
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.evidence import prepare_task,extract
from dynamic_retrieval.engine import run,day,iso
from dynamic_retrieval.models import Config

SOURCE=ROOT/'artifacts/web-semantic/f450968cafff41d6a70015244263ad51'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def deny_network(event,args):
    if event=='socket.connect':raise RuntimeError('Diagnostic must remain offline')
sys.addaudithook(deny_network)

# Analyst interpretation of frozen excerpts; not a new model annotation or human gold label.
NOTES={
'22bf79cd46f8':('related_context','否定状态/动作客体切分','原文前句指向铀库存回收及销毁，随后明确 Iran has not agreed。目标客体带 to surrender，而标注把这部分放进动作，导致客体不等及动作未识别。可研究为同一事件的反向状态；尚未同意不等于截至年底必不发生。'),
'c7e47ddf93b3':('semantic_risk','相互冲突的报道','标注 rationale 同时承认匿名美方称原则同意与伊朗公开否认，却保留单向 Yes 支持。公开承诺条件亦未确立。应先拆分相互冲突的陈述/弃权，不能把同义词修复直接变成准入。'),
'53e08f383dc4':('semantic_risk','预测及市场押注','quote 使用 are likely；rationale 明确使用 traders added to bets。模型把预测写成 leave rates unchanged，并标 reported。现有关键词/自报状态校验漏掉该表达；应分离已发生通胀事实与未来利率预测。'),
'8979c24efb76':('semantic_risk','海峡指代错误','quote 前文明确讨论 Oman 与 Iran 之间的 Strait of Hormuz，结尾称 Persian Gulf 的出口。标注却补成 Bab el-Mandeb。原文中的 the strait 不能投影为任务海峡。'),
'921cac0c7e2f':('semantic_risk','海峡指代错误','quote 写明 routes bypassing the SoH，key passageway 的上下文是霍尔木兹海峡。模型把该关闭事实当曼德海峡方向性证据，缺少明确桥接依据。'),
'd3d0853cdf60':('related_context','攻击与关闭是不同关系','正文报告胡塞声称在曼德海峡附近攻击船只，原文同时说明 AP 无法独立核实。可作为 reported attack 背景；不能当实际关闭或 PortWatch 七日均值达标。Monday 的确切日期未解析。'),
'89d373e98625':('related_context','通行受阻背景','quote 明确提到 Bab el-Mandeb 无恢复畅通协议，地点相关；目标整句被当主体，导致拒绝。可研究为通行受阻背景，但无 PortWatch 七日均值 <=10 的观测，也不是最终关闭结论。'),
'9de446cc5a51':('related_context','封锁宣告/威胁及重复报道','胡塞宣布针对沙特航运封锁并威胁扼住曼德海峡；事实是宣告与威胁，不是水道已关闭。与另两篇 7 月 30 日报道可能复述同一事态，不能当三个独立事实；日期与事件归并需验证。'),
'f2aa105887a5':('related_context','封锁宣告/威胁及重复报道','原文 declared a blockade 是已报道宣告，could choke off 是潜在后果。两者须分开；不能因出现 could 就抹去宣告事实，也不能把后果记为发生。与同日另外两篇可能同源事态。'),
'c689c37e2cb5':('related_context','封锁宣告/威胁及重复报道','原文只报告宣告/威胁，后文还说 some Saudi oil exports are continuing。不能升级为关闭事实，且与同日两篇需要事实去重；模型主体被概括成 shipping traffic，真实行为方是胡塞。'),
'57c7563120da':('scope_uncertain','旧事件日期与关闭范围','归档发布日期为 8 月 24 日，正文航班取消时间为 3 月 1–2 日，不能用发布日期替代事实日期。closure of Israeli airspace 未拆出 object，且日期范围无法解析。仅该航空公司通知不足以独立确认题目要求的重大普遍关闭；市场有效区间也需明确。'),
'8fe858955d6d':('related_context','复合目标解析/反向状态','任务 US announces end 被拆成主体 US announces、动作 end。原文报告美方维持封锁能力及行动，属于反向状态背景；不直接证明从未宣布终止，也不证明未来 No。应分离宣布、执行状态及终止关系。'),
'1b812febb7ab':('related_context','被动目标与主动行为方','目标是 Trump 被弹劾，原文是 Al Green 提交针对 Trump 的条款。不同语法角色不能直接作同一主体比较；提交是程序进展，非众议院通过，Monday 日期亦需锚定。'),
'fca7cb60f5ee':('related_context','议案身份/背书关系','目标未识别 passes，整句成为主体。原始 quote 是不完整片段，但同一已提供 excerpt 的前文明确有 endorsement；后续需引用完整上下文，映射 Proposition 40 与目标议案，背书不等于通过。'),
'e8c306230981':('related_context','议案资格条件与多时间','原文声明六月二十五日认证进入十一月三日选票，对题目资格条件相关；不能当投票通过。目标整句主体及混合认证/选举日期均未结构化，需分开发生日期与计划日期。')}

def main():
    manifest=read(SOURCE/'manifest.json');source_hash=sha(SOURCE/'manifest.json')
    for name,digest in manifest['files'].items():assert sha(SOURCE/name)==digest,name
    for name in ['matching.py','matching_v4.py','evidence.py','engine.py','core.py','models.py','semantic.py']:
        key='src/dynamic_retrieval/'+name
        assert sha(ROOT/key)==manifest['code_sha256'][key],key
    rows=[];tasks=[];replayed=0;counterfactual=None
    for folder in sorted((SOURCE/'runs').iterdir()):
        market=folder.name;inputs=SOURCE/'inputs/tasks'/market
        task=read(inputs/'task.json');docs=read(inputs/'forecast-documents.json');ann=read(folder/'machine-annotations.json')
        saved={mode:read(folder/mode/'result.json') for mode in ('fixed','basic','enhanced')}
        for mode,result in saved.items():
            replay=run(task,docs,Config(**result['config']),ann)
            for key in ('result','rounds','evidence','provenance'):assert replay[key]==result[key],(market,mode,key)
            replayed+=1
        read_ids={mode:{i for step in r['rounds'] for i in step['retrieved_ids']} for mode,r in saved.items()}
        effective=prepare_task(task)
        directional=[]
        for doc in docs:
            a=ann[doc['id']]
            if not any(a['support']):continue
            e=extract(doc,effective,ann);key=doc['id'][:12];category,cause,note=NOTES[key]
            excerpt=a['excerpt'];pos=excerpt.index(a['quote'])
            per_mode={}
            for mode,result in saved.items():
                read_rounds=[step['round'] for step in result['rounds'] if doc['id'] in step['retrieved_ids']]
                admitted=doc['id'] in {item['id'] for item in result['evidence']}
                passes=e['relevance']>=result['config']['admission']
                per_mode[mode]=dict(body_read=bool(read_rounds),read_rounds=read_rounds,admitted=admitted,passes_matching=passes,
                    rejection_observed=bool(read_rounds) and not passes,diagnostic_only_not_read=not bool(read_rounds))
            row=dict(market_id=market,id=doc['id'],title=doc['title'],canonical_url=doc['canonical_url'],published_at=doc['published_at'],observed_at=doc['observed_at'],source_id=doc['source_id'],
                question=task['question'],target_elements=task['target_elements'],raw_elements=a['elements'],support=a['support'],factual_status=a['factual_status'],time_scope=a['time_scope'],
                quote=a['quote'],rationale=a['rationale'],supplied_excerpt_context=excerpt[max(0,pos-750):pos+len(a['quote'])+450],
                document_sha256=sha(inputs/'forecast-documents.json'),annotation_file_sha256=sha(folder/'machine-annotations.json'),
                relevance=e['relevance'],threshold=saved['enhanced']['config']['admission'],matching_trace=e['matching_trace'],modes=per_mode,
                assessment=dict(category=category,cause=cause,note=note,kind='assistant_analysis_of_frozen_excerpt_not_ground_truth',human_reviewed=False))
            rows.append(row);directional.append(doc['id'])
        enh=saved['enhanced']; cfg=enh['config']
        reach=min(day(x['boundary_before']) for x in enh['rounds'])-cfg['band_days']
        tasks.append(dict(market_id=market,question=task['question'],target_elements=task['target_elements'],matching_warnings=task.get('matching_warnings',[]),
            directional_documents=len(directional),enhanced_reads=sum(i in read_ids['enhanced'] for i in directional),
            minimum_probe_start=iso(reach),last_boundary=enh['rounds'][-1]['boundary_after'],actions=dict(Counter(x['action'] for x in enh['rounds'])),
            remaining_budget=enh['rounds'][-1]['remaining'],round_limit=cfg['rounds'],uncertainty_expansion=cfg['enable_uncertainty_expansion']))
        if market=='2853074':
            wide=run(task,docs,replace(Config(**cfg),initial_window_days=30.),ann)
            wider_reads={i for step in wide['rounds'] for i in step['retrieved_ids']}
            counterfactual=dict(market_id=market,only_change={'initial_window_days':[14.,30.]},model_requests=0,labels_accessed=False,
                original_directional_reads=sum(i in read_ids['enhanced'] for i in directional),counterfactual_directional_reads=sum(i in wider_reads for i in directional),
                original_all_reads=len(read_ids['enhanced']),counterfactual_all_reads=len(wider_reads),admitted=len(wide['evidence']),probabilities=wide['result']['probabilities'],
                inference='Wider reading reaches the three older documents but current matcher still rejects them. This is diagnosis, not a production policy change or quality score.')
            assert counterfactual['counterfactual_directional_reads']==7 and counterfactual['admitted']==0
    assert len(rows)==15 and {r['id'][:12] for r in rows}==set(NOTES)
    counts={mode:{key:sum(row['modes'][mode][key] for row in rows) for key in ['body_read','admitted','passes_matching','rejection_observed','diagnostic_only_not_read']} for mode in ('fixed','basic','enhanced')}
    assert counts['enhanced']['body_read']==12 and counts['enhanced']['admitted']==0
    report=dict(status='completed_label_free_diagnosis',source=str(SOURCE.relative_to(ROOT)),source_manifest_sha256=source_hash,
        source_unchanged=True,algorithm_changed=False,model_requests=0,labels_accessed=False,independent_quality_score=False,
        exact_replayed_runs=replayed,directional_documents=len(rows),counts=counts,
        blockers_nonexclusive=dict(Counter(b for row in rows for b in row['matching_trace']['blockers'])),time_status=dict(Counter(row['matching_trace']['time_check']['status'] for row in rows)),
        assessment_counts=dict(Counter(row['assessment']['category'] for row in rows)),rows=rows,tasks=tasks,coverage_counterfactual=counterfactual,
        limitations=['Assistant interpretations are not human gold labels or independent source verification.','15 machine-directional documents do not mean 15 valid independent facts.','12 actual read rejections plus 3 offline-only matching diagnoses in enhanced mode.','Do not lower admission to force nonzero predictions.','If used for tuning, retain this cohort as development diagnostics and freeze a new cohort for future evaluation.'])
    for name,digest in manifest['files'].items():assert sha(SOURCE/name)==digest,name
    assert sha(SOURCE/'manifest.json')==source_hash
    out=ROOT/'docs/admission-v4-diagnostic.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    cards=[]
    for n,row in enumerate(rows,1):
        a=row['assessment'];m=row['modes']['enhanced'];trace=row['matching_trace']
        cards.append('<details><summary>'+str(n)+'. '+escape(row['title'])+' <span>'+('已读取后拒绝' if m['body_read'] else '未读取 / 离线仍不匹配')+'</span></summary><p><b>任务：</b>'+escape(row['question'])+'</p><p><b>诊断：</b>'+escape(a['cause']+'。'+a['note'])+'</p><p><b>代码阻断：</b>'+escape(', '.join(trace['blockers']))+'；时间判断 '+escape(trace['time_check']['status'])+'</p><div class="pair"><pre>目标五要素\n'+escape(json.dumps(row['target_elements'],ensure_ascii=False,indent=2))+'</pre><pre>原始标注五要素\n'+escape(json.dumps(row['raw_elements'],ensure_ascii=False,indent=2))+'</pre></div><blockquote>'+escape(row['quote'])+'</blockquote><p class="muted">已提供给模型的原文上下文：</p><pre>'+escape(row['supplied_excerpt_context'])+'</pre><p class="muted">文档 '+escape(row['id'])+'；发布日期 '+escape(row['published_at'])+'</p></details>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>15 篇方向性文档准入诊断</title><style>body{font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif;background:#f3f6f3;color:#233c3b;margin:0}main{max-width:1100px;margin:40px auto;padding:0 22px}h1{font-size:32px}.stats,.pair{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.pair{grid-template-columns:1fr 1fr}.stats div{padding:20px;background:#e5efe8;border-radius:9px}.stats b{display:block;font-size:30px}section,details{background:#fff;border:1px solid #dae4dd;padding:20px;border-radius:9px;margin:16px 0}summary{cursor:pointer;font-weight:600}summary span{font-size:12px;color:#926b35}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 Consolas,monospace;background:#f5f7f4;padding:14px;min-width:0}.muted{color:#75847c;font-size:13px;overflow-wrap:anywhere}blockquote{border-left:3px solid #438b72;margin:15px 0;padding:10px 18px;background:#edf5ef}a{color:#247e70}.note{background:#fbf3df;padding:16px}@media(max-width:700px){.stats,.pair{grid-template-columns:1fr}}</style><main><p class="muted">2026-10-22 · 冻结批次离线诊断 · 新增模型调用 0</p><h1>15 篇方向性文档为何未准入</h1><p>精确重放原来的 30 份预测，并逐项检查目标解析、原始标注、读取路径和匹配阻断。算法与原始预测均未修改。</p><div class="stats"><div><b>12 / 15</b>增强策略读到后被拒绝</div><div><b>3 / 15</b>未读到，离线匹配也不通过</div><div><b>0 / 15</b>当前匹配门槛通过</div></div><section><h2>诊断结论</h2><p>任务解析、事件关系映射和模型标注可靠性同时存在缺口。主体/客体字面相等不足以处理主动/被动角色、否定状态、程序进展；但放宽匹配也会放进错误证据。</p><p class="note">4 篇有明确标注风险：2 篇海峡指代错误、1 篇预测及押注依据、1 篇冲突报道；1 篇旧事件日期及关闭范围不清。其余 10 篇为待结构化的关联背景候选，并不代表应全部准入或是真实独立事实。</p><p>3 篇未读取文档均发表于 7 月 30 日。初始窗口 14 天加过渡带 14 天，最早到 7 月 31 日 23:59:59；后续只收缩到 3 天，没有向更早历史扩张。该事件还剩约 178.4 模拟预算，问题并非总预算不足。</p><p>只把该事件初始窗口从 14 改为 30 天进行离线对照：方向性文档读取从 4/7 升至 7/7，准入仍为 0，概率仍为 0.5。扩大读取单独不能解决匹配问题。</p></section><section><h2>下一步修复顺序</h2><ol><li>结构化任务：主体/行为/客体/地点/时间之外，保留关系类型、角色、否定、阈值和资格条件；不再以出现 be 或 end 判断解析成功。</li><li>校验事实指代与支持来源：区分 Hormuz / Bab el-Mandeb、事实/预测、宣告/发生、单方报道/冲突；保留原始标注，单独输出审计与弃权理由。</li><li>将“同一事件相关背景”与“满足结算条件”分开，再修复否定、被动角色、先决步骤与混合日期。</li><li>匹配修正后再评估历史探测策略与事实去重，最后另选冻结新样本评价；不在这批已检查数据上声称独立提升。</li></ol></section><h2>逐篇可追溯记录</h2>'''+''.join(cards)+'''<section><p><a href="admission-v4-diagnostic.json">完整机器诊断数据</a> · <a href="admission-v4-diagnosis.md">诊断说明与修复清单</a> · <a href="http://127.0.0.1:8765/">工作台</a></p><p class="muted">这是对本地冻结原文的分析，不是人工金标、现实真实性核验或新预测评分。保留 reviewed:false；未放宽门槛、修改支持向量或发送新模型请求。</p></section></main></html>'''
    (ROOT/'docs/admission-v4-summary.html').write_text(page,encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','tasks','limitations')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
