import test from 'node:test';
import assert from 'node:assert/strict';
import * as execution from '../web/execution-model.mjs';
const base={mode:'enhanced',initial_window_days:14,earliest_days:120,min_window_days:3,band_days:14,grid_days:3.5,total_budget:200,round_budget:20,rounds:24};
test('patent replay keeps policy strings separate and retains valid disabled legacy round budget',()=>{
 assert.equal(typeof execution.buildReplayOptions,'function');
 const actual=execution.buildReplayOptions({...base,total_budget:'100',rounds:'5',round_budget:undefined,execution_policy:'patent',grid_cap_fraction:'0.2',grid_width_fraction:'0.25',source_cost_json:''},base);
 assert.equal(actual.config.round_budget,20);assert.equal(actual.config.total_budget,100);assert.equal(actual.config.rounds,5);
 assert.equal(actual.execution.budget_policy,'patent_budget_v1');assert.equal(actual.execution.grid_policy.version,'patent_grid_v1');assert.equal(actual.execution.source_cost_profile,null);
 assert.equal(actual.config.execution_policy,undefined);
});
test('legacy choice explicitly clears inherited execution and basic has no enhanced grid',()=>{
 assert.equal(typeof execution.buildReplayOptions,'function');
 assert.deepEqual(execution.buildReplayOptions({...base,execution_policy:'legacy'},base).execution,{});
 assert.equal(execution.buildReplayOptions({...base,mode:'basic',execution_policy:'patent',source_cost_json:''},base).execution.grid_policy,null);
});
test('opening a patent result restores source profile and custom grid values',()=>{
 assert.equal(typeof execution.executionDefaults,'function');
 const profile={version:'patent_source_cost_v1',observations:[]};
 const values=execution.executionDefaults({provenance:{budget_policy:'patent_budget_v1',grid_policy:{version:'patent_grid_v1',cap_fraction:.1,width_fraction:.5},source_cost_profile:{profile}}});
 assert.equal(values.execution_policy,'patent');assert.equal(values.grid_cap_fraction,.1);assert.equal(values.grid_width_fraction,.5);assert.deepEqual(JSON.parse(values.source_cost_json),profile);
 assert.equal(execution.executionDefaults({}).execution_policy,'legacy');
});
test('historical result remains historical and missing cost calibration stays explicit',()=>{
 assert.equal(typeof execution.executionView,'function');
 assert.match(execution.executionView({}).policy,/历史/);
 const view=execution.executionView({provenance:{budget_policy:'patent_budget_v1',grid_policy:{version:'patent_grid_v1'}},rounds:[]});
 assert.match(view.policy,/patent_budget_v1/);assert.match(view.cost,/示例成本.*未标定/);
});
test('invalid profile JSON and fractions never produce a submission',()=>{
 assert.equal(typeof execution.buildReplayOptions,'function');
 for(const source_cost_json of ['not-json','[]','"D:/profile.json"'])assert.throws(()=>execution.buildReplayOptions({...base,execution_policy:'patent',grid_cap_fraction:.2,grid_width_fraction:.25,source_cost_json},base));
 assert.throws(()=>execution.buildReplayOptions({...base,execution_policy:'patent',grid_cap_fraction:'NaN',grid_width_fraction:.25,source_cost_json:''},base));
});
test('selected round explanation uses saved round budget and reason only',()=>{
 assert.equal(typeof execution.executionView,'function');
 const view=execution.executionView({provenance:{budget_policy:'patent_budget_v1'}},{budget_plan:{regular_baseline:10,effective:6,reserves:{recovery:2}},recovery_reason:'insufficient_full_band_budget'});
 assert.match(view.round,/10/);assert.match(view.round,/6/);assert.match(view.round,/insufficient_full_band_budget/);
 assert.match(execution.executionView({}).round,/未记录/);
});
test('saved decision trace drives the displayed budget and supplied synthetic cost is not calibrated',()=>{
 const view=execution.executionView({provenance:{budget_policy:'patent_budget_v1',source_cost_profile:{profile:{}}},diagnostics:{source_cost_profile:{observation_status:'synthetic_formula_fixture',empirical_calibration:false}}},{decision_trace:{budget_plan:{regular_baseline:25,effective:12,reserves:{recovery:4}},recovery:{reason:'budget_insufficient'}}});
 assert.match(view.round,/25/);assert.match(view.round,/12/);assert.match(view.round,/budget_insufficient/);assert.match(view.cost,/合成.*未标定/);
});
test('opening a budget-only enhanced result preserves its disabled grid until explicitly enabled',()=>{
 const run={config:base,provenance:{budget_policy:'patent_budget_v1'}};
 const defaults=execution.executionDefaults(run);
 const payload=execution.buildReplayOptions({...base,...defaults},base);
 assert.equal(payload.execution.grid_policy,null);
 assert.equal(execution.buildReplayOptions({...base,...defaults,grid_enabled:'enabled'},base).execution.grid_policy.version,'patent_grid_v1');
});

test('retrieval policy roundtrips without rewriting the chosen budget or grid',()=>{
 const run={provenance:{budget_policy:'patent_budget_v1',retrieval_policy:'bm25_read_guard_v1',grid_policy:{version:'patent_grid_v1',cap_fraction:.31,width_fraction:.5}}};
 const defaults=execution.executionDefaults(run);
 assert.equal(defaults.retrieval_policy,'bm25_read_guard_v1');
 const payload=execution.buildReplayOptions({...base,...defaults},base);
 assert.equal(payload.execution.retrieval_policy,'bm25_read_guard_v1');
 assert.equal(payload.config.total_budget,200);assert.equal(payload.execution.grid_policy.cap_fraction,.31);
 assert.match(execution.executionView(run).policy,/BM25/);
 assert.equal(execution.buildReplayOptions({...base,...defaults,retrieval_policy:''},base).execution.retrieval_policy,undefined);
});
