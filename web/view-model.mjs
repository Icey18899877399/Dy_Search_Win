export const modeNames={fixed:'固定窗口',basic:'基础动态',enhanced:'增强动态'};
export const directionNames={support:'支持首项',against:'支持次项',neutral:'中性 / 弃权',mixed:'多方向'};
export const number=(v,d=2)=>Number.isFinite(Number(v))&&v!==null&&v!==undefined?Number(v).toFixed(d):'—';
export const percent=v=>v===null||v===undefined?'—':`${number(v*100,1)}%`;
export function direction(e){const s=e.support||[];if(!s.some(x=>x>0))return 'neutral';if(s[0]>0&&!s.slice(1).some(x=>x>0))return 'support';if(!(s[0]>0)&&s[1]>0)return 'against';return 'mixed';}
export function safeUrl(v){try{let u=new URL(v);return ['http:','https:'].includes(u.protocol)?u.href:null;}catch{return null;}}
export function filterRuns(rows,{query='',mode='',kind=''}={}){const q=query.toLowerCase().trim();return rows.filter(r=>(!mode||r.mode===mode)&&(!kind||(r.data_kind||'').includes(kind))&&(!q||[r.question,r.market_id,r.event_id,r.batch,r.group].join(' ').toLowerCase().includes(q)));}
export function roundView(run,index){const rounds=run.rounds||[];const ix=Math.max(0,Math.min(rounds.length-1,index));const r=rounds[ix];if(!r)return {round:null,index:0,evidence:[],sources:{},probability:null,spent:null};const known=new Set(rounds.slice(0,ix+1).flatMap(x=>[...(x.retrieved_ids||[]),...(x.recovered_ids||[]),...(x.window_ids||[])]));const windowIds=new Set(r.window_ids||[]);return {round:r,index:ix,evidence:(run.evidence||[]).filter(e=>known.has(e.id)).map(e=>({...e,in_window:windowIds.has(e.id),historical_weight:r.evidence_weights?.[e.id]??null})),sources:r.source_states||{},probability:r.probabilities?.[0]??null,spent:typeof r.remaining==='number'?run.config.total_budget-r.remaining:null};}
const stable=x=>JSON.stringify(x,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
export function comparisonCheck(runs){if(runs.length<2)return {ok:false,reason:'请至少选择两个运行。'};const a=runs[0];if(runs.some(r=>!r.computation_version)||runs.some(r=>r.computation_version!==a.computation_version))return {ok:false,reason:'计算代码版本缺失或不同，仅可并列浏览。'};if(runs.some(r=>!r.provenance?.input_sha256||!r.provenance?.annotation_sha256))return {ok:false,reason:'缺少输入或标注指纹，无法确认同输入对照。'};if(runs.some(r=>r.provenance.input_sha256!==a.provenance.input_sha256||r.provenance.annotation_sha256!==a.provenance.annotation_sha256))return {ok:false,reason:'输入或标注指纹不同，仅可并列浏览。'};if(runs.some(r=>stable(r.task)!==stable(a.task)))return {ok:false,reason:'任务语义或截止时刻不同，仅可并列浏览。'};const config=r=>Object.fromEntries(Object.entries(r.config||{}).filter(([k])=>k!=='mode'));if(runs.some(r=>stable(config(r))!==stable(config(a))))return {ok:false,reason:'除策略外的配置不同，仅可并列浏览。'};const policies=r=>Object.fromEntries(['evidence_policy','comparison_policy','budget_policy','retrieval_policy','fact_policy','runtime_policy','recovery_policy','source_parameters','source_cost_profile'].map(k=>[k,r.provenance?.[k]??null]));if(runs.some(r=>stable(policies(r))!==stable(policies(a))))return {ok:false,reason:'证据或执行规则不同，仅可并列浏览。'};const enhanced=runs.filter(r=>r.config?.mode==='enhanced');if(enhanced.some(r=>stable(r.provenance?.grid_policy??null)!==stable(enhanced[0].provenance?.grid_policy??null)))return {ok:false,reason:'增强网格配置不同，仅可并列浏览。'};return {ok:true,reason:'输入、标注、任务、执行规则及除策略外的配置一致。'};}

export function chooseDefaultRun(rows){const candidates=rows.filter(r=>r.mode==='enhanced'&&!String(r.data_kind||'').includes('synthetic'));const pool=candidates.length?candidates:rows;const rank=r=>/web[-_/]?runs?/i.test(String(r.batch||r.group||''))?10000:Number(String(r.batch||r.group||'').match(/semantic-v(\d+)/)?.[1]||0);return pool.slice().sort((a,b)=>rank(b)-rank(a)||String(b.batch||b.group||'').localeCompare(String(a.batch||a.group||''),'en',{numeric:true})||String(b.id).localeCompare(String(a.id),'en',{numeric:true}))[0]||null;}

export const effectiveTarget=(run,evidence)=>evidence.matching_trace?.target??run.task?.target_elements??{};
export const admissionStatus=e=>e.admitted===true?'已准入':e.admitted===false?'未准入':'准入未知';
export function rejectionDescription(e){if(e.admitted===null)return '当前诊断未能验证准入状态';if(e.rejection_reason==='relevance_below_admission_threshold')return '关联度低于准入门槛';if(e.rejection_reason)return '诊断记录了拒绝或验证原因，请展开匹配轨迹查看原始代码';return e.admitted===false?'未通过准入门槛':e.admitted===true?'已通过当前准入门槛':'已存工件未记录完整拒绝原因';}

export function pickComparisonRuns(rows,current){const exact=rows.filter(r=>r.market_id===current.market_id&&current.group&&r.group===current.group);const config=r=>Object.fromEntries(Object.entries(r.config||{}).filter(([k])=>k!=='mode'));let candidates=exact;if(new Set(exact.map(r=>r.mode)).size<2){const verified=rows.filter(r=>r.market_id===current.market_id&&current.batch&&r.batch===current.batch&&r.question===current.question&&r.cutoff===current.cutoff&&['input_sha256','annotation_sha256','computation_version'].every(key=>current[key]&&r[key]===current[key])&&current.config&&r.config&&stable(config(r))===stable(config(current)));candidates=verified.length>=2?verified:exact;}return ['fixed','basic','enhanced'].map(mode=>candidates.find(r=>r.id===current.id&&r.mode===mode)||candidates.find(r=>r.mode===mode)).filter(Boolean);}


const relationLabels={
  same_event_opposing_or_related_statement:'同一事件的相反或相关表述',military_progress_not_capture:'军事进展，不能等同已攻占',release_statement_not_authenticity_claim:'文件解封或公开，不代表文件真实性',departure_statement_or_pressure_not_completed_exit:'离职表态或压力，不代表已经离职',capture_statement:'攻占表述',same_action:'同类行为',unresolved:'事件关系尚未明确',
  opposing_state:'相反状态',agreement_statement:'协议或同意表述',termination_statement:'终止或暂停表述',declaration_or_threat:'声明或威胁',reported_attack:'报道的袭击',disruption_context:'通行受扰背景',qualification_step:'选票资格认证步骤',endorsement_context:'背书或支持背景',passage_statement:'通过表述',procedural_step:'程序步骤',impeachment_statement:'弹劾表述',closure_statement:'关闭表述',test_statement:'试验表述',leadership_statement:'领导地位表述',rate_decision_statement:'利率决策表述'
};
const blockerLabels={
  location_mismatch:'地点不一致',location_unresolved:'地点未明确',subject_mismatch:'主体不一致',subject_unresolved:'主体未明确',object_mismatch:'客体不一致',object_unresolved:'客体未明确',action_relation_unresolved:'行为关系尚不能确认',event_time_outside_interval:'事件时间超出当前范围',
  unsupported_task:'不支持的任务模板，不准入证据',actor_not_grounded:'原文未明确支持目标主体',forecast_or_market_basis:'依据为预测或市场判断',conflicting_claims:'来源说法存在冲突',place_coreference_conflict:'地点指代存在冲突',target_not_grounded:'来源上下文未明确支持目标',claim_relation_not_grounded:'原文未明确支持目标主张关系',closure_scope_unverified:'关闭范围尚未核实',subject_unresolved_or_mismatch:'主体未明确或不一致',action_unresolved_or_mismatch:'行为未明确或不一致',object_unresolved_or_mismatch:'客体未明确或不一致',location_unresolved_or_mismatch:'地点未明确或不一致',event_time_unknown:'事件时间未明确',event_time_outside:'事件时间超出观察范围'
};
const templateLabels={blockade_announcement:'封锁终止公告',rate_decision:'利率决策',strait_closure:'海峡关闭',uranium_agreement:'伊朗铀库存移交协议',impeachment:'弹劾',wealth_tax:'财富税投票',airspace_closure:'领空关闭',nuclear_test:'核武器试验',leadership:'领导地位',legacy_typed:'沿用 V4 类型化任务',unsupported:'不支持的任务模板'};
const conditionLabels={
  'IMF PortWatch 7-day moving average transit calls <= 10; background disruption is not threshold observation':'IMF PortWatch 通行次数的 7 日移动平均值 ≤ 10；受扰背景不等于已观测到该阈值',
  'one-time tax threshold at least USD 1 billion':'一次性财富税的征税门槛至少为 10 亿美元',
  'qualifying ballot certification':'须取得符合要求的选票资格认证',
  'passage in named California election':'须在指定的加利福尼亚州选举中通过',
  'House approval; filing articles is only a procedural step':'须获众议院批准；提交弹劾条款仅属于程序步骤',
  'authorized official public announcement of a decided termination/suspension; current enforcement is background':'须由获授权的官方公开宣布已决定终止或暂停；当前执行封锁仅属于背景',
  'major general closure by Israel; isolated airline cancellation is insufficient':'须由以色列实施大范围普遍关闭；个别航空公司取消航班不足以成立',
  'public Iranian agreement to surrender; conflicting anonymous reports are not agreement':'须有伊朗公开同意移交；存在冲突的匿名报道不等于达成协议'
};
const label=(labels,value)=>Object.hasOwn(labels,value)?labels[value]:(value||'未记录');
export function patentSupportNotes(trace){
  if(!trace)return [];
  const support=trace.support||{};
  return [
    '支持度规则：'+(support.contract_source||'未记录')+'；命中 '+(support.matched_rule_ids?.join('、')||'无')+'；结论 '+(support.resolution||'未记录'),
    '原模型支持 '+JSON.stringify(trace.original_support??[])+' 仅供审计，不直接用于专利支持度计算。',
    '中性或冲突原因：'+(support.blockers?.join('；')||'未记录阻断；需同时检查规则命中及完整断言')
  ];
}
export function matchingNotes(trace){
  if(['patent_elements_v1','patent_elements_v2','patent_elements_v3','patent_elements_v4'].includes(trace?.policy))return [
    '准入按规范化五要素交集比例计算；相关性与方向性支持分别判断。',
    '任务解析：'+(trace.task_parse?.status||'未记录')+'；缺失或不支持的条件不会被补造为事实。'
  ];
  if(!['typed_v4','typed_v5'].includes(trace?.policy))return [];
  const v5=trace.policy==='typed_v5';
  const times=v5?{
    within:'明确事件时间位于观察范围内，仅代表上下文时间匹配',
    outside:'明确事件时间超出观察范围，未通过时间准入检查',
    unknown:'事件时间未明确，不以发布时间代替；未通过时间准入检查',
    overlap_unknown:'事件时间区间与观察范围部分重叠，计入上下文时间匹配；不构成结果成立的证明'
  }:{within:'明确事件时间位于范围内',outside:'明确事件时间超出范围',unknown:'时间未明确，不补造日期',overlap_unknown:'时间范围部分重叠，暂不计匹配'};
  const notes=[
    '事件关系：'+label(relationLabels,trace.relation),
    '准入阻断：'+(trace.blockers?.length?trace.blockers.map(x=>label(blockerLabels,x)).join('；'):'无明确冲突；仍按关联度门槛判断'),
    '时间判断：'+label(times,trace.time_check?.status)+'。支持向量沿用冻结标注，相关性不代表事件已发生。'
  ];
  if(v5){
    const parse=trace.task_parse||{},status=label({supported_template:'已识别模板',unsupported:'不支持的任务模板，不准入证据'},parse.status);
    notes.push('任务解析：'+status+'（'+label(templateLabels,parse.kind)+'）');
    notes.push('限定条件：'+(parse.conditions?.length?parse.conditions.map(x=>label(conditionLabels,x)).join('；'):'未记录附加限定条件'));
  }
  return notes;
}

// Read only recorded v2 semantics; absence is never inferred as a successful parse.
export function patentSemanticDetails(trace){
  if(!['patent_elements_v2','patent_elements_v3','patent_elements_v4'].includes(trace?.policy))return [];
  const details=[],add=(label,value)=>{if(value!==undefined&&value!==null)details.push({label,value:typeof value==='string'?value:JSON.stringify(value)});};
  const contract=trace.structured_contract;
  add('任务解析',trace.task_parse);
  if(contract){
    add('任务契约',{kind:contract.kind,status:contract.status,participants:contract.participants,action:contract.action});
    add('截止条件',contract.deadline);add('统计或事件周期',contract.time_interval);add('计数口径',contract.count_metric);
    add('契约原文见证',contract.source_witnesses);
  }
  add('有效目标',trace.effective_target);add('规范化证据要素',trace.effective_elements);
  add('要素原文见证（位置与作用域）',trace.normalization?.witnesses);
  add('未获原文支持的要素',trace.normalization?.removed);
  const assertion=trace.normalization?.assertion;
  if(assertion)add('断言作用域',(assertion.text??'未记录原句')+' ｜ 原文位置 '+(assertion.start??'未记录')+'–'+(assertion.end??'未记录')+' ｜ '+(assertion.scope??'未记录')+' ｜ 引文绑定 '+(assertion.quote_bound??'未记录'));
  add('关联原文句段',trace.normalization?.linked_sentences);
  add('实际读取原文范围',trace.normalization?.context_read_span);
  add('跨句条件见证',trace.support?.linked_condition_witnesses);
  add('事件时间检查',trace.support?.time_check);
  add('时间关联原句',trace.normalization?.temporal_linked_sentences);
  add('任务条件原文',trace.support?.condition_witnesses);
  add('证据阶段',trace.support?.evidence_class);
  add('是否为终局断言（不等于官方结算）',trace.support?.outcome_determined);
  add('支持规则及命中原因',trace.support?.rules);
  add('中性或冲突原因',trace.support?.blockers);
  return details;
}
