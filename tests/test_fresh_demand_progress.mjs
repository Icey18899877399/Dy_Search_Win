import assert from 'node:assert/strict';
import {freshJobView} from '../web/fresh-model.mjs';
const view=freshJobView({extraction_mode:'on_demand',model_request_upper_bound:60,total_documents:20,completed_documents:16,validated_documents:16,failed_documents:0});
assert.match(view.extraction,/上限 60/);
assert.match(view.extraction,/16 次/);
