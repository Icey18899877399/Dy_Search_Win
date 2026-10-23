"""Replay frozen V5 development evidence without model requests or label metrics."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'.runtime')
from dynamic_retrieval.evidence import extract
from dynamic_retrieval.fact_groups import group_facts, independent_fact_weights, row_audit
from dynamic_retrieval.core import independent_weights
from dynamic_retrieval.matching_v6 import evaluate as evaluate_v6


def run(root=ROOT):
    hashes={}
    def read(path):
        raw=path.read_bytes();hashes[str(path.relative_to(root))]=hashlib.sha256(raw).hexdigest()
        return json.loads(raw.decode('utf-8-sig'))
    summary_path=root/'docs'/'matching-v5-independent-summary.json'
    # Explicit projection. The historical file also contains labels and scores:
    # neither is selected, inspected by this program, used for policy, nor emitted.
    historical=read(summary_path)
    index={(r['market_id'],r['document_id']):r for r in historical['directional']}
    del historical
    details=[];tasks=[];group_reports={};totals=Counter();blockers=Counter();group_blockers=Counter()
    weights_changed=0
    for batch in sorted((root/'artifacts').glob('semantic-v5-independent-*')):
        for task_dir in sorted((batch/'inputs'/'tasks').iterdir()):
            if not task_dir.is_dir():continue
            mid=task_dir.name
            task=read(task_dir/'task.json')
            documents=read(task_dir/'forecast-documents.json')
            selected=read(task_dir/'sampled-documents.json')
            totals['selected_documents']+=len(selected)
            annotations=read(batch/'runs'/mid/'machine-annotations.json')
            traces=read(batch/'runs'/mid/'extraction-trace.json')
            trace_by_id={t['document_id']:t for t in traces}
            totals['extraction_failures']+=sum(t.get('status')!='validated' for t in traces)
            config=read(batch/'runs'/mid/'enhanced'/'result.json')['config']
            rows=[];directional_count=0
            totals['documents']+=len(documents)
            for doc in documents:
                annotation=annotations.get(doc['id'])
                if annotation is None:totals['unannotated_documents']+=1;continue
                # Existing validator checks exact bound excerpt, hash and frozen task.
                extracted=extract(doc,task,annotations)
                row=deepcopy(doc)
                row.update({k:deepcopy(annotation[k]) for k in ('elements','support','quote','excerpt','factual_status','time_scope')})
                before=deepcopy(row);audit=row_audit(row)
                assert before==row
                assert row['support']==extracted['support']
                trace=trace_by_id[doc['id']]
                assert trace['status']=='validated'
                assert trace['parsed_response']['elements']==annotation['elements']
                assert trace['parsed_response']['support']==annotation['support']
                rows.append(row);totals['validated_documents']+=1
                group_blockers.update(audit['blockers'])
                if not any(row['support']):continue
                directional_count+=1;key=(mid,doc['id'])
                frozen=index[key];match=extracted['matching_trace']
                assert match['blockers']==frozen['blockers'],key
                passes=extracted['relevance']>=config['admission']
                assert passes==frozen['passes'],key
                blockers.update(match['blockers'])
                comparison_score,comparison_trace=evaluate_v6(annotation['elements'],task,quote=annotation['quote'],context=annotation['excerpt'],rationale=annotation['rationale'])
                details.append(dict(market_id=mid,question=task['question'],document_id=doc['id'],
                    title=doc.get('title',''),source_id=doc['source_id'],published_at=doc['published_at'],
                    source_url=doc.get('canonical_url',''),quote=row['quote'],quote_bound=audit['quote_bound'],
                    frozen_elements=row['elements'],support=row['support'],factual_status=row['factual_status'],
                    time_scope=row['time_scope'],rationale=annotation['rationale'],
                    matching_trace=match,frozen_read=frozen['read'],frozen_passes=passes,
                    frozen_admitted=frozen['admitted'],frozen_final=frozen['final'],
                    grouping_audit=audit,admission_repair_applied=False,
                    opt_in_v6_passes=comparison_score>=config['admission'],opt_in_v6_trace=comparison_trace,
                    evidence_artifact=str((batch/'runs'/mid/'extraction-trace.json').relative_to(root)),
                    evidence_sha256=hashes[str((batch/'runs'/mid/'extraction-trace.json').relative_to(root))]))
            grouped=group_facts(rows)
            old=independent_weights(rows,config['gamma']);new=independent_fact_weights(rows,config['gamma'])
            assert set(old)==set(new)
            changed=sum(old[k]!=new[k] for k in old)
            weights_changed+=changed
            group_reports[mid]=dict(input_documents=len(rows),eligible_documents=grouped['eligible_documents'],
                groups=len(grouped['groups']),grouped_documents=grouped['grouped_documents'],
                multi_document_groups=[g for g in grouped['groups'] if len(g['document_ids'])>1],
                old_to_new_weight_changes=changed,
                old_weight_sum=sum(old.values()),new_weight_sum=sum(new.values()))
            tasks.append(dict(market_id=mid,question=task['question'],cutoff=task['cutoff'],
                task_parse=task['task_parse'],target_elements=task['target_elements'],
                documents=len(documents),validated=len(rows),directional_documents=directional_count))
    assert len(details)==len(index)==44
    totals.update(tasks=len(tasks),directional_documents=len(details),
        directional_passes=sum(d['frozen_passes'] for d in details),
        directional_read=sum(d['frozen_read'] for d in details),
        directional_admitted=sum(d['frozen_admitted'] for d in details),
        directional_final=sum(d['frozen_final'] for d in details),
        opt_in_v6_directional_passes=sum(d['opt_in_v6_passes'] for d in details),
        opt_in_v6_new_directional_passes=sum(d['opt_in_v6_passes'] and not d['frozen_passes'] for d in details),
        eligible_for_grouping=sum(g['eligible_documents'] for g in group_reports.values()),
        grouped_documents=sum(g['grouped_documents'] for g in group_reports.values()),
        group_count=sum(g['groups'] for g in group_reports.values()),weight_changes=weights_changed)
    report=dict(status='verified_frozen_development_diagnostic',scope='18 previously inspected V5 events; not held out',
        model_requests=0,label_metrics_computed=False,admission_policy='typed_v5_unchanged',comparison_policy='typed_v6_opt_in_two_procedural_templates',
        fact_policy='conservative_v1',totals=dict(totals),blocker_counts=dict(blockers),
        grouping_blocker_counts=dict(group_blockers),unsupported_tasks=[t for t in tasks if t['task_parse']['kind']=='unsupported'],
        tasks=tasks,grouping_by_task=group_reports,directional_rows=details,input_sha256=hashes,
        repair_decision='Historical V5 unchanged. Opt-in V6 adds only Israeli parliamentary dissolution and Kevin Warsh confirmation procedure contracts. Exact dated completed proposal submission is weak procedural context, never dissolution proof. Header-only dates and future/expected stages remain rejected. No broader normalization or missing-date relaxation is applied.',
        limitations=['Lexical five-element grounding is stricter than model extraction and does not establish truth.',
                    'Distinct source IDs do not establish independent reporting or remove cross-source syndication.',
                    'Same-source duplicate zero weighting only applies within a fully grounded matching group; incomplete facts remain separate.',
                    'This diagnostic does not establish predictive quality, real monetary savings or held-out generalization.',
                    'Historical summary contains labels; this script accesses only the directional index and computes no label-based quantity.',
                    'Operator initial broad summary read exposed embedded labels before projection; no label values informed the policies or this report.'])
    for relative,digest in hashes.items():
        assert hashlib.sha256((root/relative).read_bytes()).hexdigest()==digest, relative
    report['all_input_hashes_unchanged_after_replay']=True
    out=root/'docs'/'phase12-fact-diagnostic.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Phase 12: frozen V5 development fact/admission diagnostic','',
        'Scope: 18 previously inspected development events. No model requests; no quality or held-out claim. V5 admission is unchanged.','',
        '## Counts','', '| Metric | Value |','|---|---:|']
    lines += [f'| {key} | {value} |' for key,value in totals.items()]
    lines += ['', '## Opt-in V6 evidence-backed change', '',
        'V6 adds one newly passing directional document among these 44; admission and final evidence require engine replay. This is a development comparison, with the original support unchanged.']
    for d in details:
        if d['opt_in_v6_passes'] and not d['frozen_passes']:
            lines += ['', f"- {d['market_id']} / `{d['document_id']}`: {d['opt_in_v6_trace']['stage']}; date witnesses {d['opt_in_v6_trace']['time_check']['date_witnesses']}; establishes_outcome=false.", '', '> '+d['quote']]
    lines += ['', '## Decision', '', report['repair_decision'], '',
        'The conservative opt-in grouping requires all five nonempty elements in a bound quote, an exact complete event date, identical support and known source. Only whitespace/case, exact day formats and closed country aliases normalize. Missing fields, contradictory support, qualifiers and uncertain time remain distinct. Same-source duplicates stay in the audit and add zero weight; different source representatives use gamma by chronological rank.', '',
        'Grouping runs on all validated documents within each task. Changed weights below compare lexical legacy identity with conservative identity at the frozen gamma; they are not prediction-score changes.', '',
        '## V5 unsupported task contracts', '', '| Market | Question | Directional docs |','|---|---|---:|']
    lines += [f"| {t['market_id']} | {t['question']} | {t['directional_documents']} |" for t in report['unsupported_tasks']]
    lines += ['', '## Blockers (a row can have several)', '', '| Blocker | Documents |','|---|---:|']
    lines += [f'| {key} | {value} |' for key,value in blockers.most_common()]
    lines += ['', '## Directional evidence: all 44 rows', '']
    for d in details:
        lines += [f"### {d['market_id']} / {d['document_id']}",'',d['question'],'',
            f"- Frozen source: `{d['evidence_artifact']}`; source ID `{d['source_id']}`.",
            f"- Pass/read/admitted/final: {d['frozen_passes']}/{d['frozen_read']}/{d['frozen_admitted']}/{d['frozen_final']}; support `{d['support']}` unchanged.",
            f"- Opt-in V6 passes: {d['opt_in_v6_passes']}; stage: {d['opt_in_v6_trace'].get('stage')}; blockers: {d['opt_in_v6_trace']['blockers']}.",
            f"- Admission blockers: {', '.join(d['matching_trace']['blockers']) or 'none'}.",
            f"- Grouping blockers: {', '.join(d['grouping_audit']['blockers']) or 'none'}.",'',
            '> '+d['quote'].replace('\n','\n> '),'',
            'Frozen elements: `'+json.dumps(d['frozen_elements'],ensure_ascii=False)+'`.','']
    lines += ['## Limitations','']+['- '+x for x in report['limitations']]+['',
        'Exact source SHA-256 hashes, raw evidence, grounding witnesses, matching traces and per-task group counts are in `phase12-fact-diagnostic.json`.','']
    (root/'docs'/'phase12-fact-diagnostic.md').write_text('\n'.join(lines),encoding='utf-8')
    return report

if __name__=='__main__':
    result=run()
    print(json.dumps({'status':result['status'],'totals':result['totals'],'blocker_counts':result['blocker_counts']},ensure_ascii=False))


