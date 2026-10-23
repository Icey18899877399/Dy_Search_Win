"""Label-free four-way development ablation on previously frozen model outputs; no API calls."""
import argparse,hashlib,json,sys
from pathlib import Path
from dataclasses import replace
from collections import Counter
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.cli import write_json,save_run
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.matching import validate_direction,normalize_task
from dynamic_retrieval.quality_pipeline import verify_source
from dynamic_retrieval.reviewpack import validate_output,page
from dynamic_retrieval.semantic import validate_model_annotation
VARIANTS={'filtered_baseline':(False,False),'matching_only':(True,False),'scheduler_only':(False,True),'combined':(True,True)}
def variant_task(original,matching,scheduler,matching_policy):
    task=dict(original)
    task.pop('matching_policy',None);task.pop('scheduler_policy',None)
    if matching:task['matching_policy']=matching_policy
    if scheduler:task['scheduler_policy']='grid_credit_v2'
    return task
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def execute(source,output,matching_policy='typed_v2'):
    source=Path(source).resolve();manifest=verify_source(source)
    output=validate_output(Path(output).resolve(),Path(r'D:\agents-main\agents\polymarket\data'))
    if output.is_relative_to(source) or source.is_relative_to(output):raise ValueError('Source/output overlap')
    summary=read(source/'summary.json')
    plan=dict(source=str(source),source_manifest_sha256=sha(source/'manifest.json'),
        variants=VARIANTS,model_requests=0,design='post_inspection_development_ablation',
        independent_holdout_claim=False,direction_policy='exclude_equal_nonzero_binary_support_and_poll_forecast_v1',
        matching_policy=matching_policy,scheduler_policy='grid_credit_v2',
        routing_assumption='local_frozen_document_metadata_is_free; not an online query-cost claim',
        filter_scope='all_variants_use_identical_validated_subset',tasks=[])
    prepared=[];excluded=[]
    for item in summary['tasks']:
        market=item['market_id'];inputs=source/'inputs/tasks'/market
        task=read(inputs/'task.json');docs=read(inputs/'forecast-documents.json')
        annotations=read(source/'runs'/market/'machine-annotations.json')
        keep=[]
        for doc in docs:
            validate_model_annotation(annotations[doc['id']],task,doc)
            try:validate_direction(annotations[doc['id']])
            except ValueError as exc:excluded.append(dict(market_id=market,id=doc['id'],reason=str(exc)));continue
            keep.append(doc)
        accepted={d['id']:annotations[d['id']] for d in keep}
        folder=output/'inputs'/market
        write_json(folder/'task.json',task);write_json(folder/'documents.json',keep)
        write_json(folder/'annotations.json',accepted)
        cfg=read(source/'runs'/market/'enhanced/result.json')['config']
        plan['tasks'].append(dict(market_id=market,config=cfg,
            normalized_target=normalize_task(task,policy=matching_policy)['target_elements'],
            files={p.relative_to(output).as_posix():sha(p) for p in folder.iterdir()}))
        prepared.append((market,task,keep,accepted,cfg))
    plan['excluded']=excluded
    write_json(output/'plan.json',plan) # All inputs/policies/configs are fixed before any variant.
    rows=[]
    for market,original,docs,ann,cfg in prepared:
        for name,(matching,scheduler) in VARIANTS.items():
            task=variant_task(original,matching,scheduler,matching_policy)
            for mode in ('fixed','basic','enhanced'):
                result=run(task,docs,replace(Config.from_dict(cfg),mode=mode),ann)
                save_run(result,output/'runs'/market/name/mode)
                rows.append(dict(market_id=market,variant=name,mode=mode,
                    probabilities=result['result']['probabilities'],body_reads=result['diagnostics']['body_reads'],
                    supporting=result['result']['supporting_evidence_count'],
                    spent=result['result']['spent'],final_boundary=result['result']['final_boundary'],
                    expansions=sum(r['action'] in ('expand','uncertainty_expand') for r in result['rounds'])))
        print('Ablation '+market,flush=True)
    report=dict(status='completed_development_ablation',tasks=len(prepared),runs=len(rows),
        source_validated_documents=summary['validated_documents'],retained_documents=sum(len(x[2]) for x in prepared),
        excluded_documents=len(excluded),model_requests=0,rows=rows,
        independent_holdout_claim=False,summary={})
    for variant in VARIANTS:
        group=[r for r in rows if r['variant']==variant and r['mode']=='enhanced']
        report['summary'][variant]=dict(tasks=len(group),nonuniform=sum(r['probabilities']!=[.5,.5] for r in group),
            body_reads=sum(r['body_reads'] for r in group),supporting=sum(r['supporting'] for r in group),
            expansions=sum(r['expansions'] for r in group),simulated_spent=sum(r['spent'] for r in group))
    write_json(output/'report.json',report)
    body='<p>同一有效文档/标注子集，四种修复组合 × 三方案。开发消融，无新增模型调用；不能当独立测试成绩。</p><pre>'+json.dumps(report['summary'],ensure_ascii=False,indent=2)+'</pre>'
    body+='<p><a href="plan.json">运行前冻结计划与排除原因</a> · <a href="report.json">完整逐任务数据</a></p>'
    (output/'index.html').write_text(page('三处瓶颈修复 · 开发消融',body),encoding='utf-8')
    verify_source(source)
    write_json(output/'manifest.json',dict(artifact_type='remediation_ablation',
        files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()},
        code_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src').rglob('*.py')}|{'run_remediation.py':sha(Path(__file__))}))
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'artifacts/expanded-semantic-20260515')
    p.add_argument('--matching-policy',choices=['typed_v2','typed_v3','typed_v4','typed_v5'],default='typed_v2')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();execute(a.source,a.output,a.matching_policy)
if __name__=='__main__':main()
