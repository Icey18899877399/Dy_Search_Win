"""Freeze and audit full point-in-time corpora for the three development tasks."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.data.store import Store,utc_iso
from dynamic_retrieval.fact_coverage import inspect_document,VERSION
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def execute(output):
 if output.exists() or not output.is_relative_to(ROOT/'artifacts'):raise ValueError('Use a new project artifact directory')
 old=ROOT/'artifacts/semantics-v2-final-20261023';oldmanifest=read(old/'experiment-manifest.json')
 data=Path('D:/agents-main/agents/polymarket/data').resolve();frozen=[];sources={};code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')};code[Path(__file__).relative_to(ROOT).as_posix()]=sha(__file__)
 with Store(ROOT/'artifacts/index.sqlite') as store:
  meta=dict(store.connection.execute("SELECT key,value FROM meta WHERE key IN ('audit','data_root')"));assert Path(meta['data_root']).resolve()==data
  audit=json.loads(meta['audit']);expected={x['path']:x.get('sha256') for x in audit['source_manifest']}
  for market in ['1171663','1423716','2354063']:
   base=old/'runs'/market/'enhanced';task=read(base/'inputs/task.json');assert sha(base/'inputs/task.json')==oldmanifest['files'][(base/'inputs/task.json').relative_to(old).as_posix()]
   docs=store.documents(task['event_id'],task['cutoff']);previous=read(base/'inputs/documents.json');oldbodies={(d['canonical_url'],hashlib.sha256(d['text'].encode()).hexdigest()) for d in previous}
   cut=utc_iso(task['cutoff']);first={}
   for row in store.connection.execute('SELECT canonical_url,content_hash,observed_at,source_file FROM documents WHERE event_id=? AND observed_at<=? AND published_at<=? AND has_text=1 ORDER BY observed_at,id',(task['event_id'],cut,cut)):
    first.setdefault((row['canonical_url'],row['content_hash']),dict(first_observed_at=row['observed_at'],first_source_file=row['source_file']))
   count=store.connection.execute('SELECT count(*),count(DISTINCT canonical_url) FROM documents WHERE event_id=? AND observed_at<=? AND published_at<=?',(task['event_id'],cut,cut)).fetchone()
   for rel in {task['source_file']}|{d['source_file'] for d in docs}|{first[(d['canonical_url'],d['content_hash'])]['first_source_file'] for d in docs}:
    if rel in sources:continue
    p=(data/rel).resolve()
    if not p.is_relative_to(data) or 'ground_truth' in p.parts:raise ValueError('Unsafe raw source')
    digest=sha(p)
    if digest!=expected.get(rel):raise ValueError('Raw source hash mismatch: '+rel)
    sources[rel]=digest
   frozen.append((market,task,docs,oldbodies,first,dict(index_rows=count[0],index_unique_urls=count[1],unique_url_body_versions=len(first))))
 write(output/'execution-plan.json',dict(version=VERSION,scope='previously_inspected_event_development_only',model_requests=0,label_access=False,independent_evaluation=False,
  tasks=[dict(market_id=m,event_id=t['event_id'],cutoff=t['cutoff']) for m,t,*_ in frozen],document_selection='Store latest visible successful text per event+URL; publication and body observation <= unchanged cutoff',
  raw_sources_sha256=sources,code_sha256=code,max_passages_per_document=8,max_selected_chars=12000,full_body_scan=True,
  historical_versions_scanned=False,index_source_read_failures=audit['source_read_failures'],no_absence_claim=True))
 records=[];parity=0
 for market,task,docs,oldbodies,first,pool in frozen:
  write(output/'inputs'/market/'task.json',task);write(output/'inputs'/market/'documents.json',docs)
  rows=[]
  for d in docs:
   row=inspect_document(task,d);row.update(first[(d['canonical_url'],d['content_hash'])]);row['previously_frozen_60_body']=(d['canonical_url'],d['content_hash']) in oldbodies;rows.append(row)
  write(output/'coverage'/market/'documents.json',rows)
  for path in sorted((old/'runs'/market).glob('*/result.json')):
   assert sha(path)==oldmanifest['files'][path.relative_to(old).as_posix()]
   original=read(path);p=original['provenance'];inp=path.parent/'inputs'
   actual=run(read(inp/'task.json'),read(inp/'documents.json'),Config.from_dict(original['config']),read(inp/'annotations.json'),evidence_policy=p.get('evidence_policy'),comparison_policy=p.get('comparison_policy'),budget_policy=p.get('budget_policy'),grid_policy=p.get('grid_policy'),retrieval_policy=p.get('retrieval_policy'))
   assert actual==original,'Historical output changed';parity+=1
  summary=dict(market_id=market,event_id=task['event_id'],cutoff=task['cutoff'],documents=len(rows),body_chars=sum(r['body_chars'] for r in rows),pool=pool,
   previously_frozen_bodies=sum(r['previously_frozen_60_body'] for r in rows),documents_with_candidate_passages=sum(bool(r['passages']) for r in rows),
   selected_passages=sum(len(r['passages']) for r in rows),passages_after_default_head=sum(p['after_default_12000_head'] for r in rows for p in r['passages']),
   source_quality_blockers=dict(Counter(b for r in rows for b in r['source_quality']['blockers'])),
   diagnostic_signals=dict(Counter(tag for r in rows for p in r['passages'] for tag in p['signals'])),
   v2_directional_candidates=sum(r['directional_candidates'] for r in rows),
   v2_blockers=dict(Counter(b for r in rows for p in r['passages'] for b in p['v2_blockers'])))
  records.append(summary);print(json.dumps({k:summary[k] for k in ('market_id','documents','documents_with_candidate_passages','selected_passages','passages_after_default_head','source_quality_blockers','v2_directional_candidates')},ensure_ascii=False),flush=True)
 for name,digest in code.items():assert sha(ROOT/name)==digest
 for name,digest in sources.items():assert sha(data/name)==digest
 summary=dict(status='completed_bounded_development_coverage_audit',version=VERSION,events=3,documents=sum(r['documents'] for r in records),records=records,legacy_parity_runs=parity,
  model_requests=0,label_access=False,independent_evaluation=False,empirical_calibration=False,raw_source_files_verified=len(sources),source_read_failures_in_index=audit['source_read_failures'],
  limits=['Latest visible body per event URL only; earlier overwritten versions not searched.','Finite cue/actor selectors with at most eight candidates per document are not exhaustive semantic review.','No candidate or zero directional output proves an outcome or absence of useful facts.','Source quality flags are diagnostic and not a replacement patent admission gate.'])
 write(output/'summary.json',summary)
 write(output/'experiment-manifest.json',dict(artifact_type='fact_coverage_audit',code_sha256=code,raw_sources_sha256=sources,files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}))
 print(json.dumps(dict(status=summary['status'],documents=summary['documents'],raw_source_files_verified=len(sources),legacy_parity_runs=parity)),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);execute(p.parse_args().output.resolve())
