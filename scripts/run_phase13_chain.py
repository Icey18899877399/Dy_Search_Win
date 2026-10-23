"""Offline Phase 13 chain audit. Previously inspected data; no API or labels."""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib, html, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.reviewpack import validate_output
from dynamic_retrieval.calibration_observations import estimate_incubation_band
from verify_phase12 import verify as verify_previous

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def original_shape(result):
    result=json.loads(json.dumps(result))
    result['provenance'].pop('decision_trace_version',None)
    for row in result['rounds']: row.pop('decision_trace',None)
    return result

def metrics(result):
    return dict(rounds=len(result['rounds']),reads=result['diagnostics']['body_reads'],
        spent=result['result']['spent'],final_directional=result['result']['supporting_evidence_count'],
        expansions=sum(r['action']=='expand' for r in result['rounds']),
        removed_evidence=sum(len(r['decision_trace']['boundary_adjustment']['removed_ids']) for r in result['rounds']),
        recovery_reasons=dict(Counter(r['decision_trace']['recovery']['reason'] for r in result['rounds'])))

def execute(output):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'artifacts'): raise ValueError('Output must stay on project D drive')
    output=validate_output(output)
    previous=ROOT/'artifacts/phase12-development-20261023'
    verify_previous(previous)
    hashes={};items=[]
    for base in sorted((ROOT/'artifacts').glob('semantic-v5-independent-*')):
        for folder in sorted((base/'inputs/tasks').iterdir()):
            if not folder.is_dir(): continue
            paths=[folder/'task.json',folder/'forecast-documents.json',base/'runs'/folder.name/'machine-annotations.json']
            for p in paths: hashes[str(p.relative_to(ROOT))]=sha(p)
            items.append((folder.name,*map(read,paths)))
    assert len(items)==18
    codes={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src').rglob('*.py'))}
    for name in ('run_phase13_chain.py','verify_phase13.py'):
        p=ROOT/'scripts'/name;codes[str(p.relative_to(ROOT))]=sha(p)
    records=[];focus=None
    for mid,task,docs,annotations in items:
        for mode in ('fixed','basic','enhanced'):
            p=previous/'runs'/mid/mode/'v6_admission.json'
            hashes[str(p.relative_to(ROOT))]=sha(p)
            old=read(p);cfg=Config.from_dict(old['config'])
            result=run(task,docs,cfg,annotations,comparison_policy='typed_v6',decision_trace=True)
            assert original_shape(result)==old,mid+'/'+mode+' default output changed'
            path='baseline/'+mid+'/'+mode+'.json';write(output/path,result)
            records.append(dict(market_id=mid,mode=mode,path=path,full_output_parity=True,metrics=metrics(result)))
        if mid=='2354063': focus=(task,docs,annotations)
        print('Verified default full-output parity:',mid,flush=True)
    assert focus is not None
    task,docs,annotations=focus
    # Declared sensitivity cases, not selected using scores or outcome labels.
    cases={'round_budget_40':{'round_budget':40.},'recovery_fraction_050':{'recovery_fraction':.5},
        'initial_window_21':{'initial_window_days':21.},'source_cost_0025':{'cost_per_day':.025},
        'slow_multiplier_15':{'slow_multiplier':1.5},'waiting_share_050':{'waiting_share':.5},
        'shared_quota_080':{'shared_quota':.8},'shrink_fraction_0125':{'shrink_fraction':.125}}
    profile=dict(evidence_span_days=3.,evidence_span_provenance='SYNTHETIC integration example; not measured on these events',
        task_duration_days=60.,budget_unit='simulation_units',out_of_domain='clamp',
        table=[dict(urgency=u,budget=b,parameters=dict(slow_multiplier=4-u-b/200,
            waiting_share=.4-.05*u,shared_quota=.7-.1*u)) for u in (0.,1.) for b in (0.,200.)])
    experiments=[]
    for mode in ('basic','enhanced'):
        cfg=Config.from_dict(read(previous/'runs/2354063'/mode/'v6_admission.json')['config'])
        for name,change in cases.items():
            result=run(task,docs,replace(cfg,**change),annotations,comparison_policy='typed_v6',decision_trace=True)
            path='sensitivity/'+mode+'/'+name+'.json';write(output/path,result)
            experiments.append(dict(mode=mode,name=name,change=change,path=path,metrics=metrics(result),empirical_calibration=False))
        result=run(task,docs,cfg,annotations,comparison_policy='typed_v6',runtime_policy=profile)
        path='runtime-demo/'+mode+'.json';write(output/path,result)
        experiments.append(dict(mode=mode,name='synthetic_runtime_table',change={'runtime_policy':profile},path=path,
            metrics=metrics(result),empirical_calibration=False))
    no_samples=estimate_incubation_band([],event_type='parliament_dissolution',
        calibration_cutoff=task['cutoff'],quantile=.9)
    write(output/'calibration-status.json',dict(incubation=no_samples,source_cost=dict(status='observations_missing',
        required=['source_id','response_latency_seconds','rate_limit_quota','returned_items','observation_window','quota_unit','provenance']),
        applied_to_defaults=False,runtime_profile_status='synthetic_not_fitted'))
    summary=dict(status='completed_offline_development',events=18,validated_documents=sum(len(i[2]) for i in items),
        baseline_runs=54,full_output_parity_runs=54,sensitivity_runs=16,runtime_demo_runs=2,
        network_attempts=0,accuracy_improvement_verified=False,empirical_calibration=False,defaults_changed=False,
        records=records,experiments=experiments,
        limitations=['Already inspected development data; no independent evaluation.',
          'Legacy partial-band recovery is an engineering variant; patent [0252] describes a full band.',
          'Basic is a comparator that bypasses the net-gain gate.',
          'Runtime parameters use round-start elapsed time; waiting cap locks on slow entry using that round table.',
          'Offline cutoff and simulated time/cost; real source/model costs are not measured.',
          'Regular round_budget remains explicit; not derived from total_budget/planned_rounds.',
          'Synthetic table is not empirical calibration and does not guarantee recovery.'])
    write(output/'summary.json',summary)
    def table(headers,rows):
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    round_tables=''
    labels={'insufficient_recovery_budget':'回收预算不足','no_observed_loss':'未观测到损失','approved':'可执行','cooldown':'冷却期','below_high_loss':'未过高损失阈值','negative_net_gain':'净收益为负','no_recovery_sources':'无可回收来源','fixed_mode':'固定窗口'}
    for mode in ('basic','enhanced'):
        out=read(output/'baseline/2354063'/(mode+'.json'))
        rows=[]
        for r in out['rounds']:
            t=r['decision_trace'];rec=t['recovery'];adj=t['boundary_adjustment']
            rows.append([r['round'],r['state_before'],round(r['loss'],3),round(rec['available_budget'],3),
                round(rec['query_overhead']+rec['read_reserve'],3),round(rec['candidate_width_days'],3),
                labels.get(rec['reason'],rec['reason']),r['action'],len(adj['entered_ids']),len(adj['removed_ids'])])
        round_tables+='<details><summary>'+mode+'：完整逐轮记录</summary>'+table(['轮','轮首状态','损失','回收额度','最低开销','跨度/天','判据','动作','进入','移出'],rows)+'</details>'
    rows=[]
    for record in experiments:
        m=record['metrics']; rows.append([record['mode'], '<a href="'+record['path']+'">'+record['name']+'</a>',m['reads'],round(m['spent'],3),m['expansions'],m['removed_evidence'],m['final_directional']])
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>证据损失—回收决策—参数调整</title><style>body{margin:0;background:#f1f5f9;color:#17283d;font:16px/1.7 system-ui}main{max-width:1180px;margin:auto;padding:30px}section{background:white;border-radius:14px;padding:24px;margin:20px 0}h1{font-size:30px}h2{font-size:22px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:9px;border-bottom:1px solid #dce4eb;text-align:left;white-space:nowrap}summary{cursor:pointer;padding:12px;color:#086789}a{color:#086789}.note{border-left:4px solid #cd8c21;padding-left:15px}.flow{font-size:20px;color:#075c70}</style><main><h1>证据损失 → 回收决策 → 参数调整</h1><p>阶段十三 · 18 个已检查事件 · 356 篇有效文档 · 全程离线</p><section><h2>链路已接通</h2><p class="flow">逐条损失贡献 → 来源与预算判据 → 窗口调整及证据去向 → 紧迫度 / 剩余预算查表</p><p>54 次运行与阶段十二保存的结果逐字段一致（仅新增诊断字段）。另完成 16 次单参数敏感性运行和 2 次合成参数表联调。默认参数没有替换。</p></section><section><h2>焦点事件：证据为什么没有留下</h2><p>增强模式第 17 轮才发现方向性证据。守候轮有效预算 8 × 回收份额 0.25 = 2；9 个来源的请求开销 1.8，加最低读取预留 1，共需 2.8。可回收跨度为 0，尚未进入净收益判断。</p><p>基础模式第 1 轮回收 4.889 天，证据进入窗口；第 2 轮因决策前损失为零而收缩 3.5 天，刚回收的证据被移出。后续扩缩和预算约束均可在逐轮记录中追踪。</p><p class="note">改变轮询间隔或守候份额不会直接增加当轮回收预留。参数接通不等于证据一定回收，也不等于预测质量改善。</p>'''+round_tables+'''</section><section><h2>单变量敏感性与参数表联调</h2><p>每项独立修改一个配置；synthetic_runtime_table 单独演示三参数联动。移出数是逐轮累计，同一证据可重复计数。所有费用为模拟预算单位。</p>'''+table(['模式','配置案例','读取','支出','扩窗次数','证据移出','最终方向证据'],rows)+'''</section><section><h2>专利对应与尚未完成的标定</h2><p>[0103–0104] 已接入紧迫度 / 剩余预算表、线性插值、守候额度锁定和任务截止。slow_fraction 仍固定。表值取轮首时刻，进入守候时用该轮表值锁定额度。</p><p>[0249–0250] 已实现来源三指标归一加权与历史同类事件酝酿期分位工具。当前缺真实来源观测与历史酝酿期样本，标定状态仍为未完成；发表间隔没有被当成酝酿期。</p><p class="note">[0252] 原文描述整过渡带回收；当前保留部分跨度工程实现。basic 绕过净收益门槛，属于对照策略。每轮预算仍为独立配置，未按总预算 / 计划轮数派生。本轮不声称完整复现全部专利细节。</p></section><section><h2>复核入口</h2><p><a href="summary.json">全部实验索引</a> · <a href="calibration-status.json">标定缺项</a> · <a href="../../docs/phase13-delivery.md">接口与交付说明</a> · <a href="../phase12-development-20261023/index.html">阶段十二</a></p><p>模型 API 请求 0；未计算新的标签评分。这批事件已用于开发，后续须另建独立验收集。</p></section></main></html>'''
    (output/'index.html').write_text(page,encoding='utf-8')
    for name,digest in hashes.items(): assert sha(ROOT/name)==digest
    for name,digest in codes.items(): assert sha(ROOT/name)==digest,'Code changed during run: '+name
    write(output/'experiment-manifest.json',dict(artifact_type='phase13_chain',source_sha256=hashes,code_sha256=codes,
        files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('records','experiments','limitations')},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    execute(parser.parse_args().output)
