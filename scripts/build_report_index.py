"""Build an offline entry page from the delivered demo and real pilot outputs."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts'


def main():
    summary = json.loads((ARTIFACTS / 'pilot/summary.json').read_text(encoding='utf-8'))
    rows = []
    for task in summary['tasks']:
        for mode, label in [('fixed', '固定窗口'), ('basic', '基础方案'), ('enhanced', '增强方案')]:
            folder = ARTIFACTS / 'pilot' / task['market_id'] / mode
            data = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
            result = data['result']
            href = html.escape((folder / 'report.html').relative_to(ARTIFACTS).as_posix(), quote=True)
            rows.append('<tr><td>' + html.escape(task['market_id']) + '<br><small>' + html.escape(task['question']) +
                        '</small></td><td><a href="' + href + '">' + label + '</a></td><td>' +
                        str(data['diagnostics']['visible_documents']) + '</td><td>' + str(result['rounds']) +
                        '</td><td>' + f"{result['spent']:.2f}" + '</td><td>' + str(result['evidence_count']) +
                        ' / ' + str(result['supporting_evidence_count']) + '</td><td>' +
                        html.escape(result['termination_reason']) + '</td></tr>')
    markup = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>事件预测 · 交付报告入口</title>
<style>body{margin:0;background:#f5f7f6;color:#183139;font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1200px;margin:auto;padding:36px 24px}h1{font-size:30px}h2{font-size:19px}a{color:#087f70}
.card{background:white;border:1px solid #dce5e7;border-radius:10px;padding:22px;margin:18px 0}.note{background:#faf5e7;border-left:3px solid #b08935;padding:14px 18px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:12px 10px;border-bottom:1px solid #e1e7e6;vertical-align:top}small{color:#627681}th{white-space:nowrap}.scroll{overflow:auto}</style>
<main><small>专利离线实现 · 本地可复核交付</small><h1>事件预测动态检索窗口</h1>
<p>从固定截止时刻的新闻归档出发，检查窗口移动、来源状态、当量与预算的逐轮变化。</p>
<section class="card"><h2>Task 7：覆盖诊断与正式评价准备</h2><p><a href="quality-v2-20261022/index.html">打开最新评价报告 →</a></p><p>5 个事件中 1 个取得满足要求的官方结算记录，三方案 Brier 均为 0.25（n=1）；其余明确排除。已冻结事件划分并列出窗口覆盖，本批已用于开发，不是独立测试集。</p></section>
<section class="card"><h2>新版：DeepSeek 自动语义流程</h2><p><a href="deepseek-v2-20260515/index.html">打开模型抽取与三方案回放报告 →</a></p>
<p>5 个不同事件，每个最多 10 篇新闻。自动抽取五要素、支持度和原文引用，结构校验后固定输入回放；机器标注未经过人工审核。API token 单列，预测质量尚未验证。</p></section>
<section class="card"><h2>首轮语义试跑保留记录</h2><p><a href="deepseek-20260515/index.html">查看首轮历史结果</a>：6 条非零支持引用市场赔率变化，复核判定不作为独立事件证据；新版提示词与校验器已加入排除规则。历史结构校验成功不代表符合新版策略。</p></section>
<section class="card"><h2>新版：自动全流程</h2><p><a href="automatic-20260515/index.html">打开真实归档自动流程报告 →</a></p>
<p>自动筛选 5 个不同事件，执行规则抽取、三方案调度、代理评分和报告。无需人工审核；本批规则未命中有向支持，报告明确展示弃权结果。</p></section>
<section class="card"><h2>先看算法运行过程</h2><p><a href="demo/report.html">打开合成人工标注验收报告 →</a></p>
<p>此场景为人工构造，包含方向性支持、边界回收和概率变化，用于复核机制。</p></section>
<section class="card"><h2>真实归档试跑：5 个市场 × 3 种方案</h2>
<p>截止时刻：2026-05-15 23:59:59 UTC。模式间使用相同输入、标注和总预算 200；预算是模拟单位。</p>
<div class="note">本次真实试跑没有审核方向性支持，全部概率为 0.5 / 0.5。样本按市场 ID 顺序选取，包含同事件市场及已过题目期限的市场；仅作链路验收，不是前瞻预测成绩、独立测试集或准确率比较。达到轮数上限不等于来源已空尽。</div>
<div class="scroll"><table><thead><tr><th>市场 / 题目</th><th>运行报告</th><th>可见文章</th><th>轮数</th><th>模拟消耗</th><th>最终证据 / 有向支持</th><th>终止原因</th></tr></thead><tbody>__ROWS__</tbody></table></div></section>
<section class="card"><h2>数据覆盖与下一步</h2><p>414 个 JSON 中 396 个可读；18 个权限失败已记录于 <a href="audit.json">数据审计</a>。约 100 万条文章观察记录不等于独立文章；归档正文按内容去重压缩。</p>
<p>当前可通过模型自动抽取支持度。后续质量实验需核验官方结算真值、冻结参数并按事件划分验证和测试；历史回测还需考虑模型未来知识污染。</p>
<p><a href="../README.md">运行说明</a> · <a href="../docs/patent-map.md">专利对应关系</a> · <a href="../docs/validation.md">验收记录</a> · <a href="pilot/summary.json">试跑原始汇总</a></p></section></main></html>'''
    (ARTIFACTS / 'index.html').write_text(markup.replace('__ROWS__', ''.join(rows)), encoding='utf-8')
    print('artifacts/index.html')


if __name__ == '__main__':
    main()
