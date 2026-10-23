import test from 'node:test';
import assert from 'node:assert/strict';
import {patentSemanticDetails,matchingNotes} from '../web/view-model.mjs';
import {executionView} from '../web/execution-model.mjs';
import {readFileSync} from 'node:fs';
test('v3 displays recorded linked source spans and neutral reasons',()=>{
 const trace={policy:'patent_elements_v3',normalization:{linked_sentences:[{text:'Both sides agreed.',start:42,end:60}],context_read_span:[0,12000]},support:{blockers:['event_time_unresolved'],linked_condition_witnesses:{general:[{text:'all military operations'}]}}};
 const text=patentSemanticDetails(trace).map(x=>x.label+x.value).join('\n');
 for(const part of ['Both sides agreed.','42','12000','all military operations','event_time_unresolved'])assert(text.includes(part));
 assert(matchingNotes(trace).length>0);assert(executionView({provenance:{evidence_policy:'patent_elements_v3'}},null).policy.includes('patent_elements_v3'));
});
test('v3 is selectable in replay and fresh forms without becoming default',()=>{
 for(const path of ['../web/index.html','../web/fresh.js']){
  const text=readFileSync(new URL(path,import.meta.url),'utf8');assert(text.includes('value="patent_elements_v3"'));assert(!text.includes('value="patent_elements_v3" selected'));
 }
});
