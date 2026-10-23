"""Development-only source and passage coverage audit; never adjudicates outcomes.

Selectors search the full body and preserve contiguous original offsets. They
are diagnostic candidates, not an alternative admission/support policy. V2 is
queried unchanged; independent evaluation, model calls and labels are absent.
"""
from datetime import datetime
import hashlib
import re
from . import patent_evidence_v2 as v2
from .evidence import prepare_task
from .data.store import utc_iso

VERSION='fact_coverage_v1'
OVERSIZED_BODY=200000

def _patterns(task):
    c=v2.effective_task(prepare_task(task))['_patent_contract'];kind=c['kind']
    if kind=='knesset_dissolution':
        return kind,re.compile(r'\b(?:Knesset|Israeli parliament|Israel[’\']s parliament)\b',re.I),re.compile(r'\bdissolv\w*|\bdissolution\b',re.I)
    if kind=='bilateral_ceasefire':
        participants=c['participants'];return kind,re.compile('|'.join(v2._entity_pattern(p) for p in participants),re.I),re.compile(r'\b(?:ceasefire|cease fire|truce|halt.{0,25}(?:fighting|hostilities|military))\b',re.I)
    if kind=='publisher_monthly_count':
        return kind,re.compile(v2._entity_pattern(c['participants'][0])+r'|\bMusk\b',re.I),re.compile(r'\b(?:XTracker|Post Counter|posts?|tweets?)\b',re.I)
    raise ValueError('Fact coverage requires one of the three explicit v2 task families')

def _signals(text,kind):
    signals=[]
    for label,pattern in [
        ('procedural',r'preliminary|initial approval|first reading|second reading|bill.{0,25}(?:introduced|submitted)|submitted.{0,20}bill|still.{0,30}(?:approval|reading)'),
        ('counting_source',r'XTracker|Post Counter'),
        ('numeric_count_candidate',r'\b\d[\d,]*\s+(?:posts?|tweets?)\b'),
        ('terminal_wording',r'was dissolved|has been dissolved|final total|finalized|mutually agreed|both.{0,20}agreed'),
        ('temporary_or_scope_question',r'\bEaster\b|\b\d+-hour\b|humanitarian|energy infrastructure|Black Sea'),
        ('future_or_conditional',r'\b(?:if|could|might|will|expected|would)\b'),
        ('explicit_date_candidate',v2.DATE_PATTERN),
    ]:
        if re.search(pattern,text,re.I):signals.append(label)
    return signals

def select_passages(task,text,*,max_passages=8,max_chars=12000):
    if type(max_passages) is not int or max_passages<1 or type(max_chars) is not int or max_chars<1:raise ValueError('Positive passage limits required')
    kind,actors,cues=_patterns(task);text=str(text);candidates=[]
    # Enumerate cue-local windows across the complete body, including long,
    # scraped paragraphs. Context is never concatenated across a gap.
    for match in cues.finditer(text):
        a=max(0,match.start()-420);b=min(len(text),match.end()+700)
        left=text.rfind('\n',a,match.start());right=text.find('\n',match.end(),b)
        if left>=0:a=left+1
        if right>=0:b=right
        if b-a<120:
            a=max(0,match.start()-420);b=min(len(text),match.end()+700)
        raw=text[a:b];lead=len(raw)-len(raw.lstrip());tail=len(raw.rstrip());a+=lead;b=a+tail-lead
        content=text[a:b]
        if not actors.search(content) and not(kind=='publisher_monthly_count' and re.search(r'XTracker|Post Counter',content,re.I)):continue
        signals=_signals(content,kind)
        score=3*len(actors.findall(content))+2*len(cues.findall(content))+sum(4 for tag in signals if tag in ('counting_source','terminal_wording','explicit_date_candidate'))
        candidates.append(dict(start=a,end=b,text=content,signals=signals,rank_score=score,scope='contiguous_original_body',after_default_12000_head=a>=12000))
    selected=[];seen=set();spent=0
    for p in sorted(candidates,key=lambda x:(-x['rank_score'],x['start'],x['end'])):
        if p['text'] in seen or any(min(p['end'],q['end'])-max(p['start'],q['start'])>0 for q in selected):continue
        if spent+len(p['text'])>max_chars:continue
        selected.append(p);seen.add(p['text']);spent+=len(p['text'])
        if len(selected)>=max_passages:break
    return sorted(selected,key=lambda x:x['start'])

def _source_record(task,document,*,max_passages=8,max_chars=12000):
    body=str(document.get('text',''));digest=hashlib.sha256(body.encode('utf-8')).hexdigest()
    if document.get('content_hash') and document['content_hash']!=digest:raise ValueError('Body content hash mismatch')
    row={key:document.get(key) for key in ('id','event_id','title','canonical_url','source_id','source_file','published_at','observed_at')}
    row.update(version=VERSION,body_sha256=digest,body_chars=len(body),human_reviewed=False,eligible=False,eligibility_blockers=[],passages=[],directional_candidates=0,
        selection_scope='diagnostic_only_not_prediction_input',selection_limits=dict(max_passages=max_passages,max_chars=max_chars),absence_is_not_proof=True)
    for key in ('published_at','observed_at'):
        try:
            if utc_iso(document.get(key))>utc_iso(task['cutoff']):row['eligibility_blockers'].append(key+'_after_cutoff')
        except (ValueError,KeyError,TypeError):row['eligibility_blockers'].append(key+'_invalid')
    blockers=[]
    without_urls=re.sub(r'https?://\S+','',body).strip()
    if not body.strip():blockers.append('empty_body')
    elif len(without_urls)<120 and re.search(r'wayback machine|web\.archive\.org',body,re.I):blockers.append('archive_wrapper_only')
    elif len(body)<600 and re.search(r'^\s*(?:access denied|just a moment|enable javascript|verify you are human)',body,re.I):blockers.append('access_page_only')
    if len(body)>OVERSIZED_BODY:blockers.append('oversized_body_attribution_unresolved')
    if re.search(r'fail|error',str(document.get('scrape_status','')),re.I):blockers.append('failed_scrape_status')
    row['source_quality']=dict(blockers=blockers,thresholds={'oversized_body_chars':OVERSIZED_BODY},truth_verified=False)
    row['eligible']=not row['eligibility_blockers']
    return row

def inspect_document(task,document,*,max_passages=8,max_chars=12000):
    row=_source_record(task,document,max_passages=max_passages,max_chars=max_chars)
    blockers=row['source_quality']['blockers'];body=str(document.get('text',''));digest=row['body_sha256']
    if not row['eligible'] or any(b!='oversized_body_attribution_unresolved' for b in blockers):return row
    kind,_,cue=_patterns(task)
    row['full_body_cue_matches']=len(list(cue.finditer(body)))
    task=prepare_task(task);text=str(document.get('title',''))+'\n'+body
    for p in select_passages(task,body,max_passages=max_passages,max_chars=max_chars):
        p=dict(p,source_body_sha256=digest,human_reviewed=False)
        if blockers:
            p.update(v2_support=None,v2_relevance=None,v2_blockers=blockers,classification='unattributed_candidate_not_evaluated')
        else:
            e,r,s,trace=v2.evaluate({},task,quote=p['text'],text=text,original_support=[0,0])
            p.update(v2_elements=e,v2_support=s,v2_relevance=r,v2_blockers=trace['support']['blockers'],v2_assertion=trace['normalization'].get('assertion'),classification='candidate_only_not_adjudicated')
            row['directional_candidates']+=int(any(s))
        row['passages'].append(p)
    row['selected_chars']=sum(len(p['text']) for p in row['passages'])
    return row

def fact_window_context(task,document,max_chars=12000):
    """One original contiguous model window, opt-in and version-bound."""
    if type(max_chars) is not int or not 1<=max_chars<=12000:raise ValueError('Fact window limit must be 1..12000')
    # Diagnostics never steer by model direction; ranking uses lexical signals only.
    if task.get('observed_at') is not None and utc_iso(task['observed_at'])>utc_iso(task['cutoff']):raise ValueError('Task definition is after cutoff')
    checked=_source_record(task,document,max_passages=1,max_chars=12000)
    if not checked['eligible'] or checked['source_quality']['blockers']:raise ValueError('Fact window source is not eligible or attributable')
    full=str(document.get('title',''))+'\n'+str(document.get('text',''))
    base=len(str(document.get('title','')))+1
    candidates=select_passages(task,str(document.get('text','')),max_passages=1,max_chars=12000)
    start=0
    if candidates:
        focus=base+candidates[0]['start'];start=max(0,min(focus-max_chars//3,len(full)-max_chars))
    end=min(len(full),start+max_chars)
    return dict(id=str(document['id']),excerpt=full[start:end],context_policy='fact_window_v1',excerpt_start=start,excerpt_end=end,
                selector_max_chars=max_chars,context_source_sha256=hashlib.sha256(full.encode('utf-8')).hexdigest())
