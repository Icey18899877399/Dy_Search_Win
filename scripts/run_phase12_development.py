"""Reproducible, cache-only Phase 12 development replay. Never sends requests.

Run: python -B scripts/run_phase12_development.py --output artifacts/phase12-development-20261023
Already inspected V5 events are development data. Original artifacts are read-only.
"""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import html
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'.runtime/tmp')
from dynamic_retrieval.calibration import calibrate_sources, calibrate_gamma
from dynamic_retrieval.call_cost import CallCostLedger
from dynamic_retrieval.engine import run
from dynamic_retrieval.evidence import extract
from dynamic_retrieval.fact_groups import row_audit
from dynamic_retrieval.models import Config
from dynamic_retrieval.on_demand import run_on_demand
from dynamic_retrieval.semantic import DeepSeekClient
from dynamic_retrieval.reviewpack import validate_output


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

class NetworkDisabled:
    def open(self,*args,**kwargs):raise AssertionError('Development replay must never use network')


def execute(output):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'artifacts'):
        raise ValueError('Development outputs must stay inside this D-drive project artifacts folder')
    output=validate_output(output)
    folders=sorted((ROOT/'artifacts').glob('semantic-v5-independent-*'))
    if len(folders)!=4:raise ValueError('Expected four frozen V5 batches')
    source_hashes={};items=[]
    for base in folders:
        manifest=read(base/'manifest.json')
        source_hashes[str((base/'manifest.json').relative_to(ROOT))]=sha(base/'manifest.json')
        for name,expected in manifest['files'].items():
            if sha(base/name)!=expected:raise ValueError('Frozen input hash mismatch: '+name)
            source_hashes[str((base/name).relative_to(ROOT))]=expected
        for td in sorted((base/'inputs/tasks').iterdir()):
            if not td.is_dir():continue
            items.append((base,td,read(td/'task.json'),read(td/'forecast-documents.json'),
                read(base/'runs'/td.name/'machine-annotations.json')))
    code_hashes={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src').rglob('*.py'))}
    code_hashes[str(Path(__file__).relative_to(ROOT))]=sha(Path(__file__))
    plan=dict(scope='previously_inspected_development_only',label_access=False,
        external_model_requests_allowed=False,inputs=source_hashes,code_sha256=code_hashes,
        task_count=len(items),valid_document_count=sum(len(x[3]) for x in items),
        sampled_document_count=sum(len(read(x[1]/'sampled-documents.json')) for x in items),
        ablations=['v5_legacy','v6_admission','v5_conservative_facts','v6_conservative_facts'],
        defaults_changed=False,source_parameters_applied=False)
    write(output/'execution-plan.json',plan)
    records=[];source_rows=[];gamma_rows=[];directional=[]
    for base,td,task,docs,annotations in items:
        mid=td.name
        for doc in docs:
            source_rows.append(dict(observation_id=mid+':'+doc['id'],source_id=doc['source_id']))
            evidence=extract(doc,task,annotations)
            if row_audit(evidence)['eligible']:
                gamma_rows.append(dict(observation_id=mid+':'+doc['id'],source_id=doc['source_id'],
                    event_id=task['event_id'],elements=evidence['elements'],support=evidence['support']))
            if any(evidence['support']):
                revised=extract(doc,task,annotations,comparison_policy='typed_v6')
                directional.append(dict(market_id=mid,document_id=doc['id'],support=evidence['support'],
                    v5_relevance=evidence['relevance'],v6_relevance=revised['relevance'],
                    v6_trace=revised['matching_trace']))
        for mode in ('fixed','basic','enhanced'):
            frozen=read(base/'runs'/mid/mode/'result.json')
            cfg=Config.from_dict(frozen['config'])
            variants={}
            for name,policy,facts in [('v5_legacy',None,'legacy'),('v6_admission','typed_v6','legacy'),
                    ('v5_conservative_facts',None,'conservative_v1'),('v6_conservative_facts','typed_v6','conservative_v1')]:
                result=run(task,docs,cfg,annotations,comparison_policy=policy,fact_policy=facts)
                write(output/'runs'/mid/mode/(name+'.json'),result)
                variants[name]=dict(probabilities=result['result']['probabilities'],
                    body_reads=result['diagnostics']['body_reads'],admitted=result['diagnostics']['admitted_documents'],
                    directional_admitted=sum(any(e['support']) for e in result['evidence']),
                    directional_final=result['result']['supporting_evidence_count'],
                    simulated_spent=result['result']['spent'])
                if name=='v5_legacy':baseline=result
            ledger=CallCostLedger(output/'runs'/mid/mode/'cache-attempts.jsonl')
            client=DeepSeekClient(ROOT/'artifacts/deepseek-cache',api_key='',max_attempts=1,cost_ledger=ledger)
            client._opener=NetworkDisabled()
            lazy=run_on_demand(task,docs,cfg,client)
            write(output/'runs'/mid/mode/'on-demand-cache.json',lazy)
            parity=all(lazy[k]==baseline[k] for k in ('rounds','result','evidence'))
            if not parity:raise AssertionError('On-demand versus shared annotation mismatch '+mid+'/'+mode)
            calls=lazy['diagnostics']['model_calls']
            assert calls['network_attempts']==0
            records.append(dict(market_id=mid,event_id=task['event_id'],question=task['question'],mode=mode,
                documents=len(docs),variants=variants,lazy_shared_parity=parity,
                frozen_v5_result_parity=baseline['result']==frozen['result'],
                lazy_calls={k:v for k,v in calls.items() if k!='events'}))
        print('Completed development replay:',mid,flush=True)
    calibration=dict(source_parameters=calibrate_sources(source_rows),gamma=calibrate_gamma(gamma_rows),
        source_data_note='Frozen documents identify sources only. No measured query cost or coverage denominator is present.',
        gamma_data_note='Only quote-grounded complete facts qualify. No incomplete fact is promoted to a duplicate.',
        band_days=dict(status='uncalibrated',reason='No measured evidence incubation intervals by event type'),
        threshold_quantiles=dict(status='uncalibrated',reason='No independent stable-regime metric history'),
        urgency_table=dict(status='implemented_not_fitted',reason='No empirical urgency-budget table or observed incubation estimate'),
        applied=False)
    write(output/'calibration-status.json',calibration)
    totals={}
    for name in plan['ablations']:
        totals[name]={k:sum(r['variants'][name][k] for r in records) for k in
            ('body_reads','admitted','directional_admitted','directional_final','simulated_spent')}
        totals[name]['changed_prediction_runs_vs_v5']=sum(
            r['variants'][name]['probabilities']!=r['variants']['v5_legacy']['probabilities'] for r in records)
    summary=dict(status='completed_cache_only_development',scope=plan['scope'],events=len(items),
        sampled_documents=plan['sampled_document_count'],validated_documents=plan['valid_document_count'],
        failed_historical_documents_excluded=plan['sampled_document_count']-plan['valid_document_count'],
        ablation_runs=len(records)*4,on_demand_runs=len(records),
        on_demand_parity_runs=sum(r['lazy_shared_parity'] for r in records),
        original_result_parity_runs=sum(r['frozen_v5_result_parity'] for r in records),
        directional_documents=len(directional),v5_directional_passes=sum(r['v5_relevance']>=.4 for r in directional),
        v6_directional_passes=sum(r['v6_relevance']>=.4 for r in directional),
        external_network_attempts=sum(r['lazy_calls']['network_attempts'] for r in records),
        cache_hits=sum(r['lazy_calls']['cache_hits'] for r in records),actual_new_tokens=0,
        monetary_cost=None,monetary_savings_verified=False,accuracy_improvement_verified=False,
        totals=totals,records=records,directional=directional,calibration_applied=False,
        limitations=['Development data, not untouched evaluation.','Failed historical extractions excluded for common-input comparison.',
            'Zero new calls means cache replay only; counterfactual cold-cache savings are not measured.',
            'Procedure evidence is weak context, not settlement proof.','Strict fact grouping is lexical and does not prove independent reality.'])
    write(output/'summary.json',summary)
    rows=''.join('<tr><td>'+html.escape(name)+'</td><td>'+str(v['body_reads'])+'</td><td>'+str(v['directional_admitted'])+'</td><td>'+str(v['directional_final'])+'</td><td>'+str(v['changed_prediction_runs_vs_v5'])+'</td></tr>' for name,v in totals.items())
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>参数、证据与调用成本开发验证</title><style>body{font:16px/1.65 system-ui;background:#f2f5fa;color:#17263d;margin:0}main{max-width:1080px;margin:auto;padding:32px}section{background:white;padding:24px;margin:18px 0;border-radius:14px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}.scroll{overflow:auto}a{color:#11649c}.note{border-left:4px solid #cb8c29;padding-left:14px}</style><main><h1>参数、证据与调用成本：开发验证</h1><p>18 个已检查事件 · 358 篇历史样本 / 356 篇有效文档 · 保留原实验</p><section><h2>本轮结果</h2><p>216 次证据消融 + 54 次按需缓存回放。按需路径与共享标注路径的调度、证据和预测全部一致。</p><p>方向性文档准入检查：V5 通过 '''+str(summary['v5_directional_passes'])+' / '+str(len(directional))+'；V6 通过 '+str(summary['v6_directional_passes'])+''' / 44。新增规则仅覆盖议会解散和 Fed 主席确认的已发生程序步骤，时间必须来自相同事件陈述。</p><p class="note">程序进展不等于完成结算；本轮未访问标签计算新评分，不能声明预测质量改善。</p></section><section><h2>同输入开发消融</h2><div class="scroll"><table><tr><th>策略</th><th>累计读取</th><th>方向证据准入</th><th>最终方向证据</th><th>预测变化次数 / 54</th></tr>'''+rows+'''</table></div><p>表中计数累加 18 个事件 × 3 种调度模式，同一文档可能被重复统计。</p></section><section><h2>参数标定状态</h2><p>已实现来源成本和覆盖尺度拟合、gamma 样本标定、紧迫度—预算档位插值，以及按来源参数的显式引擎入口。当前冻结数据缺少实际查询覆盖分母、费用与事实孕育期观测，所以这些参数仍未标定，默认值没有替换。</p><p><a href="calibration-status.json">逐来源状态与缺失原因</a></p></section><section><h2>实际调用账本</h2><p>本轮网络请求 0，新增 tokens 0；缓存命中 '''+str(summary['cache_hits'])+''' 次。缓存历史 tokens 单独记录，不能当新增支出或节省。</p><p>客户端已记录每次网络尝试、重试、耗时、已返回用量与未知用量；正式费用和冷缓存成本比较仍待实测。进程被强杀时，在途请求可能没有完成记录。</p></section><section><h2>可复核材料</h2><p><a href="summary.json">完整运行结果索引</a> · <a href="execution-plan.json">输入与代码冻结清单</a> · <a href="../../docs/phase12-fact-diagnostic.md">逐条证据诊断</a> · <a href="http://127.0.0.1:8765/">原工作台</a></p></section></main></html>'''
    (output/'index.html').write_text(page,encoding='utf-8')
    for name,digest in source_hashes.items():assert sha(ROOT/name)==digest
    for name,digest in code_hashes.items():assert sha(ROOT/name)==digest,'Source changed during experiment: '+name
    manifest=dict(artifact_type='phase12_development',code_sha256=code_hashes,source_sha256=source_hashes,
        files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    write(output/'experiment-manifest.json',manifest)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('records','directional')},ensure_ascii=False))
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();execute(args.output)
