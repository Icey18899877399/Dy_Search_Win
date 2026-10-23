import test from 'node:test';
import assert from 'node:assert/strict';
import {comparisonCheck} from '../web/view-model.mjs';
test('same source code and corpus do not imply same evidence or budget policy',()=>{
 const a={task:{market_id:'x'},config:{mode:'fixed'},computation_version:'sha',provenance:{input_sha256:'i',annotation_sha256:'a',evidence_policy:'patent_elements_v1'}};
 const b=structuredClone(a);b.config.mode='enhanced';assert.equal(comparisonCheck([a,b]).ok,true);
 for(const key of ['evidence_policy','comparison_policy','budget_policy','retrieval_policy','fact_policy','runtime_policy']){
  const changed=structuredClone(b);changed.provenance[key]='different';assert.equal(comparisonCheck([a,changed]).ok,false,key);
 }
});
