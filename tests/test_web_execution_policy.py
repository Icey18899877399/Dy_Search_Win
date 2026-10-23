import copy, http.client, inspect, json, tempfile, threading, unittest
from pathlib import Path
from dynamic_retrieval.cli import save_run, write_json
from dynamic_retrieval.demo import demo_inputs, demo_result
from dynamic_retrieval.web_catalog import Catalog
from dynamic_retrieval.web_jobs import JobManager, worker
EXECUTION={'budget_policy':'patent_budget_v1','grid_policy':{'version':'patent_grid_v1','cap_fraction':.2,'width_fraction':.25},'source_cost_profile':None}
class WebExecutionTests(unittest.TestCase):
 def setUp(self):
  runtime=Path(__file__).resolve().parents[1]/'.runtime';runtime.mkdir(exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=runtime);self.root=Path(self.tmp.name)
  self.result=demo_result();self.folder=self.root/'artifacts/sample';self.save_source()
  self.catalog=Catalog(self.root);self.ident=self.catalog.list()['runs'][0]['id'];self.manager=JobManager(self.root,self.catalog,start=False)
 def save_source(self):
  import hashlib
  save_run(self.result,self.folder)
  task,docs,annotations=demo_inputs()
  for name,value in [('task',task),('documents',docs),('annotations',annotations)]:write_json(self.folder/'inputs'/f'{name}.json',value)
  manifest=json.loads((self.folder/'manifest.json').read_text(encoding='utf-8'))
  for path in (self.folder/'inputs').iterdir():manifest['files'][path.relative_to(self.folder).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
  write_json(self.folder/'manifest.json',manifest)
 def tearDown(self):self.manager.close();self.tmp.cleanup()
 def require_execution(self):self.assertIn('execution',inspect.signature(self.manager.submit).parameters,'Frozen submission must accept separate execution options')
 def test_execution_saved_and_idempotency_binds_policy(self):
  self.require_execution();job=self.manager.submit(self.ident,{},'policy',execution=EXECUTION)
  payload=json.loads((self.root/'.runtime/web-jobs'/job['id']/'payload.json').read_text(encoding='utf-8'))
  self.assertEqual(payload['execution'],EXECUTION);self.assertNotIn('budget_policy',payload['config'])
  self.assertEqual(self.manager.submit(self.ident,{},'policy',execution=copy.deepcopy(EXECUTION))['id'],job['id'])
  with self.assertRaisesRegex(ValueError,'Idempotency'):self.manager.submit(self.ident,{},'policy',execution={})
 def test_rejects_unsafe_shapes_and_grid_in_non_enhanced_mode(self):
  self.require_execution()
  malformed=[{'cutoff':'2030'},[],{'budget_policy':True},{'budget_policy':'other'},{'grid_policy':{'version':'patent_grid_v1','cap_fraction':True,'width_fraction':.25}},{'grid_policy':{'version':'patent_grid_v1','cap_fraction':.2,'width_fraction':float('nan')}},{'source_cost_profile':'D:/profile.json'},{'source_cost_profile':{'version':'patent_source_cost_v1','observations':'file'}}]
  for i,value in enumerate(malformed):
   with self.subTest(value=value),self.assertRaises(ValueError):self.manager.submit(self.ident,{},'bad'+str(i),execution=value)
  with self.assertRaises(ValueError):self.manager.submit(self.ident,{'mode':'basic'},'grid-basic',execution=EXECUTION)
  self.assertEqual(self.manager.jobs,{})
 def test_omitted_options_inherit_new_result_but_explicit_empty_restores_legacy(self):
  self.require_execution();self.result['provenance'].update(budget_policy='patent_budget_v1',grid_policy=EXECUTION['grid_policy'],comparison_policy='typed_v6');self.save_source();self.catalog.refresh()
  job=self.manager.submit(self.ident,{},'inherit');self.assertEqual(job['execution'],EXECUTION)
  payload=json.loads((self.root/'.runtime/web-jobs'/job['id']/'payload.json').read_text(encoding='utf-8'));self.assertEqual(payload['comparison_policy'],'typed_v6')
  self.assertEqual(self.manager.submit(self.ident,{},'legacy',execution={})['execution'],{})
 def test_worker_applies_actual_budget_policy_and_preserves_hashes(self):
  self.require_execution();execution={'budget_policy':'patent_budget_v1','grid_policy':None,'source_cost_profile':None}
  job=self.manager.submit(self.ident,{'rounds':2},'worker',execution=execution);output=self.root/'artifacts/output'
  worker(self.root/'.runtime/web-jobs'/job['id']/'payload.json',output)
  result=json.loads((output/'result.json').read_text(encoding='utf-8'))
  self.assertEqual(result['provenance']['budget_policy'],'patent_budget_v1');self.assertEqual(result['provenance']['input_sha256'],self.result['provenance']['input_sha256'])
  self.assertEqual(result['rounds'][0]['decision_trace']['budget_plan']['regular_baseline'],self.result['config']['total_budget']/2)
 def test_worker_grid_and_source_profile_are_applied_and_replayable(self):
  self.require_execution()
  task,docs,annotations=demo_inputs()
  profile=dict(version='patent_source_cost_v1',observations=[dict(source_id=source,interface_id='fixture:'+source,observation_id='test:'+source,observed_at=task['cutoff'],measurement_kind='synthetic',response_latency_seconds=1,rate_limit_quota=10,returned_items=2,observation_window='synthetic test only',quota_unit='requests/day') for source in sorted({d['source_id'] for d in docs})],weights=dict(response_latency_seconds=.2,rate_limit_quota=.3,returned_items=.5),base_cost=1,budget_unit='simulation_units')
  options=copy.deepcopy(EXECUTION);options['source_cost_profile']=profile
  job=self.manager.submit(self.ident,{'rounds':2},'cost-worker',execution=options);output=self.root/'artifacts/cost-output'
  worker(self.root/'.runtime/web-jobs'/job['id']/'payload.json',output)
  result=json.loads((output/'result.json').read_text(encoding='utf-8'))
  self.assertEqual(result['provenance']['grid_policy'],options['grid_policy'])
  self.assertEqual(result['provenance']['source_cost_profile']['profile'],profile)
  self.assertEqual(result['diagnostics']['source_cost_profile']['observation_status'],'synthetic_formula_fixture')
  self.assertTrue(result['rounds'][0]['decision_trace']['grid_budget']['cells'])
  self.catalog.refresh()
  output_id=next(row['id'] for row in self.catalog.list()['runs'] if row['id']!=self.ident)
  inherited=self.manager.submit(output_id,{},'cost-inherit')
  self.assertEqual(inherited['execution'],options)
 def test_guarded_bm25_worker_and_inherited_replay(self):
  options=dict(budget_policy='patent_budget_v1',grid_policy=dict(version='patent_grid_v1',cap_fraction=.31,width_fraction=.5),retrieval_policy='bm25_read_guard_v1')
  job=self.manager.submit(self.ident,{'rounds':2},'guarded-worker',execution=options)
  output=self.root/'artifacts/guarded-output'
  worker(self.root/'.runtime/web-jobs'/job['id']/'payload.json',output)
  result=json.loads((output/'result.json').read_text(encoding='utf-8'))
  self.assertEqual(result['provenance']['retrieval_policy'],options['retrieval_policy'])
  self.assertEqual(result['provenance']['input_sha256'],self.result['provenance']['input_sha256'])
  self.assertTrue(result['diagnostics']['retrieval_execution']['indexed_document_ids'])
  self.catalog.refresh()
  output_id=next(row['id'] for row in self.catalog.list()['runs'] if row['id']!=self.ident)
  inherited=self.manager.submit(output_id,{},'guarded-inherit')
  self.assertEqual(inherited['execution']['retrieval_policy'],options['retrieval_policy'])
 def test_grid_limits_and_profile_policy_fail_before_queueing(self):
  for grid in [dict(version='patent_grid_v1',cap_fraction=.9,width_fraction=.25),dict(version='patent_grid_v1',cap_fraction=.2,width_fraction=.00001)]:
   with self.assertRaisesRegex(ValueError,'grid'):
    self.manager.submit(self.ident,{},'invalid-grid-'+str(grid['width_fraction']),execution=dict(EXECUTION,grid_policy=grid))
  with self.assertRaisesRegex(ValueError,'patent_budget_v1'):
   self.manager.submit(self.ident,{},'invalid-cost-policy',execution={'source_cost_profile':{}})
  self.assertEqual(self.manager.jobs,{})
 def test_invalid_cost_worker_reports_safe_specific_reason(self):
  import time
  task,docs,annotations=demo_inputs()
  profile=dict(version='patent_source_cost_v1',observations=[dict(source_id=source,interface_id='fixture:'+source,observation_id='test:'+source,observed_at=task['cutoff'],measurement_kind='synthetic',response_latency_seconds=1,returned_items=2,observation_window='synthetic test only',quota_unit='requests/day') for source in sorted({d['source_id'] for d in docs})],weights=dict(response_latency_seconds=.2,rate_limit_quota=.3,returned_items=.5),base_cost=1,budget_unit='simulation_units')
  self.manager.close();self.manager=JobManager(self.root,self.catalog)
  job=self.manager.submit(self.ident,{},'missing-quota',execution=dict(EXECUTION,source_cost_profile=profile))
  deadline=time.monotonic()+10
  while time.monotonic()<deadline and self.manager.get(job['id'])['status'] in ('queued','running'):time.sleep(.02)
  job=self.manager.get(job['id']);self.assertEqual(job['status'],'failed')
  self.assertIn('rate_limit_quota',job['error'])
  safe=json.loads((self.root/'.runtime/web-jobs'/job['id']/'validation-error.json').read_text(encoding='utf-8'))
  self.assertEqual(safe['code'],'cost_rate_limit_quota')
 def test_source_mismatch_is_reported_without_echoing_source_contents(self):
  task,docs,annotations=demo_inputs()
  profile=dict(version='patent_source_cost_v1',observations=[dict(source_id='sensitive-value-not-to-echo',interface_id='test',observation_id='test',observed_at=task['cutoff'],measurement_kind='synthetic',response_latency_seconds=1,rate_limit_quota=1,returned_items=1,observation_window='test',quota_unit='requests/day')],weights=dict(response_latency_seconds=.2,rate_limit_quota=.3,returned_items=.5),base_cost=1,budget_unit='simulation_units')
  job=self.manager.submit(self.ident,{},'missing-source',execution=dict(EXECUTION,source_cost_profile=profile))
  directory=self.root/'.runtime/web-jobs'/job['id']
  with self.assertRaises(ValueError):worker(directory/'payload.json',self.root/'artifacts/invalid-output')
  safe=json.loads((directory/'validation-error.json').read_text(encoding='utf-8'))
  self.assertEqual(safe['code'],'cost_source_coverage')
  self.assertNotIn('sensitive-value-not-to-echo',json.dumps(safe))
 def test_http_execution_route_and_token_boundary(self):
  self.require_execution()
  from dynamic_retrieval.web_server import Handler,LocalServer
  server=LocalServer(('127.0.0.1',0),Handler);server.token='test-token';server.jobs=self.manager
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  def request(payload,token='test-token'):
   conn=http.client.HTTPConnection('127.0.0.1',server.server_port);conn.request('POST','/api/jobs',json.dumps(payload),{'Content-Type':'application/json','X-Run-Token':token})
   response=conn.getresponse();body=json.loads(response.read());conn.close();return response.status,body
  payload={'source_id':self.ident,'config':{},'idempotency_key':'http','execution':EXECUTION}
  try:
   self.assertEqual(request(payload,'wrong')[0],403)
   status,body=request(payload);self.assertEqual(status,202,body);self.assertEqual(body['job']['execution'],EXECUTION)
   self.assertEqual(request(dict(payload,unknown=True))[0],400)
  finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
