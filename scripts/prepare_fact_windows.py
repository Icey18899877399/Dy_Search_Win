"""Prepare audited source windows and case cards offline; zero provider requests."""
from pathlib import Path
import argparse,json,hashlib,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.semantic import evidence_context
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from audit_fact_coverage import sha,read,write
CASES=[
 ('1171663','5a25a5ad0adf205cd5f39c5d9d468a7ed13e1842159d296794e408a66ebb4439','双边表态和全面停火报道','报道包含俄方停火宣布、乌方遵守表态及全方向停止军事行动。属于应补抽取的真实报道，不能因为短暂就自动当作任务排除项；是否属于人道暂停及正式共同协议仍需明确对应。','multi_sentence_relation_and_scope_unresolved'),
 ('1171663','31bb7e0c6498f8814b88f81eabbad6de6824c7bc86f0c6a624f240b01771561e','另一来源的同一复活节停火','领导人表态、起止日期与全方向暂停分散在不同句段；现有v2单断言规则未组合这些信息。不可将转载/同一事件当成多个独立事实。','multi_sentence_relation_and_scope_unresolved'),
 ('1171663','05368f0f7263675c86b3169bc60b25b3b08d3d58b562220480b9a9036e11fef5','正文尾部的俄乌停火报道','相关段落位于长文后部，需检查选定连续窗口是否覆盖；不能把前面的伊朗停火报道绑定到俄乌任务。','head_truncation_and_cross_event_separation'),
 ('2354063','3250b8d600752b8aff3b473b1978d02d2f244d7bba0aaac7289c38ec824061c8','110票初步表决与后续程序','正文明确初步表决110票支持、0反对，还需后续审批。能确认程序事实，不能据此判定议会已经解散。','procedural_fact_not_final_dissolution'),
 ('2354063','38bbe90dfd7cd8790f042b2ad242d9f3ddaf86eb92278f66069b339a37f2d16e','初步批准及三读要求','开头的approved a bill必须连同preliminary reading和第三次投票要求理解；标题或单独一句不能充当最终解散证明。','procedural_fact_not_final_dissolution'),
 ('2354063','ba238c27837c64ba078af41579946011882c5e38529aee896f9daa61ad134b2a','标题很强但正文只有存档链接','scrape_status=success不代表成功取得报道正文；该记录应补抓原始文章历史版本，不能借标题做证据。','missing_article_body'),
 ('2354063','6f3e4f0536b48c0eecf09726d8d339121f8d4027e230098ee4863a186e6abe4d','超长聚合页出处归属不明','正文约154万字符，单页发布时间不能自动作为其中每篇文章或事实的发布时间；先拆出可追溯子文章。','aggregated_article_attribution_unresolved'),
 ('1423716','570c7102bd283899da8e1dc155afff186331b4725ba28699659af01843b2476c','数量词命中并非目标计数','840000 tweets描述Wordle话题且属于其他时期，与马斯克2026年4月个人发帖计数不同。不得用数值关键词代替计数口径。','wrong_actor_period_and_metric'),
 ('1423716','21e2127680d84699b04604e4bbd4d5e5103942187cc5e535dcf448372ddcb1bc','赔率文章不是实际统计','区间及概率来自预测市场，且统计周期不同；缺少XTracker对应月份的实际计数。','market_derived_not_observed_count')]

def execute(out):
 if out.exists() or not out.is_relative_to(ROOT/'artifacts'):raise ValueError('Use a new artifact folder')
 src=ROOT/'artifacts/fact-coverage-20261023';manifest=read(src/'experiment-manifest.json')
 for name,digest in manifest['files'].items():assert sha(src/name)==digest
 code={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')};code[Path(__file__).relative_to(ROOT).as_posix()]=sha(__file__)
 write(out/'execution-plan.json',dict(scope='development_source_window_validation_only',context_policy='fact_window_v1',max_chars=12000,model_requests=0,label_access=False,source_manifest_sha256=sha(src/'experiment-manifest.json'),code_sha256=code))
 records=[];cards=[];parity=0
 for market in ('1171663','1423716','2354063'):
  task=read(src/f'inputs/{market}/task.json');newtask=dict(task,evidence_context_policy='fact_window_v1')
  docs=read(src/f'inputs/{market}/documents.json');rows={r['id']:r for r in read(src/f'coverage/{market}/documents.json')}
  write(out/f'inputs/{market}/task.json',newtask);windows=[]
  for d in docs:
   base=dict(document_id=d['id'],body_sha256=d['content_hash'],canonical_url=d['canonical_url'])
   row=rows[d['id']];full=d['title']+'\n'+d['text'];offset=len(d['title'])+1
   try:
    c=evidence_context(newtask,d);e=c['evidence'];assert full[e['excerpt_start']:e['excerpt_end']]==e['excerpt']
    selected=row['passages'];oldcovered=sum(offset+p['start']>=0 and offset+p['end']<=12000 for p in selected);newcovered=sum(offset+p['start']>=e['excerpt_start'] and offset+p['end']<=e['excerpt_end'] for p in selected)
    windows.append(dict(base,status='prepared_not_sent',evidence=e,old_head_complete_candidates=oldcovered,new_window_complete_candidates=newcovered,
      newly_covered_candidates=sum(offset+p['end']>12000 and offset+p['start']>=e['excerpt_start'] and offset+p['end']<=e['excerpt_end'] for p in selected)))
   except ValueError:
    windows.append(dict(base,status='excluded_before_model',blockers=row['eligibility_blockers']+row['source_quality']['blockers']))
  write(out/f'windows/{market}.json',windows)
  for mid,ident,title,meaning,gap in CASES:
   if mid!=market:continue
   d=next(x for x in docs if x['id']==ident);row=rows[ident];w=next(x for x in windows if x['document_id']==ident)
   ps=row['passages']
   if gap=='head_truncation_and_cross_event_separation':ps=[p for p in ps if p['after_default_12000_head']]
   if not ps:ps=[dict(start=0,end=min(len(d['text']),1800),text=d['text'][:1800],scope='original_body_diagnostic_only')]
   snippets=[{k:p[k] for k in ('start','end','text','scope')} for p in ps[:3]]
   for p in snippets:assert p['text']==d['text'][p['start']:p['end']]
   cards.append(dict(market_id=market,event_id=task['event_id'],document_id=ident,title=title,source_title=d['title'],canonical_url=d['canonical_url'],published_at=d['published_at'],observed_at=d['observed_at'],first_observed_at=row['first_observed_at'],cutoff=task['cutoff'],body_sha256=d['content_hash'],source_file=d['source_file'],snippets=snippets,assessment=meaning,gap=gap,assessment_origin='assistant_source_inspection_development_only',human_reviewed=False,is_outcome_label=False,model_window_status=w['status']))
  ready=[w for w in windows if w['status']=='prepared_not_sent'];records.append(dict(market_id=market,documents=len(docs),prepared=len(ready),excluded=len(docs)-len(ready),nonprefix_windows=sum(w['evidence']['excerpt_start']>0 for w in ready),newly_covered_candidates=sum(w['newly_covered_candidates'] for w in ready),old_head_complete_candidates=sum(w['old_head_complete_candidates'] for w in ready),new_window_complete_candidates=sum(w['new_window_complete_candidates'] for w in ready)))
  old=ROOT/'artifacts/semantics-v2-final-20261023/runs'/market
  for path in old.glob('*/result.json'):
   original=read(path);p=original['provenance'];inp=path.parent/'inputs'
   assert run(read(inp/'task.json'),read(inp/'documents.json'),Config.from_dict(original['config']),read(inp/'annotations.json'),evidence_policy=p.get('evidence_policy'),budget_policy=p.get('budget_policy'),grid_policy=p.get('grid_policy'),retrieval_policy=p.get('retrieval_policy'))==original
   parity+=1
 write(out/'fact-cards.json',cards)
 summary=dict(status='prepared_offline_not_model_evaluated',records=records,cards=len(cards),model_requests=0,independent_evaluation=False,empirical_calibration=False,legacy_parity_runs=parity,
  caveat='Candidate coverage is lexical, not factual accuracy. A single contiguous window can omit other candidates; no performance or outcome claim.')
 write(out/'summary.json',summary)
 for name,digest in code.items():assert sha(ROOT/name)==digest
 write(out/'experiment-manifest.json',dict(artifact_type='fact_window_development_preparation',code_sha256=code,files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);execute(p.parse_args().output.resolve())
