import test from 'node:test';
import assert from 'node:assert/strict';
import {freshExecution} from '../web/fresh-model.mjs';
import {patentSemanticDetails} from '../web/view-model.mjs';
test('v4 survives request validation and shows nonterminal and event-time provenance',()=>{
 const x=freshExecution({execution_preset:'patent',cap_fraction:.31,width_fraction:.5,retrieval_policy:'bm25_read_guard_v1',evidence_policy:'patent_elements_v4'});
 assert.equal(x.evidence_policy,'patent_elements_v4');
 const tr={policy:'patent_elements_v4',support:{evidence_class:'nonterminal_progress',outcome_determined:false,condition_witnesses:[{text:'general halt'}],time_check:{event_time:'2026-05-28',effective_start:'2026-07-02'}},normalization:{temporal_linked_sentences:[{text:'This vote took place on May 28, 2026.'}]}};
 const text=patentSemanticDetails(tr).map(x=>x.value).join('\n');
 for(const s of ['nonterminal_progress','false','general halt','2026-07-02','This vote'])assert(text.includes(s));
});
