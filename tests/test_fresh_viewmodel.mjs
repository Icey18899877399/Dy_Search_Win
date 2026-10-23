import assert from 'node:assert/strict';
import {freshPreviewPayload,freshJobPayload,freshJobView,utcInput} from '../web/fresh-model.mjs';
assert.equal(utcInput('2026-08-28T23:59:59Z'),'2026-08-28T23:59:59');
const base={cutoff:'2026-08-28T23:59:59',max_documents:'20',count:'10',config:{}};
assert.equal(freshPreviewPayload(base).cutoff,'2026-08-28T23:59:59.000Z');
for(const patch of [{max_documents:11},{max_documents:41},{count:0},{count:21},{count:1.5},{cutoff:'invalid'},{config:{api_key:'secret'}},{config:{min_window_days:20,initial_window_days:10}}])assert.throws(()=>freshPreviewPayload({...base,...patch}));
assert.throws(()=>freshJobPayload({preview_id:'p',tasks:[{market_id:'a'}]},[], 'key'));
assert.throws(()=>freshJobPayload({preview_id:'p',tasks:[{market_id:'a'}]},['b'], 'key'));
assert.deepEqual(freshJobPayload({preview_id:'p',tasks:[{market_id:'a'}]},['a','a'],'key'),{preview_id:'p',market_ids:['a'],idempotency_key:'key'});
const v=freshJobView({completed_documents:3,total_documents:8,validated_documents:2,failed_documents:1,completed_runs:1,result_ids:['a','b','c']});
assert.equal(v.extraction,'已抽取 3 / 8 篇 · 验证通过 2 篇 · 失败 1 篇');
assert.equal(v.runs,'已保存策略运行 1 份');
assert.deepEqual(v.resultIds,['a','b','c']);
assert.equal(freshJobView({}).extraction,'文档进度尚未记录');
console.log('fresh view-model tests passed');

// A superseded request may never restore a cohort or reset a newer request's UI.
const {createPreviewGate}=await import('../web/fresh-model.mjs');
const gate=createPreviewGate();
const first=gate.begin();assert.equal(gate.isCurrent(first),true);
gate.invalidate();assert.equal(gate.isCurrent(first),false);
const second=gate.begin();assert.equal(gate.isCurrent(first),false);assert.equal(gate.isCurrent(second),true);
const writes=[];
for(const token of [first,second])if(gate.isCurrent(token))writes.push(token);
assert.deepEqual(writes,[second]);
gate.invalidate();assert.equal(gate.isCurrent(second),false);
console.log('stale preview response guards passed');
