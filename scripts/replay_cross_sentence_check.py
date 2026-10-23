"""Re-evaluate frozen model annotations after review; never imports an API client."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from run_cross_sentence_check import read,write,sha
from dynamic_retrieval.evidence import extract
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.cli import save_run

def execute(out):
 source=ROOT/'artifacts/cross-sentence-20261023'
 if out.exists():raise ValueError('New output required')
 m=read(source/'experiment-manifest.json')
 for name,h in m['files'].items():assert sha(source/name)==h
 code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')};code['scripts/replay_cross_sentence_check.py']=sha(__file__)
 write(out/'execution-plan.json',dict(source_manifest_sha256=sha(source/'experiment-manifest.json'),scope='same_frozen_machine_annotations_review_fixes',model_requests=0,independent_evaluation=False,code_sha256=code))
 rows=[];runs=[];totals=[];parity=0
 for market in ('1171663','1423716','2354063'):
  for arm in ('head','fact_window_v1'):
   inp=source/f'inputs/{market}/{arm}';task=read(inp/'task.json');docs=read(inp/'documents.json');anns=read(inp/'annotations.json')
   for name,value in [('task',task),('documents',docs),('annotations',anns)]:write(out/f'inputs/{market}/{arm}/{name}.json',value)
   cfg=Config.from_dict(read(source/f'runs/{market}/{arm}/patent_elements_v2/result.json')['config'])
   for d in docs:
    row=dict(market_id=market,arm=arm,document_id=d['id'],policies={})
    for policy in ('patent_elements_v2','patent_elements_v3'):
     ev=extract(d,task,anns,evidence_policy=policy);row['policies'][policy]={k:ev[k] for k in ('elements','relevance','support','quote','patent_evidence_trace')};row['policies'][policy]['admitted']=ev['relevance']>=cfg.admission
    rows.append(row)
   for policy in ('patent_elements_v2','patent_elements_v3'):
    result=run(task,docs,cfg,anns,evidence_policy=policy,budget_policy='patent_budget_v1',grid_policy={'version':'patent_grid_v1','cap_fraction':.31,'width_fraction':.5},retrieval_policy='bm25_read_guard_v1',decision_trace=True)
    folder=out/f'runs/{market}/{arm}/{policy}';save_run(result,folder)
    for name,value in [('task',task),('documents',docs),('annotations',anns)]:write(folder/f'inputs/{name}.json',value)
    manifest=read(folder/'manifest.json');manifest['files'].update({p.relative_to(folder).as_posix():sha(p) for p in (folder/'inputs').iterdir()});write(folder/'manifest.json',manifest)
    runs.append(dict(market_id=market,arm=arm,policy=policy,result_path=folder.relative_to(out).as_posix()+'/result.json',result=result['result'],admitted=result['diagnostics']['admitted_documents']))
  for path in (ROOT/f'artifacts/semantics-v2-final-20261023/runs/{market}').glob('*/result.json'):
   old=read(path);p=old['provenance'];inp=path.parent/'inputs'
   assert run(read(inp/'task.json'),read(inp/'documents.json'),Config.from_dict(old['config']),read(inp/'annotations.json'),evidence_policy=p.get('evidence_policy'),budget_policy=p.get('budget_policy'),grid_policy=p.get('grid_policy'),retrieval_policy=p.get('retrieval_policy'))==old
   parity+=1
 for arm in ('head','fact_window_v1'):
  for policy in ('patent_elements_v2','patent_elements_v3'):
   xs=[r['policies'][policy] for r in rows if r['arm']==arm];totals.append(dict(arm=arm,policy=policy,documents=len(xs),admitted=sum(x['admitted'] for x in xs),directional=sum(any(x['support']) for x in xs)))
 write(out/'documents.json',rows);summary=dict(status='completed_frozen_annotation_replay',model_requests=0,source_model_requests=14,totals=totals,runs=runs,legacy_parity_runs=parity,independent_evaluation=False,empirical_calibration=False)
 write(out/'summary.json',summary)
 for name,h in code.items():assert sha(ROOT/name)==h
 write(out/'experiment-manifest.json',dict(artifact_type='cross_sentence_reviewed_development_replay',code_sha256=code,files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
 print(summary['totals'])
if __name__=='__main__':execute(ROOT/'artifacts/cross-sentence-final-20261023')
