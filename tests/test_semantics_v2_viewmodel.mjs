import test from 'node:test';
import assert from 'node:assert/strict';
import {executionDefaults,buildReplayOptions,executionView} from '../web/execution-model.mjs';
import {freshExecution,freshPreviewPayload} from '../web/fresh-model.mjs';
import {matchingNotes,comparisonCheck} from '../web/view-model.mjs';
const base={mode:'enhanced',initial_window_days:30,earliest_days:90,min_window_days:7,band_days:7,grid_days:2,total_budget:100,round_budget:10,rounds:5};
const fresh={execution_preset:'patent',cap_fraction:'.31',width_fraction:'.5',retrieval_policy:'bm25_read_guard_v1',evidence_policy:'patent_elements_v2'};
test('v2 selected for new events survives preview freeze and replay restoration',()=>{
 const execution=freshExecution(fresh);
 assert.equal(execution.evidence_policy,'patent_elements_v2');
 const preview=freshPreviewPayload({cutoff:'2026-10-01T00:00',max_documents:20,count:2,execution});
 assert.equal(preview.execution.evidence_policy,'patent_elements_v2');
 const defaults=executionDefaults({provenance:execution});
 assert.equal(defaults.evidence_policy,'patent_elements_v2');
 assert.equal(buildReplayOptions({...base,...defaults},base).execution.evidence_policy,'patent_elements_v2');
});
test('v1 saved configurations and explicit new-event selection retain v1',()=>{
 const execution=freshExecution({...fresh,evidence_policy:'patent_elements_v1'});
 assert.equal(execution.evidence_policy,'patent_elements_v1');
 const defaults=executionDefaults({provenance:execution});
 assert.equal(defaults.evidence_policy,'patent_elements_v1');
 assert.equal(buildReplayOptions({...base,...defaults},base).execution.evidence_policy,'patent_elements_v1');
 assert.equal(executionDefaults({}).evidence_policy,'');
});
test('unknown evidence policy is rejected by both request builders',()=>{
 assert.throws(()=>freshExecution({...fresh,evidence_policy:'patent_elements_unknown'}));
 assert.throws(()=>buildReplayOptions({...base,execution_policy:'patent',grid_cap_fraction:.31,grid_width_fraction:.5,evidence_policy:'patent_elements_unknown'},base));
});
test('v2 matching and execution notes explain intersection admission independently of support',()=>{
 const notes=matchingNotes({policy:'patent_elements_v2',task_parse:{status:'supported_template'}}).join(' ');
 assert.match(notes,/交集/);assert.match(notes,/方向性支持/);
 assert.match(executionView({provenance:{evidence_policy:'patent_elements_v2'}},null).policy,/v2/);
 assert.match(executionView({provenance:{evidence_policy:'patent_elements_v1'}},null).policy,/交集/);
});
test('v1 and v2 outputs cannot become a same-configuration comparison',()=>{
 const a={computation_version:'same-code',task:{market_id:'x'},config:{mode:'fixed'},provenance:{input_sha256:'i',annotation_sha256:'a',evidence_policy:'patent_elements_v1'}};
 const b={...a,config:{mode:'basic'},provenance:{...a.provenance,evidence_policy:'patent_elements_v2'}};
 assert.equal(comparisonCheck([a,b]).ok,false);
});

import * as viewModel from '../web/view-model.mjs';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const semanticTrace={policy:'patent_elements_v2',task_parse:{status:'supported_template',kind:'ceasefire'},structured_contract:{kind:'ceasefire',status:'supported',participants:['Russia','Ukraine'],action:'ceasefire_in_effect',deadline:{date:'2026-10-31',timezone:'UTC',year_source:'question'},time_interval:null,count_metric:null,source_witnesses:[{text:'ceasefire',start:8,end:16,scope:'question'}]},effective_target:{subject:'Russia',object:'Ukraine',action:'ceasefire_in_effect'},effective_elements:{subject:'Russia'},normalization:{witnesses:{subject:[{text:'Russia',start:0,end:6,scope:'body'}]},assertion:{text:'Russia and Ukraine entered a ceasefire.',start:0,end:39,scope:'complete_original_title_or_body_sentence',quote_bound:true}},support:{time_check:{status:'within',event_time:'2026-10-01',cutoff:'2026-10-02T00:00:00Z',publication_time_substituted:false},rules:[{rule_id:'ceasefire_rule',matched:false,reason:'Requires a completed bilateral ceasefire.',blockers:['event_time_unknown']}],blockers:['event_time_unknown']}};
test('v2 diagnostic details retain contract, time, canonical witnesses and local assertion scope without changing input',()=>{
 const before=JSON.stringify(semanticTrace);
 assert.equal(typeof viewModel.patentSemanticDetails,'function');
 const text=viewModel.patentSemanticDetails(semanticTrace).map(x=>x.label+': '+x.value).join('\n');
 for(const token of ['ceasefire','Russia','Ukraine','2026-10-31','question','2026-10-01','body','complete_original_title_or_body_sentence','Requires a completed bilateral ceasefire.','event_time_unknown'])assert(text.includes(token),token);
 assert.equal(JSON.stringify(semanticTrace),before);
 assert.deepEqual(viewModel.patentSemanticDetails(null),[]);
 assert.deepEqual(viewModel.patentSemanticDetails({policy:'patent_elements_v1'}),[]);
});
test('v2 semantic details render as literal text and keep the raw evidence trace',async()=>{
 class Element {constructor(tag){this.tag=tag;this.children=[];this.style={};this.dataset={};this.value='';}set textContent(value){this.value=String(value);this.children=[];}get textContent(){return this.value+this.children.map(x=>x.textContent).join('');}set innerHTML(value){throw Error('Evidence must be literal text');}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.value='';this.children=[...nodes];}get lastChild(){return this.children.at(-1);}addEventListener(){}}
 const hostile='<img src=x onerror="globalThis.injected=true">',trace=structuredClone(semanticTrace);trace.normalization.assertion.text=hostile;
 const evidence={id:'v2',title:'Evidence',quote:'Frozen quote',support:[0,0],elements:{},matching_trace:{policy:'patent_elements_v2',task_parse:trace.task_parse},patent_evidence_trace:trace};
 const host=new Element('div'),app=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
 const context=vm.createContext({...viewModel,document:{createElement:tag=>new Element(tag)},$:()=>host,state:{run:{task:{target_elements:{}},config:{admission:.5}},index:0,evidenceSerial:0},visibleEvidence:()=>[evidence],renderEvidence:()=>{},date:value=>value||'—'});
 vm.runInContext(app.split('\n').find(line=>line.startsWith('const node='))+'\n'+app.slice(app.indexOf('async function selectEvidence('),app.indexOf('function renderRecord(')),context);
 await vm.runInContext('selectEvidence("v2",false)',context);
 const paragraphs=host.children.flatMap(x=>x.children).filter(x=>x.tag==='p').map(x=>x.textContent);
 assert(paragraphs.some(x=>x.includes('断言作用域')&&x.includes(hostile)));
 assert(paragraphs.some(x=>x.includes('任务契约')&&x.includes('ceasefire')));
 const raw=host.children.find(x=>x.tag==='details').children.find(x=>x.tag==='pre').textContent;
 assert.deepEqual(JSON.parse(raw).patent_evidence_trace,trace);assert.equal(context.injected,undefined);
});
