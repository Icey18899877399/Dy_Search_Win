"""Bounded, source-bound contracts for three event families; legacy fallback.

Admission remains exact element-overlap. Outcome rules never consume model
support. No wall-clock, publication-date substitution, or fuzzy fact merging.
All patterns are finite English assertion grammars, not an open-world verifier.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import calendar
import re
from . import patent_evidence as v1
from .core import ELEMENTS, fact_key
from .semantic import MARKET_ODDS

POLICY = 'patent_elements_v2'
MONTHS = '|'.join(calendar.month_name[1:])
DATE_PATTERN = r'(?:\d{4}-\d{2}-\d{2}|(?:'+MONTHS+r')\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{1,2}\s+(?:'+MONTHS+r')\s+\d{4})'
STAMP_PATTERN = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})'
DATES = re.compile(r'\b(?:'+STAMP_PATTERN+'|'+DATE_PATTERN+r')\b',re.I)
KNESS = r'(?:Israeli\s+(?:parliament|Knesset)|Israel[’\']s\s+parliament|(?:the\s+)?(?:\d+(?:st|nd|rd|th)\s+)?Knesset)'
CONFLICT = re.compile(r'\b(?:false|falsely|incorrect|untrue|not true|no evidence|denied|retracted|debunked|disputed|correction|corrected)\b',re.I)
UNCERTAIN = re.compile(r'\b(?:if|unless|could|might|would|will|shall|expected|scheduled|forecast\w*|predict\w*|projected|alleged|possibly|perhaps)\b',re.I)
STAGE = re.compile(r'\b(?:propos\w*|preliminary|first reading|second reading|draft|committee|plans?|talks?|discuss\w*|candidacy|candidate)\b',re.I)


def _clean(s):return v1._clean(s)
def _date(s):
    s=re.sub(r'(\d)(?:st|nd|rd|th)\b',r'\1',s,flags=re.I)
    for fmt in ('%Y-%m-%d','%B %d, %Y','%B %d %Y','%d %B %Y'):
        try:return datetime.strptime(s,fmt).date()
        except ValueError:pass
    return None


def _instant(s):
    try:
        d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return d if d.tzinfo else None
    except (ValueError,TypeError):return None


def _visible_description(task):
    cutoff=_instant(task.get('cutoff')); observed=_instant(task.get('observed_at'))
    visible=not(observed and cutoff and observed>cutoff)
    return str(task.get('description','')) if visible else '',visible


def _end_of_day(day,tz):
    # US Eastern civil-time rules since 2007; avoid OS-local timezone dependence.
    if tz=='America/New_York' and day.year>=2007:
        march=date(day.year,3,1);nov=date(day.year,11,1)
        start=march+timedelta(days=(6-march.weekday())%7+7)
        end=nov+timedelta(days=(6-nov.weekday())%7)
        offset=-4 if start<=day<end else -5
        return datetime.combine(day,time(23,59,59),timezone(timedelta(hours=offset)))
    if tz=='UTC':return datetime.combine(day,time(23,59,59),timezone.utc)
    return None


def _contract(task):
    q=str(task.get('question','')).strip().rstrip('?').strip()
    desc,visible=_visible_description(task)
    c=dict(version='patent_contract_v2',status='supported',kind=None,participants=[],action=None,
           deadline=None,count_metric=None,time_interval={'start':None,'end':None},
           source_witnesses=[dict(source='question',text=q)],description_cutoff_visible=visible,
           wallclock_year_inference=False,fallback_v1=False)
    cm=re.fullmatch(r'(?:Will\s+)?(.+?)\s+post\s+(\d+)\s*[-–]\s*(\d+)\s+(tweets?|posts?)\s+in\s+('+MONTHS+r')\s+(\d{4})',q,re.I)
    km=re.fullmatch(r'(?:Will\s+)?'+KNESS+r'\s+(?:be\s+)?dissolved\s+by\s+(.+)',q,re.I)
    bm=re.fullmatch(r'(?:Will\s+)?(.+?)\s+(?:x|and|&)\s+(.+?)\s+(?:reach\s+(?:a\s+)?)?ceasefire\s+by\s+(.+)',q,re.I)
    if cm:
        publisher,lo,hi,unit,month,year=cm.groups();monthnum=list(m.lower() for m in calendar.month_name).index(month.lower());year=int(year)
        begin=date(year,monthnum,1);end=date(year,monthnum,calendar.monthrange(year,monthnum)[1])
        tracker=bool(re.search(r'xtracker|Post Counter',desc,re.I))
        c.update(kind='publisher_monthly_count',participants=[_clean(publisher)],action='post',
                 time_interval=dict(start=begin.isoformat(),end=end.isoformat(),timezone='unspecified',granularity='closed_calendar_month'),
                 count_metric=dict(unit=_clean(unit),lower=int(lo),upper=int(hi),bounds='inclusive',
                    definition=desc,source='xtracker_post_counter' if tracker else 'explicit_monthly_post_total',
                    required_source_witness=tracker,definition_source='description' if desc else 'question'))
        if int(lo)>int(hi) or not tracker or not desc:c['status']='incomplete'
        c['target_elements']={'subject':_clean(publisher),'action':'post','object':f'{lo}-{hi} posts','time':f'{year:04d}-{monthnum:02d}'}
    elif km or bm:
        c['kind']='knesset_dissolution' if km else 'bilateral_ceasefire'
        c['participants']=['israeli parliament'] if km else [_clean(bm[1]),_clean(bm[2])]
        c['action']='dissolve' if km else 'agree ceasefire'
        rawdeadline=km[1] if km else bm[3]
        deadline=_date(rawdeadline);year_source='question'
        if deadline is None:
            md=re.fullmatch(r'('+MONTHS+r')\s+(\d{1,2})',rawdeadline,re.I)
            if md:
                dm=re.search(r'\b'+re.escape(md[1])+r'\s+'+md[2]+r',?\s+(\d{4})\b',desc,re.I)
                if dm:deadline=_date(rawdeadline+', '+dm[1]);year_source='description'
        tz='America/New_York' if re.search(r'\b(?:ET|EST|EDT)\b',desc) else 'UTC' if re.search(r'\bUTC\b',q+' '+desc) else 'unspecified'
        c['deadline']=dict(date=deadline.isoformat() if deadline else None,timezone=tz,year_source=year_source if deadline else None,
                           raw=rawdeadline,boundary='inclusive_end_of_day',time_source='description' if tz!='unspecified' else None)
        start=None
        if deadline:
            # Explicit inception interval wins; otherwise year cycle is conservative.
            start=date(deadline.year,1,1)
            rng=re.search(r'between\s+('+MONTHS+r')\s+(\d{1,2})(?:,?\s+(\d{4}))?\s+and',desc,re.I)
            if rng:start=_date(f'{rng[1]} {rng[2]}, {rng[3] or deadline.year}')
        c['time_interval']=dict(start=start.isoformat() if start else None,end=deadline.isoformat() if deadline else None,
                                cycle_source='description_interval' if deadline and re.search(r'between\s+',desc,re.I) else 'explicit_deadline_year')
        if deadline is None:c['status']='incomplete'
        if bm:
            c['agreement_conditions']=dict(public=True,mutual=True,general_halt=True,
                excluded_scopes=['humanitarian','energy infrastructure','Black Sea','informal'],
                agreement_before_effective_start_allowed=True,framework_requires_dated_halt=True,
                source='description' if desc else 'bounded_official_general_ceasefire_definition')
        target={'subject':c['participants'][0],'action':c['action']}
        if bm:target['object']=c['participants'][1]
        if deadline:target['time']=deadline.isoformat()
        c['target_elements']=target
    else:
        c.update(status='unsupported',kind='legacy_fallback',fallback_v1=True)
        return c
    if desc:c['source_witnesses'].append(dict(source='description',text=desc))
    if set(_clean(x) for x in task.get('outcomes',[]))!={'yes','no'}:c['status']='incomplete'
    return c


def effective_task(task):
    c=_contract(task)
    out=v1.effective_task(task) if c['fallback_v1'] else deepcopy(task)
    if not c['fallback_v1']:
        out['target_elements']=deepcopy(c['target_elements'])
        out['_patent_task_parse']=dict(status='supported_template' if c['status']=='supported' else 'incomplete_contract',kind=c['kind'],
            reason='Finite question and cutoff-visible description contract; no publication or wall-clock dates.')
    out['_patent_contract']=c
    return out


def validate_support_rules(task):
    c=_contract(task)
    if c['fallback_v1']:return v1.validate_support_rules(task)
    # Existing explicitly supplied support schemas are validated, never silently ignored.
    if 'support_rules' in task:v1.validate_support_rules(task)
    return [dict(id=c['kind']+'.'+name,requirements=deepcopy(c.get('target_elements',{})),
        assertion_pattern='finite_source_assertion_parser_v2',support={o:direction if _clean(o)=='yes' else -direction for o in task['outcomes']},reason=reason)
        for name,direction,reason in [('positive',1,'Completed compatible event or finalized in-range monthly total.'),
                                     ('negative',-1,'Explicit elapsed-deadline failure or finalized out-of-range monthly total.')]]


def _sentences(text):
    # Preserve offsets; common initials/month abbreviations are not boundaries.
    # Also recognize scraped joins such as "Thursday.The" without whitespace.
    start=0
    abbreviations={'mr','mrs','ms','dr','prof','sr','jr','jan','feb','mar','apr','jun','jul','aug','sep','sept','oct','nov','dec','st','vs','etc'}
    boundaries=list(re.finditer(r'[.!?](?=\s|[A-Z]|$)|\n+',text))
    for m in boundaries:
        if m.group()=='.':
            token=re.search(r'([A-Za-z.]+)$',text[:m.start()])
            word=token[1] if token else ''
            if word.casefold() in abbreviations or re.fullmatch(r'(?:[A-Z]\.)*[A-Z]',word):continue
        end=m.end();segment=text[start:end];left=len(segment)-len(segment.lstrip());right=len(segment.rstrip())
        if right>left:yield segment[left:right],start+left,start+right
        start=end
    segment=text[start:];left=len(segment)-len(segment.lstrip());right=len(segment.rstrip())
    if right>left:yield segment[left:right],start+left,start+right


def _entity_pattern(value):
    aliases={'russia':r'(?:Russia|Russian(?: Federation)?)','ukraine':r'(?:Ukraine|Ukrainian)',
             'israeli parliament':KNESS}
    return r'(?<!\w)'+aliases.get(value,re.escape(value))+r'(?!\w)'


def _has_entity(s,p):return re.search(_entity_pattern(p),s,re.I)


def _bind_quote(text,quote,c):
    quote=str(quote).strip()
    if not quote:return None
    pos=text.find(quote)
    if pos<0:return None
    end=pos+len(quote);candidates=[]
    for s,a,b in _sentences(text):
        if b<=pos or a>=end:continue
        score=sum(bool(_has_entity(s,p)) for p in c['participants'])
        action=bool(re.search(r'dissolv|dissolution|ceasefire|truce|post|tweet',s,re.I))
        candidates.append((score+int(action),-a,s,a,b))
    if not candidates:return None
    _,_,s,a,b=max(candidates)
    return dict(text=s,start=a,end=b,scope='complete_original_title_or_body_sentence',quote_bound=True,quote_span=[pos,end])


def _extract(assertion,c,raw):
    s=assertion['text'];kind=c['kind'];elements={};witness={};info=dict(stage='unresolved',count=None,explicit_negative=False,complete=False)
    def add(key,value,match):
        if match:
            elements[key]=_clean(value);a,b=match.span()
            witness[key]=[dict(text=match.group(),start=assertion['start']+a,end=assertion['start']+b,scope='original_title_and_body')]
    # Semicolon clauses keep unrelated denials from contaminating a completed claim.
    clauses=list(re.finditer(r'[^;]+',s));claim=next((m for m in clauses if any(_has_entity(m.group(),p) for p in c['participants']) and re.search(r'dissolv|dissolution|ceasefire|truce|post|tweet',m.group(),re.I)),None)
    clause=claim.group() if claim else s;offset=claim.start() if claim else 0
    info['clause']=clause
    for i,p in enumerate(c['participants']):
        if kind in ('publisher_monthly_count','bilateral_ceasefire'):continue
        match=_has_entity(clause,p)
        if match:
            # Re-find in full sentence to maintain exact witness offsets.
            add('subject' if i==0 else 'object',p,re.search(_entity_pattern(p),s[offset:offset+len(clause)],re.I))
            key='subject' if i==0 else 'object'
            for w in witness.get(key,[]):w['start']+=offset;w['end']+=offset
    # Bind actual grammatical participants, even when target entities are merely
    # mentioned elsewhere in this sentence. Preserve them in the exact fact key.
    actual=[]
    if kind=='bilateral_ceasefire':
        name=r'[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}'
        pair=re.search(r'(?P<first>'+name+r')\s+(?:and|&)\s+(?P<second>'+name+r')\s+(?i:(?:(?:publicly|officially|jointly|mutually)\s+)*(?:announced|agreed|signed|reached|held|proposed)|(?:had|have|has|did)\s+not\s+(?:yet\s+)?(?:reached|reach|agreed|signed))\b',clause)
        if pair:actual=[('subject',pair,'first'),('object',pair,'second')]
    elif kind=='publisher_monthly_count':
        publisher=re.search(r'Post Counter\s+for\s+(?P<person>[^,;]+?)\s+for\s+(?:the\s+)?(?:entire|whole|full)?\s*(?:month\s+of\s+)?(?:'+MONTHS+r')\b',clause,re.I)
        if publisher:actual=[('subject',publisher,'person')]
        else:
            name=r'[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}'
            ordinary=re.search(r'(?P<person>'+name+r')(?:\s+(?:posted|tweeted|published|wrote)\b|[’\']s\s+(?:new\s+)?(?:post|tweet)\b|\s+used\b[^;.!?]{0,160}\bto\s+post\b)',clause)
            if ordinary:actual=[('subject',ordinary,'person')]
        info['publisher_bound']=bool(actual)
    for key,match,group in actual:
        rawname=match.group(group);canonical=_clean(rawname)
        canonical={'russian':'russia','russian federation':'russia','ukrainian':'ukraine'}.get(canonical,canonical)
        elements[key]=canonical
        a,b=match.span(group)
        witness[key]=[dict(text=rawname,start=assertion['start']+offset+a,end=assertion['start']+offset+b,scope='original_title_and_body')]
    if kind=='knesset_dissolution':
        action=re.search(r'\b(?:dissolved|dissolve|dissolving|dissolution)\b',clause,re.I)
        neg=re.search(r'\b(?:had|has|was|is)\s+not\s+(?:yet\s+)?(?:been\s+)?dissolved\b|\bnever\s+(?:been\s+)?dissolved\b',clause,re.I)
        completed=re.search(KNESS+r'\s+(?:has been|had been|was|is)\s+(?:formally\s+|officially\s+)?dissolved\b|'+KNESS+r'\s+(?:formally\s+|officially\s+)?dissolved\s+itself\b',clause,re.I)
        stage=STAGE.search(clause)
        info.update(stage='negative' if neg else 'procedural' if stage else 'completed' if completed else 'mentioned',explicit_negative=bool(neg),complete=bool(completed))
        if action:add('action','not dissolved' if neg else ('dissolution '+_clean(stage.group())) if stage else 'dissolve' if completed else 'dissolution mentioned',re.search(action.re.pattern,s,re.I))
    elif kind=='bilateral_ceasefire':
        action=re.search(r'\b(?:ceasefire|truce)\b',clause,re.I)
        neg=re.search(r'\b(?:had|have|has|did)\s+not\s+(?:yet\s+)?(?:reached|reach|agreed|signed)\b|\bno\s+(?:official\s+)?ceasefire\s+agreement\s+(?:was|had been)\s+reached',clause,re.I)
        completed=re.search(r'\b(?:announced|agreed|signed|reached|entered into force|took effect)\b',clause,re.I)
        stage=STAGE.search(clause)
        info.update(stage='negative' if neg else 'procedural' if stage else 'completed' if completed else 'mentioned',explicit_negative=bool(neg),complete=bool(completed))
        if action:add('action','no ceasefire agreement' if neg else ('ceasefire '+_clean(stage.group())) if stage else 'agree ceasefire' if completed else 'ceasefire mentioned',re.search(action.re.pattern,s,re.I))
    else:
        action=re.search(r'\b(?:posted|posts?|tweets?|Post Counter)\b',clause,re.I)
        number=re.search(r'\b(\d[\d,]*)\s+(?:posts?|tweets?)\b',clause,re.I)
        if action and info.get('publisher_bound'):add('action','post',re.search(action.re.pattern,s,re.I))
        if number:
            info['count']=int(number[1].replace(',',''));add('object',f"{info['count']} posts",re.search(number.re.pattern,s,re.I))
        info.update(stage='count',complete=bool(re.search(r'\b(?:final|finalized|completed)\b',clause,re.I) and re.search(r'\b(?:entire|whole|full)\s+(?:calendar\s+)?month\b',clause,re.I)))
    # Only dates attached to this assertion, never publication dates/deadline defaults.
    ds=list(DATES.finditer(clause))
    selected=None
    for d in ds:
        prefix=clause[:d.start()]
        if kind=='knesset_dissolution':
            attachment=r'(?:dissolved(?:\s+itself)?|dissolution(?:\s+bill)?|bill|vote|reading)\s+(?:on|by|as of)\s*$'
        elif kind=='bilateral_ceasefire':
            attachment=r'(?:ceasefire(?:\s+agreement)?|truce|agreement|talks|proposal)\s+(?:on|by|as of)\s*$'
        else:
            attachment=r'(?:posts?|tweets?|posted(?:\s+a\s+(?:message|tweet|post))?|tweeted|published(?:\s+a\s+(?:message|tweet|post))?)\s+(?:on|by|as of)\s*$'
        attached=bool(re.search(attachment,prefix,re.I))
        leading=bool(re.fullmatch(r'\s*["“]?(?:On|By|As of)\s+',prefix,re.I))
        if not attached and not leading:continue
        if re.search(r'\bby\s*$',prefix,re.I) and not info['explicit_negative']:continue
        selected=d;break
    if selected:
        parsed=_date(selected.group());stamp=_instant(selected.group())
        if parsed or stamp:
            elements['time']=stamp.isoformat() if stamp else parsed.isoformat()
            witness['time']=[dict(text=selected.group(),start=assertion['start']+offset+selected.start(),end=assertion['start']+offset+selected.end(),scope='original_title_and_body')]
    elif kind=='publisher_monthly_count' and not ds:
        m=re.search(r'\b('+MONTHS+r')\s+(\d{4})\b',clause,re.I)
        if m:
            mn=list(x.lower() for x in calendar.month_name).index(m[1].lower());elements['time']=f'{int(m[2]):04d}-{mn:02d}'
            witness['time']=[dict(text=m.group(),start=assertion['start']+offset+m.start(),end=assertion['start']+offset+m.end(),scope='original_title_and_body')]
    # Grounded residual fields cannot borrow across sentences or replace parsed ones.
    for k,v in raw.items():
        if k!='location' or k in elements or not v:continue
        match=re.search(r'(?<!\w)'+re.escape(str(v))+r'(?!\w)',clause,re.I)
        if match:
            add(k,v,re.search(r'(?<!\w)'+re.escape(str(v))+r'(?!\w)',s,re.I))
    if kind=='bilateral_ceasefire' and not elements.get('action'):
        for key in ('subject','object'):
            elements.pop(key,None);witness.pop(key,None)
    # Denial and negation belong to the asserted action identity. They must
    # never borrow the exact fact group of the positive embedded proposition.
    qualifier=None
    if elements.get('action'):
        if CONFLICT.search(clause):qualifier='disputed'
        elif kind=='bilateral_ceasefire' and re.search(r'\b(?:not|never)\s+(?:(?:yet|mutually|officially)\s+)*(?:agreed|signed|reached|announced)\b',clause,re.I) and not info['explicit_negative']:
            qualifier='negated'
        elif kind=='publisher_monthly_count' and re.search(r'\b(?:was|were|is|had|has)\s+not\b|\bnot\s+\d',clause,re.I):qualifier='negated'
        if qualifier:
            elements['action']=qualifier+' '+elements['action']
            witness['action']=[dict(text=clause,start=assertion['start']+offset,end=assertion['start']+offset+len(clause),scope='original_title_and_body')]
    return elements,witness,info


def _same_claim_conflict(text,assertion,c,e):
    found=[]
    for s,a,b in _sentences(text):
        for clause in re.split(r';',s):
            if not CONFLICT.search(clause):continue
            entities=all(_has_entity(clause,p) for p in c['participants'])
            action=re.search(r'dissolv|dissolution',clause,re.I) if c['kind']=='knesset_dissolution' else re.search(r'ceasefire|truce',clause,re.I) if c['kind']=='bilateral_ceasefire' else re.search(r'Post Counter|posts?|tweets?',clause,re.I)
            # Explicit different dates/counts are a different assertion.
            dates=[_date(m.group()).isoformat() for m in DATES.finditer(clause) if _date(m.group())]
            if c['kind']=='publisher_monthly_count':
                dates += [f'{int(m[2]):04d}-{list(x.lower() for x in calendar.month_name).index(m[1].lower()):02d}' for m in re.finditer(r'\b('+MONTHS+r')\s+(\d{4})\b',clause,re.I)]
            compatible=not dates or not e.get('time') or e['time'] in dates
            if entities and action and compatible:found.append(dict(text=clause,start=a,end=b))
    return found


def _support(e,c,task,assertion,info,text,annotation,rules):
    blockers=[];direction=0;cutoff=_instant(task.get('cutoff'));clause=info.get('clause','')
    timing=dict(status='unresolved',event_time=e.get('time'),cutoff=task.get('cutoff'),publication_time_substituted=False)
    if c['status']!='supported':blockers.append('incomplete_task_contract')
    if not assertion:blockers.append('quote_not_verbatim_bound_to_original_sentence')
    if not cutoff:blockers.append('cutoff_unresolved')
    if annotation and annotation.get('time_scope') in ('unknown','historical_other_cycle'):blockers.append('annotation_temporal_compatibility_unresolved')
    if annotation and annotation.get('factual_status','asserted') not in ('asserted','reported'):blockers.append('annotation_not_asserted_or_reported')
    if MARKET_ODDS.search(clause):blockers.append('market_derived_claim')
    conflicts=_same_claim_conflict(text,assertion,c,e) if assertion else []
    if conflicts:blockers.append('matched_claim_conflict')
    temporal_stripped=re.sub(r'\b(?:'+MONTHS+r')\s+\d{4}\b','',DATES.sub('',clause),flags=re.I)
    if UNCERTAIN.search(temporal_stripped) or re.search(r'\bmay\b',temporal_stripped,re.I) or '?' in clause:blockers.append('uncertain_assertion')
    if info.get('stage')=='procedural':blockers.append('procedural_not_completed')
    for i,p in enumerate(c['participants']):
        if e.get('subject' if i==0 else 'object')!=p:blockers.append('missing_task_participant')
    kind=c['kind'];event_stamp=_instant(e.get('time',''));event=event_stamp.date() if event_stamp else _date(e.get('time',''))
    if kind=='publisher_monthly_count':
        expected=c['time_interval']['start'][:7]
        if e.get('time')!=expected:blockers.append('different_or_unresolved_month')
        if not info.get('complete'):blockers.append('not_explicit_whole_month_final_count')
        publisher=_entity_pattern(c['participants'][0])
        if not re.search(r'(?:Post Counter\s+for\s+'+publisher+r'|'+publisher+r'\s+(?:posted|published))',clause,re.I):blockers.append('count_publisher_relation_unbound')
        if re.search(r'\binclud(?:es?|ing)\s+(?:all\s+)?(?:ordinary\s+)?replies\b|\bexclud(?:es?|ing)\s+(?:all\s+)?(?:reposts|quote posts|deleted posts)\b',clause,re.I):blockers.append('incompatible_counting_definition')
        if re.search(r'\b(?:daily|so far|to date|forecast|projected)\b',clause,re.I):blockers.append('incomplete_or_forecast_count')
        if c['count_metric']['required_source_witness'] and not (re.search(r'\b(?:XTracker|xtracker\.polymarket\.com)\b',clause,re.I) and re.search(r'Post Counter',clause,re.I)):blockers.append('counting_metric_source_unverified')
        # Unspecified civil timezone: require date strictly later than month end.
        end=date.fromisoformat(c['time_interval']['end'])
        complete=bool(cutoff and cutoff.date()>end)
        timing.update(status='period_complete' if complete else 'period_not_complete',event_interval=[c['time_interval']['start'],c['time_interval']['end']],timezone='unspecified')
        if not complete:blockers.append('period_not_complete_at_cutoff')
        if info.get('count') is None:blockers.append('count_unresolved')
        if re.search(r'\b(?:was|were|is|had|has)\s+not\b|\bnot\s+\d',clause,re.I):blockers.append('negated_count_not_actual_total')
        if not blockers:
            direction=1 if c['count_metric']['lower']<=info['count']<=c['count_metric']['upper'] else -1
    else:
        deadline=date.fromisoformat(c['deadline']['date']) if c['deadline']['date'] else None
        start=date.fromisoformat(c['time_interval']['start']) if c['time_interval']['start'] else None
        if not event:blockers.append('event_time_unresolved')
        elif cutoff:
            timing['status']='at_or_before_cutoff' if event<=cutoff.date() else 'after_cutoff'
            if event>cutoff.date() or (event_stamp and event_stamp>cutoff):
                blockers.append('event_after_cutoff');timing['status']='after_cutoff'
            if start and event<start:blockers.append('historical_other_cycle')
        if info.get('explicit_negative'):
            # Only a failure stated through the actual deadline can prove No.
            boundary=_end_of_day(deadline,c['deadline']['timezone']) if deadline else None
            elapsed=bool(cutoff and deadline and (cutoff>boundary if boundary else cutoff.date()>deadline))
            if not elapsed:blockers.append('deadline_not_elapsed')
            if event!=deadline or not re.search(r'\bby\s+'+DATE_PATTERN,clause,re.I):blockers.append('negative_does_not_cover_deadline')
            if not blockers:direction=-1
        else:
            if not info.get('complete'):blockers.append('no_completed_assertion')
            if deadline and event and event>deadline:blockers.append('event_after_deadline_not_task_failure')
            if kind=='bilateral_ceasefire':
                p1,p2=[_entity_pattern(p) for p in c['participants']]
                pair=r'(?:'+p1+r'\s+(?:and|&)\s+'+p2+'|'+p2+r'\s+(?:and|&)\s+'+p1+')'
                if not re.search(pair+r'\s+(?:(?:publicly|officially|jointly|mutually)\s+)*(?:announced|agreed|signed|reached)\b',clause,re.I):blockers.append('agreement_participant_relation_unbound')
                if re.search(r'\b(?:not|never)\s+(?:(?:yet|mutually|officially)\s+)*(?:agreed|signed|reached|announced)\b',clause,re.I):blockers.append('negated_agreement')
                if not re.search(r'\b(?:publicly announced|officially announced|official\s+ceasefire\s+agreement)\b',clause,re.I):blockers.append('public_official_agreement_unestablished')
                if not re.search(r'\b(?:mutually agreed|both\s+(?:sides|countries)\s+(?:agreed|signed)|jointly\s+(?:announced|signed))\b',clause,re.I):blockers.append('mutual_agreement_unestablished')
                if not re.search(r'\b(?:general|comprehensive|all[- ]fronts?|all\s+military)\b',clause,re.I):blockers.append('general_halt_unestablished')
                if re.search(r'\b(?:humanitarian|energy infrastructure|Black Sea|informal)\b',clause,re.I):blockers.append('excluded_ceasefire_scope')
            if not blockers:direction=1
    support=[direction if _clean(o)=='yes' else -direction for o in task['outcomes']]
    matched=[r['id'] for r in rules if direction and r['support']==dict(zip(task['outcomes'],support))]
    evaluations=[dict(r,configured_support=r['support'],matched=r['id'] in matched,blockers=list(blockers),
        assertion_witness=assertion['text'] if assertion else None,assertion_source_scope='complete_original_title_or_body_sentence') for r in rules]
    return support,dict(rule_table_version='patent_support_v2',contract_source='question_and_cutoff_visible_description',
        matched_rule_ids=matched,rules=evaluations,blockers=list(dict.fromkeys(blockers)),time_check=timing,
        conflict_witnesses=conflicts,resolution='matched' if direction else 'no_unambiguous_rule_abstain',
        original_model_support_used=False,reviewed=False)


def evaluate(elements,task,*,quote,text,original_support,annotation=None):
    c=_contract(task)
    if c['fallback_v1']:
        e,r,s,tr=v1.evaluate(elements,task,quote=quote,text=text,original_support=original_support,annotation=annotation)
        tr['policy']=POLICY;tr['structured_contract']=c;return e,r,s,tr
    rules=validate_support_rules(task);effective=effective_task(task);target=effective['target_elements']
    assertion=_bind_quote(str(text),quote,c)
    e,w,info=_extract(assertion,c,elements) if assertion else ({},{},{})
    matched=[k for k,v in target.items() if e.get(k)==v];relevance=len(matched)/len(target) if target else 0.
    support,st=_support(e,c,task,assertion,info,text,annotation,rules)
    removed={k:'no_coherent_original_assertion_witness' for k in elements if k not in e}
    tr=dict(policy=POLICY,original_target=deepcopy(task['target_elements']),effective_target=deepcopy(target),task_parse=effective['_patent_task_parse'],
        raw_elements=deepcopy(elements),original_support=list(original_support),effective_elements=deepcopy(e),structured_contract=c,
        normalization=dict(witnesses=w,removed=removed,publication_time_substituted=False,
            alias_source='finite_source_bound_entity_and_action_grammar',assertion=assertion,assertion_status=info.get('stage','unbound')),
        overlap=dict(target=target,matched=matched,matched_count=len(matched),target_count=len(target),relevance=relevance,semantic_gate_applied=False),
        support=st,fact_group=dict(key=list(fact_key(e)),policy='exact_normalized_five_elements',fuzzy_merge=False,weighting='gamma ** chronological_rank'))
    return e,relevance,support,tr


