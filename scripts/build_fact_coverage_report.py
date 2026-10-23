from pathlib import Path
import json,html,re
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
a=read(R/'artifacts/fact-coverage-20261023/summary.json');w=read(R/'artifacts/fact-windows-20261023/summary.json');cards=read(R/'artifacts/fact-windows-20261023/fact-cards.json')
n=re.search(r'Ran (\d+) tests',(R/'docs/fact-coverage-python-tests.log').read_text(encoding='utf-8-sig'))[1]
names={'1171663':'俄乌停火','1423716':'月度发帖计数','2354063':'议会解散'}
rows=[]
for r,c in zip(a['records'],w['records']):rows.append([names[r['market_id']],r['documents'],r['selected_passages'],r['passages_after_default_head'],c['prepared'],r['v2_directional_candidates']])
table='| 任务 | 截止可见正文 | 候选段落 | 起点在原12k之外 | 预备窗口 | v2非零支持候选 |\n|---|---:|---:|---:|---:|---:|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in rows)
lead='已扩展检查到三个既有事件的527篇截止前可见正文，找到可追溯的事件进展报道和抽取入口缺口。决定性事实及任务条件尚未全部闭合，未进入标定或独立评价。'
md=f'''# 截止前事实覆盖与抽取窗口（2026-10-23）

{lead}

## 实际完成

- 核对28个原始来源文件哈希、527篇正文哈希与发布时间/正文观测时间；截止不变。之前60篇均包含在内，新增检查467篇同事件正文，全部计为开发暴露。
- 全文检索得到585个词法候选段落，262篇至少一个候选；不是585个独立有效事实。保存原始连续片段、位置、URL、正文哈希、来源文件和同一URL/正文版本的首次观测时间。
- 发现1条正文只有Wayback链接、1个154万字符的聚合页。新抽取窗口在模型请求之前拦截这两种来源异常；这是源文本预检，不替换专利交集准入公式。
- 新增显式 `evidence_context_policy="fact_window_v1"`：在全文定位候选，再取最长12000字符的单个连续原文窗口；共享抽取和按需抽取都保存起止位置与完整原文哈希，复验片段/任务绑定。旧前缀策略保持默认，不改提示词与历史标注。
- 保存525份可用窗口，未发送到模型；另有2份明确排除原因。窗口准备完成不代表模型完成抽取。

## 同截止检查

{table}

v2非零支持为0仍是现有有限规则的输出，不能据此断言原文客观没有可用证据。候选数量来自有限关键词筛选，每篇最多8段，并非穷尽语义审核。

## 查明的事实与缺口

1. **俄乌停火：有值得补抽取的真实报道。** Reuters转载与Le Monde正文包含双方领导人表态、32小时复活节停火、起止日期及全方向停止军事行动。信息分散在多个句段，v2单断言规则未完整组合。短暂本身不是任务明示排除条件，不能自动据此判无效；仍需明确正式共同协议与人道暂停排除条件的对应。当前没有把这些报道硬写成Yes。
2. **议会：程序事实明确，最终状态未闭合。** 有110票初步表决、仍需委员会和后续投票的正文；不能把approved a bill、vote to dissolve或标题中的dissolve当成最终解散。另一个强标题记录实际没有正文。
3. **发帖计数：数据缺口仍存在。** 本批189篇未检出XTracker/Post Counter对应月份的实际总数；数值命中包括其他主体、其他年份、预测市场区间。统计源时区也未明确。关键词未检出不等于断言原始数据任何位置都不存在，应补同期计数器历史快照或逐帖明细。

## 新窗口收益与限制

原前缀完整覆盖568/585个候选段落，新窗口覆盖570/585；新增覆盖12个、丢失原覆盖10个，净增2。15段的起点在原12k之外，另有候选跨越边界。这里比较的是词法候选片段覆盖，**不是准确率、事实有效率或预测收益**。因此只显式启用，不自动推广为默认，也不增加付费调用。

## 可复跑与接口

```powershell
# 在项目D盘目录运行，输出目录必须是新的。
python -B scripts/audit_fact_coverage.py --output artifacts/fact-coverage-new
python -B scripts/prepare_fact_windows.py --output artifacts/fact-windows-new
```

`prepare_fact_windows.py`使用已冻结的fact-coverage-20261023作为对照来源。任务输入增加上述evidence_context_policy后，`build_evidence_messages`、共享抽取`_extract_one`与按需`ModelAnnotationProvider`均采用新窗口；CLI/前端未新增选项或默认切换。供开发调用的任务样例在`artifacts/fact-windows-20261023/inputs/<market>/task.json`。

## 验收与后续

- {n}项Python测试通过，包括未来正文/任务元数据拒绝、正文假成功、尾部事实选择、片段篡改拒绝、旧前缀不变、共享/按需绑定和机器标注reviewed:false。9份上一批完整预测输出保持一致。
- 新模型请求0、结算标签访问0；预测概率、事实归并、损失、预算与回收公式未改，参数未标定。
- 冻结索引本身有18个源文件读取失败；本轮使用最新可见正文版本，未穷尽较早被覆盖的正文版本，也未遍历其他事件挂接的同主题新闻。这些限制禁止“全数据无事实”的结论。
- 下一步先围绕已找到的跨句停火事实建立**多原文片段—同一事件关系—适用条件**的可追溯校验，补议会最终状态/计数器历史快照；明确哪些属于规则漏提、哪些属于缺数据。取得足够可靠且不重复的事实后，再采集真实成本和检出观测、做到达回放；冻结后才开展未使用事件独立评价。

[可视化案例与原文](fact-coverage-summary.html) · [覆盖汇总](../artifacts/fact-coverage-20261023/summary.json) · [窗口比较](../artifacts/fact-windows-20261023/summary.json) · [9个案例](../artifacts/fact-windows-20261023/fact-cards.json)
'''
(R/'docs/fact-coverage-delivery.md').write_text(md,encoding='utf-8')
trs=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)
sections=[]
for i,c in enumerate(cards,1):
 snippets=''.join('<blockquote>'+html.escape(s['text'])+'</blockquote><small>原文字符 '+str(s['start'])+'–'+str(s['end'])+'</small>' for s in c['snippets'])
 sections.append(f'<details><summary>{i}. {html.escape(c["title"])}</summary><p>{html.escape(c["assessment"])}</p><p><a href="{html.escape(c["canonical_url"],quote=True)}">{html.escape(c["source_title"])}</a></p><small>发布 {c["published_at"]} · 当前版本观测 {c["observed_at"]}<br>同URL/正文首次观测 {c["first_observed_at"]} · 截止 {c["cutoff"]}</small>{snippets}<p><small>原始文件：{html.escape(c["source_file"])}<br>正文SHA256：{c["body_sha256"]}<br>机器整理，非人工审核或结算标签。</small></p></details>')
page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>截止前事实覆盖检查</title><style>body{{background:#0f172a;color:#e2e8f0;font:16px/1.8 system-ui;margin:0}}main{{max-width:1120px;margin:auto;padding:36px 24px}}section,details{{background:#1e293b;border:1px solid #475569;border-radius:12px;padding:22px;margin:20px 0}}h1{{color:white}}strong{{color:#fbbf24}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #475569}}a{{color:#7dd3fc}}summary{{cursor:pointer;font-weight:bold}}blockquote{{white-space:pre-wrap;border-left:3px solid #38bdf8;margin:18px 0;padding:8px 18px;background:#172033;overflow-wrap:anywhere}}small{{color:#cbd5e1;overflow-wrap:anywhere}}</style><main><p>开发资料回用 · 截止不变 · 2026-10-23</p><h1>截止前事实与抽取覆盖</h1><section><p>{lead}</p><p><strong>527篇正文 · 28个原始文件核验 · 新模型请求0</strong></p></section><section><h2>本轮找到了什么</h2><p>俄乌：双方表态与全方向暂停报道分散在多句，需进一步核对协议及人道暂停口径。议会：初步表决有明确报道，最终解散条件尚未闭合。计数：未检出目标月份的实际计数器总数。</p><table><tr><th>任务</th><th>正文</th><th>候选段落</th><th>原12k外</th><th>预备窗口</th><th>v2非零支持</th></tr>{trs}</table><p>585个候选段落来自词法筛选，不能当成585个独立有效事实；0支持也不能证明原文没有可用事实。</p></section><section><h2>抽取入口已补，效果仍需验证</h2><p>新增可选连续原文窗口，保存起止位置、原文哈希和任务绑定。排除一条存档链接正文和一个出处不明的超长聚合页。</p><p>同样12000字符：候选完整覆盖568→570。新增12、丢失10、净增2；保持可选，不改变默认或宣称预测提升。</p><p>{n}项Python测试通过 · 9份旧预测完整一致 · 525份窗口仅离线准备，未调用模型</p></section><h2>9个原文案例</h2><p>点击展开。外部链接用于标识出处，历史内容以冻结正文与位置为准。</p>{''.join(sections)}<section><h2>下一步门槛</h2><p>先解决跨句事实关系与任务条件校验，补最终状态或同期计数快照；事实覆盖足够后再做真实观测标定、到达回放和独立评价。</p><p><a href="fact-coverage-delivery.md">完整交付说明</a> · <a href="../artifacts/fact-coverage-20261023/summary.json">覆盖汇总</a> · <a href="../artifacts/fact-windows-20261023/fact-cards.json">原始案例数据</a></p></section></main></html>'''
(R/'docs/fact-coverage-summary.html').write_text(page,encoding='utf-8')
p=R/'README.md';text=p.read_text(encoding='utf-8-sig').replace('**最新交付（2026-10-23）：**','**历史交付（2026-10-23）：**',1);idx=text.index('**历史交付（2026-10-23）：**');text=text[:idx]+f'**最新交付（2026-10-23）：** [截止前事实覆盖与抽取窗口](docs/fact-coverage-delivery.md) · [原文案例报告](docs/fact-coverage-summary.html)。{lead} 新增可选fact_window_v1，共享/按需抽取均保存原文位置与绑定；候选覆盖568→570，仅净增2，不改默认。{n}项Python测试通过，9旧输出一致，新模型请求0。\n\n'+text[idx:];p.write_text(text,encoding='utf-8')
p=R/'docs/progress.md';p.write_text(p.read_text(encoding='utf-8-sig')+f'\n\n## 2026-10-23 — 截止前事实覆盖与抽取窗口\n\n{lead} 28原始文件/527正文核验，585候选片段；发现存档链接正文和超长聚合页。fact_window_v1已接共享/按需但保持显式可选；525窗口未发送，覆盖568→570净增2。{n} Python通过，9旧输出一致，0新模型调用。详见fact-coverage-delivery.md。\n',encoding='utf-8')
print(json.dumps({'report':'docs/fact-coverage-summary.html','cards':len(cards),'python_tests':int(n)},ensure_ascii=False))
