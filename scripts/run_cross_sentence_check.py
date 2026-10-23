"""Bounded seven-case paired extraction; no independent evaluation or labels."""
from pathlib import Path
import sys,json,hashlib,argparse
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.semantic import DeepSeekClient,DATA_FIELDS
from dynamic_retrieval.semantic_pipeline import _extract_one
from dynamic_retrieval.call_cost import CallCostLedger
from dynamic_retrieval.evidence import extract
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.cli import save_run

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def execute(out):
 if out.exists() or not out.is_relative_to(ROOT/'artifacts'):raise ValueError('New D project artifact directory required')
 source=ROOT/'artifacts/fact-coverage-20261023';cards=read(ROOT/'artifacts/fact-windows-20261023/fact-cards.json')
 sm=read(source/'experiment-manifest.json')
 for name,h in sm['files'].items():assert sha(source/name)==h
 code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')};code['scripts/run_cross_sentence_check.py']=sha(__file__)
 selected=[c for c in cards if c['model_window_status']=='prepared_not_sent'];assert len(selected)==7
 write(out/'execution-plan.json',dict(scope='previously_inspected_development_cases',selected_ids=[c['document_id'] for c in selected],
  model='deepseek-flash',max_requests=14,max_attempts=1,max_excerpt_chars=12000,
  arms=['head','fact_window_v1'],evidence_policies=['patent_elements_v2','patent_elements_v3'],
  selection='nine_existing_fact_cards_excluding_two_source_failures',label_access=False,independent_evaluation=False,
  source_manifest_sha256=sha(source/'experiment-manifest.json'),code_sha256=code))
 ledger=CallCostLedger(out/'api-ledger.jsonl');client=DeepSeekClient(out/'cache',max_attempts=1,timeout=60,cost_ledger=ledger)
 records=[];traces=[];runs=[];parity=0
 for market in ('1171663','1423716','2354063'):
  task=read(source/f'inputs/{market}/task.json');all_docs=read(source/f'inputs/{market}/documents.json')
  ids={c['document_id'] for c in selected if c['market_id']==market};docs=[d for d in all_docs if d['id'] in ids]
  cfg=Config.from_dict(read(ROOT/f'artifacts/semantics-v2-final-20261023/runs/{market}/enhanced/result.json')['config'])
  for arm in ('head','fact_window_v1'):
   t=deepcopy(task)
   if arm!='head':t['evidence_context_policy']=arm
   write(out/f'inputs/{market}/{arm}/task.json',t);write(out/f'inputs/{market}/{arm}/documents.json',docs)
   annotations={};valid=[]
   for d in docs:
    ann,trace=_extract_one(client,t,d,12000)
    if isinstance(trace.get('parsed_response'),dict):trace['parsed_response']={k:v for k,v in trace['parsed_response'].items() if k in DATA_FIELDS}
    trace.update(market_id=market,arm=arm);traces.append(trace)
    row=dict(market_id=market,arm=arm,document_id=d['id'],status=trace['status'],policies={})
    if ann is not None:
     annotations[d['id']]=ann;valid.append(d)
     for policy in ('patent_elements_v2','patent_elements_v3'):
      ev=extract(d,t,annotations,evidence_policy=policy)
      row['policies'][policy]={k:ev[k] for k in ('elements','relevance','support','quote','patent_evidence_trace')}
      row['policies'][policy]['admitted']=ev['relevance']>=cfg.admission
    records.append(row);write(out/'traces.json',traces);write(out/'documents.json',records)
    print(json.dumps({'market':market,'arm':arm,'document':d['id'][:8],'status':trace['status']},ensure_ascii=False),flush=True)
   write(out/f'inputs/{market}/{arm}/annotations.json',annotations)
   if not valid:continue
   # Diagnostic replay only: failed extractions are excluded explicitly, no rule fallback.
   for policy in ('patent_elements_v2','patent_elements_v3'):
    result=run(t,valid,cfg,annotations,evidence_policy=policy,budget_policy='patent_budget_v1',
     grid_policy={'version':'patent_grid_v1','cap_fraction':.31,'width_fraction':.5},retrieval_policy='bm25_read_guard_v1',decision_trace=True)
    folder=out/f'runs/{market}/{arm}/{policy}';save_run(result,folder)
    for name,value in [('task',t),('documents',valid),('annotations',annotations)]:write(folder/f'inputs/{name}.json',value)
    m=read(folder/'manifest.json');m['files'].update({p.relative_to(folder).as_posix():sha(p) for p in (folder/'inputs').iterdir()});write(folder/'manifest.json',m)
    runs.append(dict(market_id=market,arm=arm,policy=policy,result_path=folder.relative_to(out).as_posix()+'/result.json',input_documents=len(valid)))
  for path in (ROOT/f'artifacts/semantics-v2-final-20261023/runs/{market}').glob('*/result.json'):
   old=read(path);p=old['provenance'];inp=path.parent/'inputs'
   assert run(read(inp/'task.json'),read(inp/'documents.json'),Config.from_dict(old['config']),read(inp/'annotations.json'),evidence_policy=p.get('evidence_policy'),budget_policy=p.get('budget_policy'),grid_policy=p.get('grid_policy'),retrieval_policy=p.get('retrieval_policy'))==old
   parity+=1
 totals=[]
 for arm in ('head','fact_window_v1'):
  rows=[r for r in records if r['arm']==arm]
  for policy in ('patent_elements_v2','patent_elements_v3'):
   ok=[r['policies'][policy] for r in rows if policy in r['policies']]
   totals.append(dict(arm=arm,policy=policy,attempted_documents=len(rows),validated_documents=len(ok),failed_documents=len(rows)-len(ok),admitted=sum(x['admitted'] for x in ok),directional=sum(any(x['support']) for x in ok),admitted_directional=sum(x['admitted'] and any(x['support']) for x in ok)))
 summary=dict(status='completed_development_only',totals=totals,cost=ledger.snapshot(),runs=runs,legacy_parity_runs=parity,independent_evaluation=False,empirical_calibration=False,monetary_cost=None,
  limitations=['purposively_selected_known_cases','machine_unreviewed','no_prediction_accuracy_labels','failed_extractions_not_rule_fallback','bounded_adjacent_anaphora_not_general_coreference'])
 write(out/'summary.json',summary)
 for name,h in code.items():assert sha(ROOT/name)==h
 write(out/'experiment-manifest.json',dict(artifact_type='cross_sentence_development_check',code_sha256=code,files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
 print(json.dumps({'status':summary['status'],'totals':totals,'legacy_parity_runs':parity},ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);execute(p.parse_args().output.resolve())
