import test from 'node:test';
import assert from 'node:assert/strict';
import { roundView, comparisonCheck, direction, safeUrl, filterRuns, chooseDefaultRun, effectiveTarget, admissionStatus, rejectionDescription, pickComparisonRuns } from '../web/view-model.mjs';
const run = {computation_version:'core-v1',task:{question:'Q',market_id:'m',cutoff:'2026-01-20',outcomes:['Yes','No']},config:{mode:'enhanced',total_budget:10},provenance:{input_sha256:'x',annotation_sha256:'y'},rounds:[{round:1,retrieved_ids:['a'],recovered_ids:[],window_ids:['a'],probabilities:[.6,.4],source_states:{s:{active:false}},remaining:8},{round:2,retrieved_ids:['b'],recovered_ids:[],window_ids:['b'],probabilities:[.7,.3],source_states:{s:{active:true}},remaining:6}],evidence:[{id:'a',weight:9,support:[1,0]},{id:'b',weight:7,support:[0,0]}]};
test('empty rounds never reveal final evidence or fabricate probability',()=>{let v=roundView({...run,rounds:[]},0);assert.deepEqual(v.evidence,[]);assert.equal(v.round,null);assert.equal(v.probability,null);});
test('earlier round excludes future evidence and final-only weights',()=>{let v=roundView(run,0);assert.deepEqual(v.evidence.map(e=>e.id),['a']);assert.equal(v.evidence[0].in_window,true);assert.equal(v.evidence[0].historical_weight,null);assert.equal(v.probability,.6);});
test('round membership and source state belong to selected round',()=>{let v=roundView(run,1);assert.equal(v.evidence[0].in_window,false);assert.equal(v.evidence[1].in_window,true);assert.equal(v.sources.s.active,true);assert.equal(v.spent,4);});
test('comparison rejects absent or differing hashes, semantics and config',()=>{let b=structuredClone(run);b.config.mode='fixed';assert.equal(comparisonCheck([run,b]).ok,true);b.provenance.input_sha256='z';assert.equal(comparisonCheck([run,b]).ok,false);b=structuredClone(run);b.task.question='Different';assert.equal(comparisonCheck([run,b]).ok,false);b=structuredClone(run);b.config.total_budget=12;assert.equal(comparisonCheck([run,b]).ok,false);b=structuredClone(run);delete b.provenance;assert.equal(comparisonCheck([run,b]).ok,false);});
test('neutral and contrary support remain distinguishable',()=>{assert.equal(direction({support:[0,0]}),'neutral');assert.equal(direction({support:[0,1]}),'against');assert.equal(direction({support:[1,0]}),'support');});
test('source links reject javascript and other unsafe protocols',()=>{assert.equal(safeUrl('javascript:alert(1)'),null);assert.equal(safeUrl('file:///secret'),null);assert.equal(safeUrl('https://example.org/a'),'https://example.org/a');});
test('catalog filtering is case insensitive and pages bounded',()=>{let rows=[{question:'Iran one',mode:'enhanced'},{question:'Iran two',mode:'fixed'},{question:'Other',mode:'fixed'}];assert.equal(filterRuns(rows,{query:'IRAN',mode:'fixed'}).length,1);});

test('comparison rejects missing or mismatched engine computation versions',()=>{let b=structuredClone(run);delete b.computation_version;assert.equal(comparisonCheck([run,b]).ok,false);b.computation_version='core-v2';assert.equal(comparisonCheck([run,b]).ok,false);});

test('default selection prefers latest semantic enhanced batch without selecting a hardcoded market',()=>{const rows=[{id:'a',mode:'enhanced',batch:'automatic-20260515'},{id:'b',mode:'enhanced',batch:'semantic-v2-20260515'},{id:'c',mode:'fixed',batch:'semantic-v3-20260515'},{id:'d',mode:'enhanced',batch:'semantic-v3-20260515'}];assert.equal(chooseDefaultRun(rows).id,'d');assert.equal(chooseDefaultRun([...rows,{id:'e',mode:'enhanced',batch:'web-runs-20261022'}]).id,'e');assert.equal(chooseDefaultRun([]),null);});

test('effective matching target uses trace normalization and falls back only when no trace target exists',()=>{const r={task:{target_elements:{subject:'raw question'}}};assert.deepEqual(effectiveTarget(r,{matching_trace:{target:{subject:'named actor',action:'wins'}}}),{subject:'named actor',action:'wins'});assert.deepEqual(effectiveTarget(r,{}),{subject:'raw question'});});
test('unknown diagnostic admission is never presented as rejected',()=>{assert.equal(admissionStatus({admitted:null}),'准入未知');assert.equal(admissionStatus({admitted:false}),'未准入');assert.equal(admissionStatus({admitted:true}),'已准入');assert.equal(rejectionDescription({admitted:false,rejection_reason:'relevance_below_admission_threshold'}),'关联度低于准入门槛');});

test('automatic comparison preserves the selected variant group before other runs in the same batch',()=>{const rows=['fixed','basic','enhanced'].flatMap(mode=>[{id:'combined-'+mode,market_id:'m',group:'combined',batch:'remediation',mode},{id:'scheduler-'+mode,market_id:'m',group:'scheduler_only',batch:'remediation',mode}]);assert.deepEqual(pickComparisonRuns(rows,rows.find(r=>r.id==='scheduler-enhanced')).map(r=>r.group),['scheduler_only','scheduler_only','scheduler_only']);});
test('comparison fallback requires matching known hashes configuration and computation version',()=>{const current={id:'a',market_id:'m',group:'one',batch:'same',mode:'enhanced',question:'Q',cutoff:'2026-01-01',input_sha256:'input',annotation_sha256:'ann',computation_version:'engine',config:{mode:'enhanced',rounds:10}};const rows=[current,{...current,id:'b',group:'two',mode:'basic',config:{mode:'basic',rounds:10}},{...current,id:'c',group:'three',mode:'fixed',input_sha256:'different',config:{mode:'fixed',rounds:10}},{...current,id:'d',group:'four',mode:'fixed',computation_version:null,config:{mode:'fixed',rounds:10}}];assert.deepEqual(pickComparisonRuns(rows,current).map(r=>r.id).sort(),['a','b']);});

import * as viewModel from '../web/view-model.mjs';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const v5Trace={policy:'typed_v5',relation:'opposing_state',blockers:['conflicting_claims'],time_check:{status:'within'},task_parse:{status:'supported_template',kind:'uranium_agreement',conditions:['public Iranian agreement to surrender; conflicting anonymous reports are not agreement']}};
const notesFor=trace=>(viewModel.matchingNotes?.(trace)||[]).join('\n');
test('V5 explains opposing evidence, conflicting claims and required agreement without asserting an outcome',()=>{
  const trace=structuredClone(v5Trace),before=JSON.stringify(trace),text=notesFor(trace);
  assert.match(text,/事件关系：相反状态/);assert.match(text,/准入阻断：.*说法.*冲突/);
  assert.match(text,/任务解析：.*已识别.*伊朗铀库存移交协议/);
  assert.match(text,/限定条件：.*伊朗公开同意.*冲突.*匿名/);
  assert.match(text,/不代表事件已发生/);assert.equal(JSON.stringify(trace),before);
});
test('V5 unknown event dates block time admission and never substitute publication dates',()=>{
  const text=notesFor({...v5Trace,blockers:['event_time_unknown'],time_check:{status:'unknown'}});
  assert.match(text,/准入阻断：事件时间未明确/);assert.match(text,/不以发布时间代替/);assert.match(text,/未通过时间准入检查/);
});
test('V5 intersecting intervals count as context matching without proving the outcome',()=>{
  const text=notesFor({...v5Trace,blockers:[],time_check:{status:'overlap_unknown'}});
  assert.match(text,/部分重叠.*计入上下文时间匹配/);assert.match(text,/不构成结果成立的证明/);assert.doesNotMatch(text,/暂不计匹配/);
});
test('unsupported V5 tasks are distinguished from legacy typed templates and old policies',()=>{
  const unsupported=notesFor({...v5Trace,blockers:['unsupported_task'],task_parse:{status:'unsupported',kind:'unsupported',conditions:[]}});
  assert.match(unsupported,/不支持的任务模板/);assert.match(unsupported,/不准入证据/);
  const legacy=notesFor({...v5Trace,task_parse:{status:'supported_template',kind:'legacy_typed',conditions:[]}});
  assert.match(legacy,/沿用 V4 类型化任务/);assert.doesNotMatch(legacy,/不支持的任务模板/);
  assert.equal(notesFor({policy:'typed_v3'}),'');assert.equal(notesFor(null),'');
});
test('V4 keeps its original overlap interpretation and original relation and blocker wording',()=>{
  assert.deepEqual(viewModel.matchingNotes?.({policy:'typed_v4',relation:'military_progress_not_capture',blockers:['location_mismatch'],time_check:{status:'overlap_unknown'}}),[
    '事件关系：军事进展，不能等同已攻占','准入阻断：地点不一致',
    '时间判断：时间范围部分重叠，暂不计匹配。支持向量沿用冻结标注，相关性不代表事件已发生。'
  ]);
});
test('selectEvidence renders V5 notes as literal text and preserves the complete raw trace',async()=>{
  class Element {
    constructor(tag){this.tag=tag;this.children=[];this.style={};this.dataset={};this.value='';}
    set textContent(value){this.value=String(value);this.children=[];}
    get textContent(){return this.value+this.children.map(x=>x.textContent).join('');}
    set innerHTML(value){throw new Error('Evidence details must never render HTML');}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.value='';this.children=[...nodes];}
    get lastChild(){return this.children.at(-1);}
    addEventListener(){}
  }
  const hostile='<img src=x onerror="globalThis.injected=true">',trace={...structuredClone(v5Trace),relation:hostile};
  trace.task_parse.conditions.push(hostile);
  const evidence={id:'e',title:'Evidence',quote:'Frozen quotation',support:[0,1],elements:{},matching_trace:trace};
  const host=new Element('div'),app=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
  const context=vm.createContext({...viewModel,document:{createElement:tag=>new Element(tag)},$:()=>host,
    state:{run:{task:{target_elements:{}},config:{admission:.5}},index:0,evidenceSerial:0},
    visibleEvidence:()=>[evidence],renderEvidence:()=>{},date:value=>value||'—'});
  vm.runInContext(app.split('\n').find(line=>line.startsWith('const node='))+'\n'+app.slice(app.indexOf('async function selectEvidence('),app.indexOf('function renderRecord(')),context);
  await vm.runInContext('selectEvidence("e",false)',context);
  const paragraphs=host.children.flatMap(x=>x.children).filter(x=>x.tag==='p').map(x=>x.textContent);
  assert(paragraphs.includes('事件关系：'+hostile));assert(paragraphs.some(x=>x.startsWith('限定条件：')&&x.includes(hostile)));
  const raw=host.children.find(x=>x.tag==='details').children.find(x=>x.tag==='pre').textContent;
  assert.deepEqual(JSON.parse(raw).matching_trace,trace);assert.equal(context.injected,undefined);
});
