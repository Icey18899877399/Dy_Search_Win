"""Build a source-linked development delivery from frozen experiment results."""
from pathlib import Path
import json,html
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
a=R/'artifacts/cross-sentence-20261023';b=R/'artifacts/cross-sentence-final-20261023';s=read(b/'summary.json');cost=read(a/'summary.json')['cost'];rows=read(b/'documents.json')
md='''# 跨句事实关联与准入/支持分离（2026-10-23）

已完成限定范围的v3实现、7篇开发案例的14次真实抽取及同标注离线对照。改善的是相关事实保留，方向支持仍为0；不宣称预测准确率、独立泛化或费用节省。

## 实际结果

| 抽取上下文 | v2准入 | v3准入 | v3方向性证据 |
|---|---:|---:|---:|
| 旧前12000字符 | 0/7 | 3/7 | 0/7 |
| fact_window_v1连续窗口 | 0/7 | 3/7 | 0/7 |

三篇停火报道保留双方相关事实，关联度为0.5，支持为[0,0]。不是三个独立事实；不能把当量或准入增长解释为预测收益。议会初步表决仍不等于最终解散，计数反例仍不能当作实际月度总数。两种上下文在这7篇上的准入结果相同，不能声称新窗口优于旧前缀。

## 对照专利

- [0044—0047]：五要素规范化后仍按精确交集比例准入，原阈值不变。相关性与方向支持分开。
- [0050—0058]：事实键仍为五要素逐项一致，几何折减和概率公式不变；模型方向不直接进入专利规则。已通过引擎测试证明中性准入增加当量而不产生方向支持。
- 新增patent_elements_v3：从引文绑定原句，最多关联4句、2400字符的相邻明确指代；每个要素和条件保留原文位置。不同地点/主体、指代否认、否定缩写、假设及不同日期均检查。模型抽取场景只读取实际提供的上下文；计数与回退分支同样先检查边界。
- 正向跨句条件使用限定的完整谓词规则；不是通用指代消解或通用语义理解。当前仍缺通用的非终局进展支持规则。日期未知的报道保留缺失，不能据此声称事实归并准确性已验证。
- CLI、后端共享/按需入口和工作台可显式选择v3；前端显示关联句、读取范围和条件见证。旧规则与默认配置保留。

## 调度回放

最终产物含12次增强模式回放：3个事件×2种上下文×2种证据规则，输入/标注逐组相同。停火任务v3累计准入3篇，最终窗口保留1篇；v2为0。停火v3最终边界为2026-04-09 23:59:59 UTC，v2为2026-04-27 23:59:59 UTC，说明中性证据也会改变窗口计量与边界。所有运行最终概率仍为[0.5,0.5]，并以轮数上限结束，不能称为有效收敛或预测改善。费用与来源参数仍是示例值，未开展独立评价。

## 真实调用与保留记录

'''
md+=f"- 模型deepseek-flash；网络请求{cost['network_attempts']}次，失败{cost['failed_network_attempts']}次，本地缓存读取{cost['cache_reads']}次；服务端报告总tokens {cost['actual_usage']['total_tokens']}（输入{cost['actual_usage']['prompt_tokens']}，输出{cost['actual_usage']['completion_tokens']}）。累计网络尝试耗时{cost['network_elapsed_seconds']:.2f}秒；不是端到端实验时长。\n"
md+='''- 机器标注保持reviewed:false；结构通过不等于事实正确。未访问结算标签，没有人民币费用估算或账单核对。
- 首轮cross-sentence-20261023及源码归档保留。审查修复后在cross-sentence-final-20261023复用同一批14份标注，新增网络请求0。
- 已关闭复审反例：跨句否定与may、其他事件条件借用、上下文越界、普通agree-to被误判为停火、否认事实身份丢失。
- 9份上一批完整预测输出保持一致。完整测试及工件核验结果另见本轮验证日志。

## 下一步

先补任务条件和可靠事件时间的原文绑定，明确哪些真实进展可由规则支持某个事态，哪些只计相关中性证据；扩展到多个真实正反例后，再比较固定/基础/增强窗口。同一时刻的冻结归档检索回放与多截止时刻的证据到达实验需分别报告。最后采集检索接口真实成本与检出观测、做参数标定并冻结，再进入未使用事件独立评价。

[逐条案例报告](cross-sentence-summary.html) · [最终对照](../artifacts/cross-sentence-final-20261023/summary.json) · [调用账本](../artifacts/cross-sentence-20261023/api-ledger.jsonl)
'''
(R/'docs/cross-sentence-delivery.md').write_text(md,encoding='utf-8')
esc=lambda x:html.escape(str(x))
body=['<h1>跨句事实关联与准入/支持分离</h1><p>开发案例 · 截止时刻不变 · 14次真实抽取 · 支持方向仍为0</p><p>v2准入0/7 → v3准入3/7；两种上下文结果相同。不是准确率或独立评价结果。</p>']
for row in rows:
 old=row['policies']['patent_elements_v2'];new=row['policies']['patent_elements_v3'];tr=new['patent_evidence_trace']
 body.append('<details><summary>'+esc(row['market_id']+' / '+row['arm']+' / '+row['document_id'][:12])+f" · 准入 {old['admitted']} → {new['admitted']}"+'</summary>')
 for label,val in [('模型原文引文',new['quote']),('规范化要素',new['elements']),('关联原句',tr['normalization'].get('linked_sentences',[])),('读取范围',tr['normalization'].get('context_read_span')),('支持度',new['support']),('保持中性的原因',tr['support']['blockers'])]:
  body.append('<h3>'+esc(label)+'</h3><pre>'+esc(val if isinstance(val,str) else json.dumps(val,ensure_ascii=False,indent=2))+'</pre>')
 body.append('</details>')
body.append('<h2>范围与后续</h2><p>有限英文指代及关系规则；未知日期保留缺失。三篇准入报道不等于三个独立事实。先补条件与事件时间的原文绑定，再做真实标定和独立评价。</p>')
(R/'docs/cross-sentence-summary.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>跨句事实验证</title><style>body{max-width:1100px;margin:40px auto;padding:0 24px;background:#101827;color:#e3ebf5;font:16px/1.7 system-ui}h1,h2{color:#9cdcff}details{background:#192538;border:1px solid #344a67;padding:16px;margin:14px 0;border-radius:8px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui}</style>'+''.join(body)+'</html>',encoding='utf-8')
for name in ('progress.md','patent-map.md'):
 p=R/'docs'/name;text=p.read_text(encoding='utf-8');text+='\n\n## 2026-10-23 — 跨句事实关联与准入/支持分离\n\n显式patent_elements_v3与工作台入口已加入。7篇开发案例14次真实抽取、28130 tokens；同标注v2→v3准入0/7→3/7，方向性0，概率仍0.5。审查修复后复用标注离线复验，9旧输出一致，未标定/未独立评价。详见[cross-sentence-delivery.md](cross-sentence-delivery.md)。\n';p.write_text(text,encoding='utf-8')
print('wrote cross-sentence delivery and case report')
