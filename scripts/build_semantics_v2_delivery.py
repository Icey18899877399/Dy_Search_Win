from pathlib import Path
import json,re,html
R=Path(__file__).resolve().parents[1]
A=R/'artifacts/semantics-v2-final-20261023'
s=json.loads((A/'summary.json').read_text(encoding='utf-8'))
v=json.loads((R/'docs/semantics-v2-artifact-verification.json').read_text(encoding='utf-8-sig'))
log=(R/'docs/semantics-v2-python-tests.log').read_text(encoding='utf-8-sig')
n=re.search(r'Ran (\d+) tests',log)[1]
rows=[]
for r in s['records']:
 d=r['diagnostic'];rows.append([{'1171663':'俄乌停火','1423716':'马斯克月度发帖数','2354063':'以色列议会解散'}[r['market']],r['documents'],d['normalized_documents'],d['before_admitted'],d['after_admitted'],d['after_directional']])
table='| 任务 | 文档 | 有原文规范化要素 | v1准入 | v2准入 | v2方向性 |\n|---|---:|---:|---:|---:|---:|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in rows)
admitted=sum(row[4] for row in rows)
lead=f'三类任务的结构化条件、原文规范化、断言冲突和时间规则已接入前后端。60篇既有开发文档的全量诊断准入为{admitted}/60篇（v1为0/60），但方向性证据仍为0，9次策略运行均为0.5；本轮不宣称预测质量提高。'
md=f'''# 三类任务语义闭环交付（2026-10-23）

{lead}

## 已完成

- 独立版本 `patent_elements_v2` 覆盖双边停火、月度发帖区间和以色列议会解散；其余任务明确回退v1。任务条件保留问题/描述出处、年份、周期和ET截止时区。
- 原文断言与要素见证逐项记录；完成事件、程序阶段、否认、实际日期和计数保持不同精确事实键。修复平台所有者被误作实际发帖者的问题。
- 停火区分达成和生效日期，要求双边、公开、一般停火；月度统计要求闭合周期及可见计数定义；历史届次、未完成程序、无关否定与冲突分别处理。缺证仍为0。
- 共享/按需抽取、CLI、冻结重跑与诊断入口统一，机器标注仍为reviewed:false。前端显示契约、原文见证、时间判断与支持阻断原因；新事件默认选择v2，历史结果继续按保存版本解释。
- 保留专利[0044–47]交集准入、[0050]精确事实归并/几何折减、[0058]独立相容规则；未调整核心概率、预算、网格与整带回收公式或示例参数。

## 同输入开发对照

{table}

上述分母是每事件全部20篇冻结文档的离线诊断，不能与某一次运行实际读取/最终保留的文档混用。准入只是五要素重叠，不表示完整事实或方向证据，部分仍仅是主题相关上下文。

- 停火材料主要为谈判、提案、战争背景或局部/短暂停火，无法闭合任务条件。
- 月度材料缺完整计数；该冻结截止为2026-04-30 23:59:59 UTC，原任务描述未注明月度统计时区。当前规则保守要求截止日期跨过月末，故此批不认定周期闭合；这是明确的工程保守约束，后续应补统计源时区。
- 议会材料主要为程序进展；规范化后只匹配主体的记录得分1/3，低于原准入阈值0.4。未降低阈值来制造改善。
- 有限英文语法仍会漏识别，未覆盖开放式指代与任意措辞；0方向并不证明所有文档客观上都没有有用信息。

## 验证与版本保留

- {n}项Python测试、41项前端测试通过；独立对抗回归覆盖主体、口径、否定、日期、原文位置与精确事实键。
- 24份旧输出逐字段一致；最终批次3事件60篇/9次运行。另保留最初9次诊断运行，因发现平台所有者误绑定而被最终批次替代，不能把两批当独立样本。
- {v['verified_runs']}份保存运行通过内容哈希、代码归档、输入、双时钟、预算及比较一致性检查。
- 无新增模型请求、无标签访问、无人工审核伪装；本轮不属于独立评价或经验参数标定。

## 下一步与验收门槛

1. 先补当前三类任务的**可判定真实事实覆盖**：在截止前可见的原文中找到完整主谓关系、实际时间、统计口径或协议范围，同时保留反例。检索不到就明确记录缺口，不反复扩大同类无关新闻或调低准入阈值。
2. 独立划分新的开发/标定数据，采集来源查询耗时、返回量、配额和检出率，统一成本尺度；自动标定代理与说明书人工样本标定分开标识。
3. 按真实观测时间到达回放，核查新增证据如何进入过渡带、触发损失和整带回收，并对比固定/基础/增强策略。
4. 冻结代码、提示词和参数后，才对未用于上述开发的事件开展独立评价，分别报告预测质量、证据保留和真实调用成本。

## 工件

- [最终实验汇总](../artifacts/semantics-v2-final-20261023/summary.json)
- [冻结执行计划](../artifacts/semantics-v2-final-20261023/execution-plan.json)
- [开发执行记录](semantics-v2-execution-plan.md)
- [历史试跑（已被最终批次替代）](../artifacts/semantics-v2-check-20261023/summary.json)
'''
(R/'docs/semantics-v2-delivery.md').write_text(md,encoding='utf-8')
tr=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)
page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>三类任务语义闭环</title><style>body{{margin:0;background:#0f172a;color:#e2e8f0;font:16px/1.8 system-ui}}main{{max-width:1080px;margin:auto;padding:40px 24px}}h1{{color:#fff}}section{{background:#1e293b;border:1px solid #475569;border-radius:12px;padding:24px;margin:20px 0}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #475569}}a{{color:#7dd3fc}}strong{{color:#fbbf24}}</style><main><p>专利实现 · 2026-10-23 · 开发数据回归</p><h1>三类任务语义闭环</h1><section><p>{lead}</p><p><strong>方向性0/60 · 九次预测均0.5 · 新模型请求0</strong></p></section><section><h2>同一批60篇文档的全量诊断</h2><table><tr><th>任务</th><th>文档</th><th>有规范化要素</th><th>v1准入</th><th>v2准入</th><th>方向性</th></tr>{tr}</table><p>准入仅表示五要素重叠，不能据此认定事实完整或预测有效。三类任务均按冻结截止时间检查。</p></section><section><h2>这次修正了什么</h2><p>任务条件与年份/时区有出处；原文参与者、断言、日期和计数口径可追溯；程序阶段、否认和不同日期不混成同一事实。前端可查看详细解释。</p><p>保持专利准入、精确事实键、概率、预算、网格与整带回收公式；未降低阈值或强制产生方向。</p><p>{n}项Python / 41项前端测试 · 24份旧输出一致 · {v['verified_runs']}份运行完整性核验</p></section><section><h2>接下来</h2><p>先补截止前可见且可判定的真实事实覆盖；再采集成本和覆盖观测，做真实到达回放。冻结后才开始未使用事件的独立评价。</p><p><a href="semantics-v2-delivery.md">完整交付说明</a> · <a href="../artifacts/semantics-v2-final-20261023/summary.json">最终原始汇总</a> · <a href="http://127.0.0.1:8765/">打开工作台</a></p></section></main></html>'''
(R/'docs/semantics-v2-summary.html').write_text(page,encoding='utf-8')
readme=R/'README.md';text=readme.read_text(encoding='utf-8-sig');text=text.replace('**最新交付（2026-10-23）：**','**历史交付（2026-10-23）：**',1)
anchor='**历史交付（2026-10-23）：**'
text=text.replace(anchor,f'**最新交付（2026-10-23）：** [三类任务语义闭环](docs/semantics-v2-delivery.md) · [可视化摘要](docs/semantics-v2-summary.html)。{lead} {n}项Python/41项前端测试通过，24份旧输出一致，{v["verified_runs"]}份运行核验通过。下一步先补可判定真实事实覆盖，再采集标定观测、到达回放及独立评价。本轮新增模型请求0。\n\n'+anchor,1);readme.write_text(text,encoding='utf-8')
p=R/'docs/patent-map.md';text=p.read_text(encoding='utf-8-sig');start=text.index('**最新技术状态');end=text.index('\n\n',start)
text=text[:start]+'**最新技术状态（2026-10-23）：** '+lead+' `patent_evidence_v2.py`对应[0044–47]、[0050]、[0058]语义输入层；有限三类任务规则，其余显式回退v1。实测标定、真实到达回放与独立评价仍未完成。详见[本轮交付](semantics-v2-delivery.md)。'+text[end:];p.write_text(text,encoding='utf-8')
p=R/'docs/progress.md';p.write_text(p.read_text(encoding='utf-8-sig')+f'\n\n## 2026-10-23 — 三类任务语义闭环\n\n{lead} {n} Python/41前端测试通过；24旧输出一致；{v["verified_runs"]}运行完整性通过。保留首轮误绑定诊断，最终批次采用semantics-v2-final-20261023。下一步先补可判定真实事实覆盖，再做真实标定、到达回放与独立评价。详见semantics-v2-delivery.md。\n',encoding='utf-8')
print(json.dumps(dict(admitted=admitted,python_tests=int(n),verified_runs=v['verified_runs']),ensure_ascii=False))


