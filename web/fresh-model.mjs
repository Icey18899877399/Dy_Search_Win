const allowed=new Set(['initial_window_days','earliest_days','min_window_days','band_days','grid_days','total_budget','round_budget','rounds']);
export const utcInput=value=>value?new Date(value).toISOString().slice(0,19):'';
export function freshPreviewPayload(values){
 const raw=String(values.cutoff||'');if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(raw))throw Error('请输入有效 UTC 截止时间。');
 const parsed=new Date(raw+'Z');if(!Number.isFinite(parsed.getTime())||!parsed.toISOString().startsWith(raw))throw Error('截止时间无效。');
 const max_documents=Number(values.max_documents),count=Number(values.count);
 if(!Number.isInteger(max_documents)||max_documents<12||max_documents>40)throw Error('每事件文档上限须为 12–40 的整数。');
 if(!Number.isInteger(count)||count<1||count>20)throw Error('候选事件数须为 1–20 的整数。');
 const config={};for(const [k,v] of Object.entries(values.config||{})){if(!allowed.has(k))throw Error('不支持的配置项：'+k);if(v==='')continue;const n=Number(v);if(!Number.isFinite(n)||n<=0||(k==='rounds'&&(!Number.isInteger(n)||n>1000)))throw Error('配置必须为有效正数：'+k);config[k]=n;}
 if(config.min_window_days>config.initial_window_days||config.initial_window_days>config.earliest_days)throw Error('窗口需满足：最小窗口 ≤ 初始窗口 ≤ 历史范围。');
 const extraction_mode=values.extraction_mode||'shared';if(!['shared','on_demand'].includes(extraction_mode))throw Error('不支持的抽取模式。');
 return {cutoff:parsed.toISOString(),max_documents,count,config,extraction_mode,...(values.execution===undefined?{}:{execution:values.execution})};
}
export function freshJobPayload(preview,selected,key){const ids=[...new Set(selected.map(String))];const available=new Set((preview?.tasks||[]).map(t=>String(t.market_id)));if(!preview?.preview_id||!ids.length||ids.some(id=>!available.has(id)))throw Error('请从当前预览选择至少一个事件。');if(!key)throw Error('缺少提交标识。');return {preview_id:preview.preview_id,market_ids:ids,idempotency_key:key};}
export function freshJobView(job){return {extraction:job.extraction_mode==='on_demand'?`按需抽取 ${job.completed_documents??0} 次 · 请求上限 ${job.model_request_upper_bound??job.total_documents??'—'}（非完成目标） · 验证通过 ${job.validated_documents??0} 次 · 失败 ${job.failed_documents??0} 次`:job.total_documents===undefined?'文档进度尚未记录':`已抽取 ${job.completed_documents??0} / ${job.total_documents} 篇 · 验证通过 ${job.validated_documents??0} 篇 · 失败 ${job.failed_documents??0} 篇`,runs:`已保存策略运行 ${job.completed_runs??0} 份`,resultIds:[...new Set([...(job.result_ids||[]),job.result_id].filter(Boolean))]};}

export function createPreviewGate(){let generation=0;return {begin:()=>++generation,invalidate:()=>{generation++;},isCurrent:token=>token===generation};}

export function freshExecution(values){
 if(values.execution_preset==='legacy')return {};
 if(values.execution_preset!=='patent')throw Error('请选择执行策略。');
 const cap_fraction=Number(values.cap_fraction),width_fraction=Number(values.width_fraction);
 if(!Number.isFinite(cap_fraction)||cap_fraction<=0||cap_fraction>1||!Number.isFinite(width_fraction)||width_fraction<=0||width_fraction>1)throw Error('分格预算比例和宽度比例须大于 0 且不超过 1。');
 if(!['read_guard_v1','bm25_read_guard_v1'].includes(values.retrieval_policy))throw Error('请选择有效检索策略。');
 if(!['legacy','patent_elements_v1','patent_elements_v2','patent_elements_v3','patent_elements_v4'].includes(values.evidence_policy))throw Error('请选择有效证据策略。');
 const execution={budget_policy:'patent_budget_v1',grid_policy:{version:'patent_grid_v1',cap_fraction,width_fraction},retrieval_policy:values.retrieval_policy};
 if(['patent_elements_v1','patent_elements_v2','patent_elements_v3','patent_elements_v4'].includes(values.evidence_policy))execution.evidence_policy=values.evidence_policy;
 if(String(values.source_cost_profile||'').trim()){
  try{execution.source_cost_profile=JSON.parse(values.source_cost_profile);}catch{throw Error('来源成本需为有效 JSON。');}
  if(!execution.source_cost_profile||Array.isArray(execution.source_cost_profile)||typeof execution.source_cost_profile!=='object')throw Error('来源成本需为 JSON 对象。');
 }
 return execution;
}
