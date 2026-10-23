"""Frozen new-event cohorts with temporal/source coverage, never label selection."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import html
import json
import re
from pathlib import Path

from .cli import write_json, market_directory
from .models import Config
from .preparation import prepare_cohort
from .quality import instant, event_split
from .reviewpack import page, validate_output
from .automatic import automatic_rules
from .evidence import prepare_task

ROOT=Path(__file__).resolve().parents[2]
POLICY='time_strata_50_30_20_source_cap_dedup_no_market_commentary_v1'
MARKET=re.compile(r'\b(?:polymarket|kalshi|prediction[\s-]+markets?|betting[\s-]+markets?|odds|USDC)\b',re.I)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body_key(doc):
    normalized=re.sub(r'\s+',' ',doc.get('text','')).strip().casefold()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def zone(doc,cutoff,config):
    age=(instant(cutoff)-instant(doc['published_at'])).total_seconds()/86400
    if age<=config.initial_window_days:return 'window'
    if age<=config.initial_window_days+config.band_days:return 'band'
    return 'history'


def stratified_documents(task,documents,config,max_documents=20,source_cap=3,
                         used_bodies=None,used_urls=None):
    if type(max_documents) is not int or max_documents<1 or type(source_cap) is not int or source_cap<1:
        raise ValueError('Positive sample size/source cap required')
    used_bodies=set(used_bodies or ());used_urls=set(used_urls or ())
    cutoff=instant(task['cutoff']);excluded=Counter();eligible=[]
    for doc in documents:
        try:
            published,observed=instant(doc['published_at']),instant(doc['observed_at'])
            if published>cutoff or observed>cutoff or doc.get('event_id')!=task['event_id']:
                raise ValueError()
        except (KeyError,ValueError,TypeError,OverflowError):
            excluded['temporal_or_foreign']+=1;continue
        if (cutoff-published).total_seconds()/86400>config.earliest_days:
            excluded['before_horizon']+=1;continue
        if len(doc.get('text','').strip())<200:
            excluded['short_body']+=1;continue
        if MARKET.search(doc.get('title','')+'\n'+doc.get('text','')):
            excluded['market_commentary']+=1;continue
        key=body_key(doc);url=doc.get('canonical_url') or str(doc['id'])
        rawkey=hashlib.sha256(doc['text'].encode('utf-8')).hexdigest()
        if key in used_bodies or rawkey in used_bodies or url in used_urls:
            excluded['previously_selected_document']+=1;continue
        eligible.append((doc,key,url,published.timestamp(),observed.timestamp()))
    unique=[];seen_bodies=set();seen_urls=set()
    for doc,key,url,pub,obs in sorted(eligible,key=lambda r:(-r[3],-r[4],str(r[0]['id']))):
        if key in seen_bodies or url in seen_urls:
            excluded['duplicate_body_or_url']+=1;continue
        seen_bodies.add(key);seen_urls.add(url);unique.append(doc)
    pools={name:[d for d in unique if zone(d,task['cutoff'],config)==name] for name in ('window','band','history')}
    quotas={'window':max_documents//2,'band':max_documents*3//10}
    quotas['history']=max_documents-sum(quotas.values())
    counts=Counter();selected=[];ids=set()
    def take(name,limit):
        added=0
        while added<limit and len(selected)<max_documents:
            choices=[d for d in pools[name] if d['id'] not in ids and counts[d['source_id']]<source_cap]
            if not choices:break
            doc=min(choices,key=lambda d:(counts[d['source_id']],-instant(d['published_at']).timestamp(),str(d['id'])))
            selected.append(doc);ids.add(doc['id']);counts[doc['source_id']]+=1;added+=1
        return added
    for name in pools:take(name,quotas[name])
    for name in pools:take(name,max_documents-len(selected))
    audit=dict(policy=POLICY,raw_documents=len(documents),eligible_unique_documents=len(unique),
               excluded=dict(excluded),source_cap=source_cap,target_sample_size=max_documents,
               quotas=quotas,available_by_zone={k:len(v) for k,v in pools.items()},
               selected_by_zone={k:sum(zone(d,task['cutoff'],config)==k for d in selected) for k in pools},
               selected_sources=dict(sorted(counts.items())),selected_documents=len(selected),
               semantic_fact_verified=False)
    return selected,audit


def previous_exposure(artifacts):
    events=set();bodies=set();urls=set();files={}
    for path in sorted(Path(artifacts).rglob('result.json')):
        manifest_path=path.parent/'manifest.json'
        if not manifest_path.is_file():continue
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('files',{}).get('result.json')!=sha(path):
            raise ValueError('Historical result hash mismatch')
        result=json.loads(path.read_text(encoding='utf-8'))
        if result['task'].get('event_id'):events.add(str(result['task']['event_id']))
        for row in result.get('provenance',{}).get('inputs',[]):
            if row.get('body_sha256'):bodies.add(row['body_sha256'])
            if row.get('canonical_url'):urls.add(row['canonical_url'])
        files[str(path.resolve())]=sha(path)
    return dict(events=sorted(events),bodies=bodies,urls=urls,files=files)


def prepare_expansion(store,data_root,cutoff,output,history=None,count=20,max_documents=20,
                      source_cap=3,seed='patent-expansion-v1',config=None):
    output=validate_output(output,data_root)
    config=config or Config()
    if max_documents<12:raise ValueError('Expanded cohort requires at least 12 documents per task')
    exposure=previous_exposure(history or ROOT/'artifacts')
    used_bodies=set(exposure['bodies']);used_urls=set(exposure['urls']);audits={}
    def selector(task,documents):
        selected,audit=stratified_documents(dict(task,cutoff=cutoff),documents,config,
                              max_documents,source_cap,used_bodies,used_urls)
        z=audit['selected_by_zone']
        accepted=(len(selected)>=12 and z['window']>=4 and z['window']+z['band']>=8 and len(audit['selected_sources'])>=3)
        audit['coverage_gate_passed']=accepted
        audits[task['market_id']]=audit
        if not accepted:return []
        used_bodies.update(body_key(d) for d in selected)
        used_urls.update(d.get('canonical_url') or str(d['id']) for d in selected)
        return selected
    cohort=prepare_cohort(store,data_root,cutoff,count=count,min_documents=12,seed=seed,
                task_filter=lambda t:t['event_id'] not in exposure['events'],
                document_selector=selector,create_drafts=False)
    for item in cohort['selected']:
        task=item['task']
        try:
            rules=automatic_rules(task)
            task.update({k:rules[k] for k in ('target_elements','element_aliases')})
        except ValueError:pass
        item['task']=prepare_task(task)
        item['sampling']=audits[task['market_id']]
        item['available_documents']=item['sampling']['raw_documents']
        item['eligibility'].update(status='automatic_metadata_and_coverage_candidate',
                                   semantic_deadline_review='not_independently_verified')
        name=market_directory(task['market_id'])
        write_json(output/'tasks'/name/'task.json',item['task'])
        write_json(output/'tasks'/name/'documents.json',item['documents'])
    split=event_split([i['task'] for i in cohort['selected']],seed)
    plan=dict(format='expanded_frozen_cohort_v1',created_at=datetime.now(timezone.utc).isoformat(),
              cutoff=cutoff,config=asdict(config),seed=seed,target_tasks=count,
              retained_tasks=len(cohort['selected']),target_documents_per_task=max_documents,
              policy=POLICY,source_cap=source_cap,excluded_events=exposure['events'],
              historical_result_sha256=exposure['files'],split=split,
              selected=[dict(market_id=i['task']['market_id'],event_id=i['task']['event_id'],
                             sampling=i['sampling']) for i in cohort['selected']],
              limitations=['Text filters and source IDs do not prove independent facts.',
                           'Exact normalized-body/URL deduplication does not eliminate paraphrases or correlated reporting.',
                           'Retrospective model knowledge contamination remains possible.'])
    cohort['provenance'].update(selection_status='frozen_before_model',sampling_policy=POLICY,
                                limitations=plan['limitations'])
    write_json(output/'cohort.json',cohort)
    write_json(output/'plan.json',plan)
    write_json(output/'screening.json',audits)
    rows=['<tr><td>'+html.escape(i['task']['question'])+'</td><td>'+str(i['sampling']['selected_by_zone'])+'</td><td>'+str(len(i['sampling']['selected_sources']))+'</td></tr>' for i in cohort['selected']]
    body='<p>目标 '+str(count)+' 个新事件；实际冻结 '+str(plan['retained_tasks'])+' 个。未使用标签、模型支持或预测成绩筛选；原有事件及已用文档排除。</p>'
    body+='<p>每任务最多 '+str(max_documents)+' 篇；按窗口/过渡带/更早历史分层，单来源上限 '+str(source_cap)+'。没有为凑数量放宽门槛。</p>'
    body+='<p>这是待运行输入，未完成模型抽取或预测评价。过滤后新闻不等同于已核验独立事实。</p><table><tr><th>任务</th><th>分层数量</th><th>来源数</th></tr>'+''.join(rows)+'</table>'
    body+='<p><a href="plan.json">模型运行前冻结计划</a> · <a href="screening.json">筛选审计</a></p>'
    (output/'index.html').write_text(page('扩大样本 · 冻结输入',body),encoding='utf-8')
    files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
    code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}
    code['run_expansion.py']=sha(ROOT/'run_expansion.py')
    write_json(output/'manifest.json',dict(artifact_type='expanded_preparation',files=files,code_sha256=code))
    return plan


def load_expansion(path,cutoff,config):
    path=Path(path).resolve()
    manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('artifact_type')!='expanded_preparation':raise ValueError('Not a frozen expansion')
    for rel,expected in manifest['files'].items():
        p=(path/rel).resolve()
        if not p.is_relative_to(path) or sha(p)!=expected:raise ValueError('Frozen cohort changed')
    plan=json.loads((path/'plan.json').read_text(encoding='utf-8'))
    if instant(cutoff)!=instant(plan['cutoff']) or asdict(config)!=plan['config']:
        raise ValueError('Frozen cutoff/config mismatch')
    cohort=json.loads((path/'cohort.json').read_text(encoding='utf-8'))
    events={i['task']['event_id'] for i in cohort['selected']}
    if len(events)!=len(cohort['selected']) or events & set(plan['excluded_events']):
        raise ValueError('Event overlap in frozen cohort')
    return cohort,plan
