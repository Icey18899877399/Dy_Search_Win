"""Self-contained, escaped offline report. No network, CDN, telemetry or remote scripts."""
import html
import json
from pathlib import Path


def render_report(result, path):
    payload=json.dumps(result,ensure_ascii=False,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    title=html.escape(result['task']['question'])
    markup='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>动态检索窗口 · 运行报告</title>
<style>
:root{color-scheme:light;--ink:#172b35;--muted:#627681;--green:#087f70;--line:#dce5e7}*{box-sizing:border-box}body{margin:0;background:#f5f7f6;color:var(--ink);font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1320px;margin:auto;padding:36px 32px}header{border-bottom:1px solid var(--line);padding-bottom:28px}.eyebrow{font:12px monospace;letter-spacing:2px;color:var(--green)}h1{font-size:29px;line-height:1.35;max-width:1050px;margin:12px 0}h2{font-size:17px;margin:0 0 12px}.muted{color:var(--muted);font-size:13px}.tags{display:flex;gap:8px;flex-wrap:wrap}.tag{background:#e4eee9;border-radius:5px;padding:3px 9px;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}.card{background:white;border:1px solid var(--line);border-radius:10px;padding:20px;min-width:0}.big{font-size:32px;font-weight:600;letter-spacing:-1px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:18px}svg{width:100%;height:auto;overflow:visible}.controls{margin:24px 0;display:flex;align-items:center;gap:18px}input[type=range]{flex:1;accent-color:var(--green)}.detail{background:#e8f2ed;padding:18px 22px;border-radius:8px;margin-bottom:20px}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border-bottom:1px solid var(--line);text-align:left;padding:9px 8px;vertical-align:top}th{color:var(--muted);font-weight:500}td{overflow-wrap:anywhere}.scroll{overflow:auto;max-height:440px}.note{border-left:3px solid #b08935;background:#faf5e7;padding:14px 18px;margin:20px 0;font-size:13px}button{border:1px solid var(--line);padding:8px 14px;border-radius:6px;background:white;cursor:pointer}details{margin-top:18px}pre{white-space:pre-wrap;word-break:break-all;font-size:12px}footer{margin-top:24px;color:var(--muted);font-size:12px}@media(max-width:760px){main{padding:20px 16px}.metrics,.charts{grid-template-columns:1fr 1fr}.charts{grid-template-columns:1fr}h1{font-size:23px}.big{font-size:24px}}@media print{body{background:white}.scroll{max-height:none}.controls{display:none}.card{break-inside:avoid}}
</style><main><header><div class="eyebrow">PATENT IMPLEMENTATION / OFFLINE REPLAY</div><h1>__TITLE__</h1><div class="tags" id="tags"></div><p class="muted" id="cutoff"></p></header>
<section class="metrics" id="metrics"></section>
<div class="note">预算和轮次时钟为显式模拟；参数为示例配置。关键词抽取未配置支持规则时保持中性，不能据此宣称预测准确性提升。代理标签不等于官方结算真值。</div>
<section class="charts"><div class="card"><h2>事态概率</h2><div id="prob"></div></div><div class="card"><h2>窗口长度 · 天</h2><div id="window"></div></div><div class="card"><h2>累计模拟预算</h2><div id="budget"></div></div><div class="card"><h2>边界外损失率</h2><div id="loss"></div></div></section>
<div class="controls"><b>逐轮复核</b><input aria-label="选择检索轮次" type="range" id="round" min="1" value="1"><span id="round-label"></span></div><div class="detail" id="detail"></div>
<section class="card"><h2>来源状态</h2><div class="scroll"><table><thead><tr><th>来源</th><th>空尽概率</th><th>有效静默 / 天</th><th>新证据数</th><th>参与常规检索</th></tr></thead><tbody id="sources"></tbody></table></div></section>
<section class="card" style="margin-top:18px"><h2>证据与出处</h2><p class="muted">独立当量为终止轮口径；仅标注“最终窗口”的条目参与最终预测。</p><div class="scroll"><table><thead><tr><th>标题 / 来源</th><th>发布 / 归档时间</th><th>关联度 / 当量</th><th>支持度 / 抽取方式</th><th>计量状态</th></tr></thead><tbody id="evidence"></tbody></table></div></section>
<details><summary>配置与运行诊断</summary><pre id="config"></pre></details><footer>离线可复核报告 · 原始数据只读 · 所有图表由本次 result.json 生成</footer></main>
<script type="application/json" id="run-data">__DATA__</script><script>
const D=JSON.parse(document.getElementById('run-data').textContent), R=D.rounds;
const el=id=>document.getElementById(id), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const f=x=>Number(x??0).toFixed(3),pct=x=>(100*x).toFixed(1)+'%';
el('tags').innerHTML=[D.config.mode,D.task.market_id,D.result.termination_reason,D.diagnostics.data_kind||'归档新闻'].map(x=>'<span class="tag">'+esc(x)+'</span>').join('');
el('cutoff').textContent='预测截止：'+D.task.cutoff+' ｜ 时间范围在任务内固定截止，轮次只调整早端边界';
el('metrics').innerHTML=[[D.task.outcomes[0]+' 概率',pct(D.result.probabilities[0])],['检索轮数',D.result.rounds],['模拟预算消耗',f(D.result.spent)],['最终证据 / 有方向支持',D.result.evidence_count+' / '+D.result.supporting_evidence_count]].map(([a,b])=>'<div class="card"><div class="muted">'+esc(a)+'</div><div class="big">'+esc(b)+'</div></div>').join('');
function chart(id,series,colors,labels,maxValue){let w=520,h=165,p=35,values=series.flat(),max=maxValue??Math.max(...values,1),min=0;let svg='<svg viewBox="0 0 '+w+' '+(h+35)+'" role="img" aria-label="'+esc(labels.join('、'))+'">';for(let i=0;i<4;i++){let y=p+(h-p)*i/3;svg+='<line x1="'+p+'" y1="'+y+'" x2="'+(w-12)+'" y2="'+y+'" stroke="#e4ebeb"/><text x="0" y="'+(y+4)+'" fill="#627681" font-size="10">'+(max*(1-i/3)).toFixed(1)+'</text>';}series.forEach((s,j)=>{let pts=s.map((v,i)=>(p+(w-p-12)*i/Math.max(1,s.length-1))+','+(h-(h-p)*v/max)).join(' ');svg+='<polyline points="'+pts+'" fill="none" stroke="'+colors[j]+'" stroke-width="2.5"/>';if(s.length===1)svg+='<circle cx="'+p+'" cy="'+(h-(h-p)*s[0]/max)+'" r="3" fill="'+colors[j]+'"/>';svg+='<text x="'+(p+j*145)+'" y="'+(h+28)+'" font-size="11" fill="'+colors[j]+'">'+esc(labels[j])+'</text>';});svg+='</svg>';el(id).innerHTML=svg;}
chart('prob',D.task.outcomes.map((_,j)=>R.map(r=>r.probabilities[j])),['#087f70','#ba7b33'],D.task.outcomes,1);
chart('window',[R.map(r=>r.window_days)],['#2679a0'],['窗口长度']);
chart('budget',[R.map(r=>D.config.total_budget-r.remaining)],['#7c64a5'],['累计消耗'],D.config.total_budget);
chart('loss',[R.map(r=>r.loss_ratio)],['#ba7b33'],['损失率'],1);
function show(){let r=R[+el('round').value-1];if(!r){el('detail').textContent='没有可执行轮次。';return;}el('round-label').textContent=r.round+' / '+R.length;el('detail').textContent='第 '+r.round+' 轮：'+r.state_before+' → '+r.state+' ｜ 动作 '+r.action+' ｜ 当量 '+f(r.volume)+'，增量 '+f(r.delta)+' ｜ 回收 '+r.recovered_ids.length+' 条 ｜ 边界 '+r.boundary_after;el('sources').innerHTML=Object.entries(r.source_states).map(([s,v])=>'<tr><td>'+esc(s)+'</td><td>'+pct(v.phi)+'</td><td>'+f(v.silence)+'</td><td>'+esc(v.new_count)+'</td><td>'+(v.active?'是':'守候监测')+'</td></tr>').join('');}
el('round').max=Math.max(1,R.length);el('round').value=Math.max(1,R.length);el('round').addEventListener('input',show);show();
el('evidence').innerHTML=D.evidence.map(e=>'<tr><td>'+esc(e.title)+'<br><span class="muted">'+esc(e.source_id)+'</span><details><summary>原文片段与要素</summary>'+esc(e.quote)+'<pre>'+esc(JSON.stringify(e.elements,null,2))+'</pre></details></td><td>'+esc(e.published_at)+'<br>'+esc(e.observed_at)+'</td><td>'+f(e.relevance)+' / '+f(e.weight)+'</td><td>'+esc(JSON.stringify(e.support))+'<br>'+esc(e.extraction_method)+'</td><td>'+(e.in_final_window?'最终窗口':'过渡带或已退出')+'</td></tr>').join('');
el('config').textContent=JSON.stringify({config:D.config,diagnostics:D.diagnostics},null,2);
</script></html>'''
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(markup.replace('__TITLE__',title).replace('__DATA__',payload),encoding='utf-8')
