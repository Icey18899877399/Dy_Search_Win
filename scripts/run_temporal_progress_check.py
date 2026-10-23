"""Frozen-development diagnostics and paired replay; no network client or labels."""
from pathlib import Path
import json, hashlib, sys
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.evidence import extract
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.cli import save_run
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def execute():
 out=ROOT/'artifacts/temporal-progress-20261023'
 if out.exists():raise ValueError('Output must be new')
 source=ROOT/'artifacts/cross-sentence-20261023';old=ROOT/'artifacts/cross-sentence-final-20261023'
 for base in (source,old):
  m=read(base/'experiment-manifest.json')
  for name,h in m['files'].items():assert sha(base/name)==h
 code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')};code['scripts/run_temporal_progress_check.py']=sha(__file__)
 write(out/'execution-plan.json',dict(scope='same_development_documents_and_machine_annotations',model_requests=0,label_access=False,independent_evaluation=False,empirical_calibration=False,source_manifest_sha256=sha(source/'experiment-manifest.json'),code_sha256=code))
 rows=[];runs=[];parity=0;wide=[]
 for market in ('1171663','1423716','2354063'):
  for arm in ('head','fact_window_v1'):
   inp=source/f'inputs/{market}/{arm}';t=read(inp/'task.json');docs=read(inp/'documents.json');anns=read(inp/'annotations.json')
   cfg=Config.from_dict(read(source/f'runs/{market}/{arm}/patent_elements_v2/result.json')['config'])
   for name,value in [('task',t),('documents',docs),('annotations',anns)]:write(out/f'inputs/{market}/{arm}/{name}.json',value)
   for d in docs:
    row=dict(market_id=market,arm=arm,document_id=d['id'],title=d.get('title'),policies={})
    for policy in ('patent_elements_v3','patent_elements_v4'):
     ev=extract(d,t,anns,evidence_policy=policy);entry={k:ev[k] for k in ('elements','relevance','support','quote','patent_evidence_trace')};entry['admitted']=ev['relevance']>=cfg.admission;row['policies'][policy]=entry
    rows.append(row)
   for policy in ('patent_elements_v3','patent_elements_v4'):
    result=run(t,docs,cfg,anns,evidence_policy=policy,budget_policy='patent_budget_v1',grid_policy={'version':'patent_grid_v1','cap_fraction':.31,'width_fraction':.5},retrieval_policy='bm25_read_guard_v1',decision_trace=True)
    if policy=='patent_elements_v3':
     assert result==read(old/f'runs/{market}/{arm}/{policy}/result.json');parity+=1
    folder=out/f'runs/{market}/{arm}/{policy}';save_run(result,folder)
    for name,value in [('task',t),('documents',docs),('annotations',anns)]:write(folder/f'inputs/{name}.json',value)
    m=read(folder/'manifest.json');m['files'].update({p.relative_to(folder).as_posix():sha(p) for p in (folder/'inputs').iterdir()});write(folder/'manifest.json',m)
    runs.append(dict(market_id=market,arm=arm,policy=policy,result=result['result'],admitted=result['diagnostics']['admitted_documents']))
  # All original development documents; no new sampling, model requests or labels.
  original=ROOT/f'artifacts/semantics-v2-final-20261023/runs/{market}/enhanced/inputs'
  t=read(original/'task.json');docs=read(original/'documents.json');anns=read(original/'annotations.json')
  for d in docs:
   row=dict(market_id=market,document_id=d['id'],policies={})
   for policy in ('patent_elements_v3','patent_elements_v4'):
    ev=extract(d,t,anns,evidence_policy=policy);row['policies'][policy]=dict(admitted=ev['relevance']>=cfg.admission,support=ev['support'],elements=ev['elements'],trace=ev['patent_evidence_trace'])
   wide.append(row)
  for f in (ROOT/f'artifacts/semantics-v2-final-20261023/runs/{market}').glob('*/result.json'):
   prior=read(f);p=prior['provenance'];i=f.parent/'inputs'
   assert run(read(i/'task.json'),read(i/'documents.json'),Config.from_dict(prior['config']),read(i/'annotations.json'),evidence_policy=p.get('evidence_policy'),budget_policy=p.get('budget_policy'),grid_policy=p.get('grid_policy'),retrieval_policy=p.get('retrieval_policy'))==prior
   parity+=1
 totals=[]
 for arm in ('head','fact_window_v1'):
  for policy in ('patent_elements_v3','patent_elements_v4'):
   xs=[r['policies'][policy] for r in rows if r['arm']==arm]
   totals.append(dict(arm=arm,policy=policy,documents=len(xs),admitted=sum(x['admitted'] for x in xs),directional=sum(any(x['support']) for x in xs),admitted_directional=sum(x['admitted'] and any(x['support']) for x in xs)))
 wide_totals=[]
 for policy in ('patent_elements_v3','patent_elements_v4'):
  xs=[r['policies'][policy] for r in wide]
  wide_totals.append(dict(policy=policy,documents=len(xs),admitted=sum(x['admitted'] for x in xs),directional=sum(any(x['support']) for x in xs),admitted_directional=sum(x['admitted'] and any(x['support']) for x in xs)))
 blocks=Counter(b for row in rows if row['arm']=='head' for b in row['policies']['patent_elements_v4']['patent_evidence_trace']['support']['blockers'])
 write(out/'documents.json',rows);write(out/'existing-development-diagnostics.json',wide)
 summary=dict(status='completed_development_replay',totals=totals,existing_development_totals=wide_totals,head_blockers=dict(blocks),runs=runs,legacy_parity_runs=parity,model_requests=0,independent_evaluation=False,empirical_calibration=False,calibration_gate='not_ready_no_admitted_directional_real_documents',limitations=['purposively_selected_known_cases','finite_english_grammar','no_new_fact_dates_imputed','no_model_calls','no_prediction_accuracy_labels','uncalibrated_progress_compatibility_rules'])
 write(out/'summary.json',summary)
 for name,h in code.items():assert sha(ROOT/name)==h
 write(out/'experiment-manifest.json',dict(artifact_type='temporal_progress_development_replay',code_sha256=code,files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
 print(json.dumps({k:summary[k] for k in ('status','totals','existing_development_totals','legacy_parity_runs','model_requests')},ensure_ascii=False))
if __name__=='__main__':execute()
