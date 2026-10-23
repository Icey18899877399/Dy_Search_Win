"""Bounded read-only source-gap audit; no labels, model calls, or input replacement."""
from pathlib import Path
import argparse, hashlib, json, re, sqlite3, sys, zlib
from collections import Counter, defaultdict
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.source_history import historical_body_candidate, VERSION
from dynamic_retrieval.fact_coverage import inspect_document, fact_window_context
from dynamic_retrieval.patent_evidence_v4 import effective_task
from dynamic_retrieval.evidence import prepare_task
from dynamic_retrieval.data.store import utc_iso


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def unpack(row):
    d=dict(row); d['text']=zlib.decompress(d.pop('payload')).decode('utf8')
    if sha_text(d['text'])!=d['content_hash']: raise ValueError('Indexed body hash mismatch')
    return d

def sha_text(text): return hashlib.sha256(text.encode('utf8')).hexdigest()

def witnesses(body):
    # Date and metric mentions only: roles are deliberately not inferred here.
    patterns={'full_date_mention': r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2},? 2026\b|\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) 2026\b',
        'relative_day':r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
        'specified_counter_mention':r'\bXTracker\b|\bPost Counter\b|xtracker\.polymarket\.com',
        'numeric_post_count_mention':r'\b\d[\d,]*\s+(?:posts?|tweets?)\b'}
    rows=[]
    for kind,pattern in patterns.items():
        for m in re.finditer(pattern,body,re.I):
            a=max(0,m.start()-160); b=min(len(body),m.end()+220)
            rows.append(dict(kind=kind,start=m.start(),end=m.end(),text=m[0],context_start=a,context_end=b,context=body[a:b],role='unresolved_mention_not_event_fact'))
    return rows

def load_visible_versions(con,task):
    cutoff=utc_iso(task['cutoff'])
    # Preserve substantive corrections even when their scraper status is failed.
    # Scope is all indexed text bodies; empty observations have no recoverable body.
    query='''SELECT d.*,b.payload FROM (
      SELECT *, ROW_NUMBER() OVER(PARTITION BY canonical_url,content_hash ORDER BY observed_at DESC,id ASC) AS rn
      FROM documents WHERE event_id=? AND observed_at<=? AND published_at<=? AND has_text=1
    ) d JOIN bodies b ON b.content_hash=d.content_hash WHERE rn=1 ORDER BY canonical_url,observed_at DESC,id'''
    return [unpack(row) for row in con.execute(query,(task['event_id'],cutoff,cutoff))]

def execute(out):
    if out.exists() or not out.is_relative_to(ROOT/'artifacts'): raise ValueError('New artifact directory required')
    baseline=ROOT/'artifacts/fact-coverage-20261023'
    bm=read(baseline/'experiment-manifest.json')
    for name,h in bm['files'].items():
        if sha(baseline/name)!=h: raise ValueError('Baseline file mismatch: '+name)
    code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}
    code[Path(__file__).relative_to(ROOT).as_posix()]=sha(__file__)
    con=sqlite3.connect((ROOT/'artifacts/index.sqlite').as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    meta=dict(con.execute("SELECT key,value FROM meta WHERE key IN ('data_root','audit')"))
    data=Path(meta['data_root']).resolve()
    if data!=Path('D:/agents-main/agents/polymarket/data').resolve(): raise ValueError('Unexpected data root')
    audit=json.loads(meta['audit']); expected={x['path']:x.get('sha256') for x in audit['source_manifest']}
    source_names=set(); records=[]; recovered=[]; inventories=[]
    write(out/'execution-plan.json',dict(version=VERSION,code_sha256=code,baseline_manifest_sha256=sha(baseline/'experiment-manifest.json'),
        model_requests=0,label_access=False,scope='known_development_tasks_historical_body_coverage',
        history_scope='Both clocks at or before original cutoff; has_text=1; all scrape statuses including failures; latest observed record per URL+body hash; same event',
        counter_scope='Cross-event title matches Musk AND tweet/post, both clocks <= original count cutoff, has_text=1; distinct body hashes',
        default_selector_changed=False,prediction_input_replaced=False,independent_evaluation=False,empirical_calibration=False))
    for market in ('1171663','1423716','2354063'):
        task=read(baseline/f'inputs/{market}/task.json'); cutoff=utc_iso(task['cutoff'])
        docs=load_visible_versions(con,task)
        original=read(baseline/f'inputs/{market}/documents.json')
        prior={(d['canonical_url'],d['content_hash']) for d in original}
        source_names.add(task['source_file']); source_names.update(d['source_file'] for d in docs)
        write(out/f'inputs/{market}/task.json',task);write(out/f'inputs/{market}/versions.json',docs)
        groups=defaultdict(list)
        for d in docs: groups[d['canonical_url']].append(d)
        candidates=[]
        for url,versions in groups.items():
            selection=historical_body_candidate(task,versions)
            selected=selection.pop('document')
            if selection['status']=='historical_body_candidate':
                window=None
                try: window=fact_window_context(task,selected)
                except ValueError: pass
                item=dict(market_id=market,canonical_url=url,selection=selection,document=selected,window=window,
                          source_mentions=witnesses(selected['text']),model_requests=0,reviewed=False,is_outcome_label=False)
                candidates.append(item);recovered.append(item)
        coverage=[]
        for d in docs:
            row=inspect_document(task,d)
            row['additional_historical_body']=(d['canonical_url'],d['content_hash']) not in prior
            row['source_mentions']=witnesses(d['text'])
            coverage.append(row)
        write(out/f'coverage/{market}.json',coverage)
        c=effective_task(prepare_task(task))['_patent_contract'];desc=task['description']
        paragraphs=[]
        for m in re.finditer(r'\S(?:[^\n]|\n(?!\n))*',desc):
            paragraphs.append(dict(start=m.start(),end=m.end(),text=m[0],
                contract_witnesses=[w for w in c['condition_witnesses'] if m.start()<=w['start'] and w['end']<=m.end()],
                validation_status='full_clause_requires_semantic_check_even_when_keyword_witness_present'))
        inventory=dict(market_id=market,task_source_file=task['source_file'],task_observed_at=task['observed_at'],cutoff=task['cutoff'],
            description_sha256=sha_text(desc),description=desc,paragraphs=paragraphs,contract=c,
            coverage_claim='all_nonblank_description_paragraphs_preserved_not_all_conditions_implemented',reviewed=False)
        assert ''.join(x['text'] for x in paragraphs).replace('\n','').replace(' ','')==desc.replace('\n','').replace(' ','')
        inventories.append(inventory)
        summary=dict(market_id=market,latest_bodies=len(original),visible_url_body_versions=len(docs),
            additional_historical_bodies=sum(r['additional_historical_body'] for r in coverage),
            recovered_urls=len(candidates),prepared_recovered_windows=sum(x['window'] is not None for x in candidates),
            candidate_passages=sum(len(r['passages']) for r in coverage),
            additional_historical_candidate_passages=sum(len(r['passages']) for r in coverage if r['additional_historical_body']),
            lexical_counter_mention_bodies=sum(any(x['kind']=='specified_counter_mention' for x in r['source_mentions']) for r in coverage))
        records.append(summary);print(json.dumps(summary),flush=True)
    task=read(baseline/'inputs/1423716/task.json');cutoff=utc_iso(task['cutoff'])
    query='''SELECT d.*,b.payload FROM (
       SELECT *,ROW_NUMBER() OVER(PARTITION BY content_hash ORDER BY observed_at DESC,id ASC) AS rn FROM documents
       WHERE lower(title) LIKE '%musk%' AND (lower(title) LIKE '%tweet%' OR lower(title) LIKE '%post%')
       AND observed_at<=? AND published_at<=? AND has_text=1
    ) d JOIN bodies b ON b.content_hash=d.content_hash WHERE rn=1 ORDER BY id'''
    cross=[unpack(row) for row in con.execute(query,(cutoff,cutoff))]
    cross_rows=[]
    for d in cross:
        source_names.add(d['source_file']);r=inspect_document(task,d)
        r['source_mentions']=witnesses(d['text']);r['scope']='cross_event_discovery_only_not_prediction_input'
        cross_rows.append(r)
    tracker_urls=con.execute("SELECT count(DISTINCT canonical_url) FROM documents WHERE lower(canonical_url) LIKE '%xtracker%'").fetchone()[0]
    con.close()
    write(out/'inputs/counter-cross-event.json',cross);write(out/'coverage/counter-cross-event.json',cross_rows)
    write(out/'recovered-candidates.json',recovered);write(out/'task-condition-inventory.json',inventories)
    sources={}
    for name in sorted(source_names):
        path=(data/name).resolve()
        if not path.is_relative_to(data) or 'ground_truth' in path.parts:raise ValueError('Unsafe raw source')
        digest=sha(path)
        if digest!=expected.get(name):raise ValueError('Raw source hash mismatch: '+name)
        sources[name]=digest
    for name,h in code.items():
        if sha(ROOT/name)!=h:raise ValueError('Code changed during audit')
    summary=dict(status='completed_bounded_development_source_audit',version=VERSION,records=records,
        latest_bodies=sum(r['latest_bodies'] for r in records),visible_url_body_versions=sum(r['visible_url_body_versions'] for r in records),
        additional_historical_bodies=sum(r['additional_historical_bodies'] for r in records),recovered_urls=len(recovered),
        cross_event_count_title_bodies=len(cross),cross_event_counter_mention_bodies=sum(any(m['kind']=='specified_counter_mention' for m in r['source_mentions']) for r in cross_rows),
        indexed_xtracker_canonical_urls=tracker_urls,raw_source_files_verified=len(sources),index_source_read_failures=audit['source_read_failures'],
        model_requests=0,prediction_input_replaced=False,independent_evaluation=False,empirical_calibration=False,
        limitations=['Same three previously inspected development tasks; URL/body versions are not independent facts.',
        'Finite passage selector and lexical date/counter mentions are not full semantic extraction.',
        'Historical body recovery establishes past availability, not latest substantive correctness.',
        'No event dates imputed from publication, captions, weekdays, or effective-start dates.',
        'Cross-event title screening is bounded; zero matched source URLs does not prove global absence.',
        'No fresh model extraction or predictive accuracy evaluation; original model inputs and defaults unchanged.'])
    write(out/'summary.json',summary)
    write(out/'experiment-manifest.json',dict(artifact_type='source_gap_audit',code_sha256=code,raw_sources_sha256=sources,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    execute(p.parse_args().output.resolve())
