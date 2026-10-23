// Pure frozen replay request and provenance view helpers.
const configKeys=['mode','initial_window_days','earliest_days','min_window_days','band_days','grid_days','total_budget','round_budget','rounds'];
export function executionDefaults(run){
 const p=run?.provenance||{},g=p.grid_policy||{};
 return {evidence_policy:p.evidence_policy||'',retrieval_policy:p.retrieval_policy||'',execution_policy:p.budget_policy==='patent_budget_v1'?'patent':'legacy',grid_enabled:p.budget_policy&&!p.grid_policy?'disabled':'enabled',grid_cap_fraction:g.cap_fraction??.2,grid_width_fraction:g.width_fraction??.25,source_cost_json:p.source_cost_profile?.profile?JSON.stringify(p.source_cost_profile.profile,null,2):''};
}
export function buildReplayOptions(values,base){
 const config={};
 for(const key of configKeys){const value=values[key]??base[key];config[key]=key==='mode'?value:Number(value);if(key!=='mode'&&!Number.isFinite(config[key]))throw new Error('配置参数必须是有限数值。');}
 if(config.min_window_days>config.initial_window_days||config.initial_window_days>config.earliest_days)throw new Error('窗口需满足：最小窗口 ≤ 初始窗口 ≤ 历史范围。');
 if(values.execution_policy==='legacy')return {config,execution:{}};
 if(values.execution_policy!=='patent')throw new Error('请选择执行规则。');
 let profile=null;const raw=String(values.source_cost_json||'').trim();
 if(raw){try{profile=JSON.parse(raw);}catch{throw new Error('来源成本配置必须是有效 JSON。');}if(!profile||typeof profile!=='object'||Array.isArray(profile))throw new Error('来源成本配置必须是 JSON 对象，不接受服务器文件路径。');}
 let grid=null;
 if(config.mode==='enhanced'&&values.grid_enabled!=='disabled'){
  grid={version:'patent_grid_v1',cap_fraction:Number(values.grid_cap_fraction),width_fraction:Number(values.grid_width_fraction)};
  if(![grid.cap_fraction,grid.width_fraction].every(v=>Number.isFinite(v)&&v>0&&v<=1))throw new Error('网格预算比例与宽度比例必须在 (0, 1] 内。');
 }
 const evidence=values.evidence_policy||'';
 if(!['','patent_elements_v1','patent_elements_v2','patent_elements_v3','patent_elements_v4'].includes(evidence))throw new Error('未知证据规则。');
 const retrieval=values.retrieval_policy||'';
 if(!['','read_guard_v1','bm25_read_guard_v1'].includes(retrieval))throw new Error('未知候选读取规则。');
 return {config,execution:{budget_policy:'patent_budget_v1',grid_policy:grid,source_cost_profile:profile,...(retrieval?{retrieval_policy:retrieval}:{}),...(evidence?{evidence_policy:evidence}:{})}};
}
export function executionView(run,round){
 const p=run?.provenance||{},d=run?.diagnostics||{},profile=p.source_cost_profile;
 const retrieval=p.retrieval_policy==='bm25_read_guard_v1'?'预算检查 + 窗口内分块 BM25':p.retrieval_policy==='read_guard_v1'?'预算检查 + 原排序':'历史读取';
 const policy=p.budget_policy?`${p.budget_policy} · ${p.grid_policy?.version||'未启用增强网格'}`:'历史策略 / 工件未声明专利预算规则';
 const observation=d.source_cost_profile?.observation_status;
 const cost=profile?(observation==='synthetic_formula_fixture'?'合成来源成本 / 未标定（仅公式验证数据）':observation==='supplied_interface_observations'?'已提供接口观测成本 / 未经验标定（记录出处未经系统核验）':'已提供来源成本配置 / 未经验标定'):p.source_parameters?'已保存来源参数 / 未经验标定':'示例成本 / 未标定（未提供来源测量配置）';
 const plan=round?.decision_trace?.budget_plan??round?.budget_plan;
 const reason=round?.recovery_reason??round?.recovery_decision?.reason??round?.decision_trace?.recovery?.reason??round?.decision_trace?.recovery_reason;
 const budget=plan?`单轮基准 ${plan.regular_baseline??'未记录'} · 有效预算 ${plan.effective??'未记录'} · 预算分配 ${JSON.stringify(plan.reserves||{})}`:'预算计划未记录';
 return {policy:policy+' · '+retrieval+(['patent_elements_v1','patent_elements_v2','patent_elements_v3','patent_elements_v4'].includes(p.evidence_policy)?' · '+p.evidence_policy+' · 要素交集准入＋相容规则支持度':''),cost,round:`${budget} ｜ 回收原因：${reason??'未记录'}`};
}
