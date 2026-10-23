import test from 'node:test';
import assert from 'node:assert/strict';
import {executionDefaults,buildReplayOptions,executionView} from '../web/execution-model.mjs';
const base={mode:'enhanced',initial_window_days:14,earliest_days:120,min_window_days:3,band_days:14,grid_days:3.5,total_budget:200,round_budget:20,rounds:24};
test('patent evidence choice is explicit and restored without erasing old policies',()=>{
 const saved={provenance:{budget_policy:'patent_budget_v1',evidence_policy:'patent_elements_v1',grid_policy:{cap_fraction:.31,width_fraction:.5}}};
 const d=executionDefaults(saved);assert.equal(d.evidence_policy,'patent_elements_v1');
 const payload=buildReplayOptions({...base,...d},base);
 assert.equal(payload.execution.evidence_policy,'patent_elements_v1');
 assert.match(executionView(saved).policy,/要素交集/);
 assert.equal(buildReplayOptions({...base,...d,evidence_policy:''},base).execution.evidence_policy,undefined);
 assert.equal(executionDefaults({}).evidence_policy,'');
 assert.throws(()=>buildReplayOptions({...base,...d,evidence_policy:'invented'},base));
});
import {matchingNotes,patentSupportNotes} from '../web/view-model.mjs';
test('patent evidence UI separates overlap admission and support rule abstention',()=>{
 assert.match(matchingNotes({policy:'patent_elements_v1',task_parse:{status:'unsupported'}}).join(' '),/交集/);
 const trace={original_support:[1,-1],support:{resolution:'no_matching_rule',contract_source:'none',matched_rule_ids:[],blockers:['event_time_after_cutoff']}};
 const text=patentSupportNotes(trace).join(' ');
 assert.match(text,/原模型/); assert.match(text,/event_time_after_cutoff/); assert.match(text,/不直接用于/);
 assert.deepEqual(patentSupportNotes(null),[]);
});
