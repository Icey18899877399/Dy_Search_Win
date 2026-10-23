"""Phase14 preregistered full-band x round-budget development comparison."""
import argparse,json,sys,html,hashlib
from collections import Counter
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.reviewpack import validate_output
from verify_phase13 import verify as verify_previous

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def metrics(result):
    return dict(reads=result['diagnostics']['body_reads'],spent=result['result']['spent'],
        rounds=result['result']['rounds'],final_directional=result['result']['supporting_evidence_count'],
        expansions=sum(r['action']=='expand' for r in result['rounds']),
        contraction_removals=sum(len(r['decision_trace']['boundary_adjustment']['removed_ids']) for r in result['rounds'] if r['action']=='contract'),
        recovery_reasons=dict(Counter(r['decision_trace']['recovery']['reason'] for r in result['rounds'])))

def execute(output):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'artifacts'):raise ValueError('Output outside project artifacts')
    validate_output(output)
    previous=ROOT/'artifacts/phase13-chain-20261023'
    verify_previous(previous)
    inputs={};items=[]
    for base in sorted((ROOT/'artifacts').glob('semantic-v5-independent-*')):
        for td in sorted((base/'inputs/tasks').iterdir()):
            if not td.is_dir():continue
            paths=[td/'task.json',td/'forecast-documents.json',base/'runs'/td.name/'machine-annotations.json']
            for p in paths:inputs[str(p.relative_to(ROOT))]=sha(p)
            items.append((td.name,*map(read,paths)))
    assert len(items)==18 and sum(len(x[2]) for x in items)==356
    codes={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src').rglob('*.py'))}
    for name in ('run_phase14_comparison.py','verify_phase14.py'):
        p=ROOT/'scripts'/name;codes[str(p.relative_to(ROOT))]=sha(p)
    plan=dict(status='frozen_before_execution',scope='previously_inspected_development_only',
        events=18,valid_documents=356,variants=['legacy','full_band','derived_budget_legacy','derived_budget_full_band'],
        label_access=False,model_requests=0,defaults_changed=False,
        derived_round_budget_rule='total_budget / planned_rounds',empirical_calibration=False,
        planned_runs=180,code_sha256=codes,input_sha256=inputs)
    write(output/'execution-plan.json',plan)
    records=[]
    for mid,task,docs,annotations in items:
        for mode in ('fixed','basic','enhanced'):
            p=previous/'baseline'/mid/(mode+'.json');old=read(p)
            inputs[str(p.relative_to(ROOT))]=sha(p)
            cfg=Config.from_dict(old['config'])
            cases=[('legacy',cfg,None),('derived_budget_legacy',replace(cfg,round_budget=cfg.total_budget/cfg.rounds),None)]
            if mode!='fixed':cases += [('full_band',cfg,'patent_full_band_v1'),
                ('derived_budget_full_band',replace(cfg,round_budget=cfg.total_budget/cfg.rounds),'patent_full_band_v1')]
            for variant,config,policy in cases:
                out=run(task,docs,config,annotations,comparison_policy='typed_v6',decision_trace=True,recovery_policy=policy)
                parity=None
                if variant=='legacy':
                    parity=out==old
                    assert parity,'Full legacy output drift: '+mid+'/'+mode
                path='runs/'+mid+'/'+mode+'/'+variant+'.json'
                write(output/path,out)
                records.append(dict(market_id=mid,mode=mode,variant=variant,path=path,
                    legacy_full_output_parity=parity,metrics=metrics(out),round_budget=config.round_budget))
        print('Completed full-band factorial:',mid,flush=True)
    totals={}
    for mode in ('fixed','basic','enhanced'):
        for variant in plan['variants']:
            selected=[r for r in records if r['mode']==mode and r['variant']==variant]
            if not selected:continue
            reasons=Counter()
            for row in selected:reasons.update(row['metrics']['recovery_reasons'])
            totals[mode+'/'+variant]=dict(runs=len(selected),**{k:sum(r['metrics'][k] for r in selected)
                for k in ('reads','spent','expansions','contraction_removals','final_directional')},recovery_reasons=dict(reasons))
    summary=dict(status='completed_development_comparison',events=18,documents=356,runs=len(records),
        legacy_full_output_parity=sum(r['legacy_full_output_parity'] is True for r in records),
        records=records,totals=totals,network_requests=0,defaults_changed=False,empirical_calibration=False,
        independent_evaluation_completed=False,accuracy_improvement_verified=False,
        limitations=['All 18 events are development data.','Costs are simulated; observed query timing is separately labelled.',
        'Full-band recovery does not guarantee final retention or semantic correctness.',
        'Strict recovery is an explicit comparator, not a claim that the entire patent is reproduced.',
        'Cost includes simulator request/read reserves in addition to patent span cost.'])
    write(output/'summary.json',summary)
    def table(headers,rows):
        return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</table></div>'
    rows=[[key,value['runs'],value['reads'],round(value['spent'],3),value['expansions'],value['contraction_removals'],value['final_directional']] for key,value in totals.items()]
    focus=[]
    for r in records:
        if r['market_id']=='2354063':
            m=r['metrics'];focus.append([r['mode'],'<a href="'+r['path']+'">'+r['variant']+'</a>',round(r['round_budget'],3),m['expansions'],m['contraction_removals'],m['final_directional'],html.escape(str(m['recovery_reasons']))])
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>整带回收对照与实测观测</title><style>body{margin:0;background:#f0f5f8;color:#192e42;font:16px/1.7 system-ui}main{max-width:1200px;margin:auto;padding:28px}section{background:white;border-radius:14px;padding:24px;margin:20px 0}h1{font-size:30px}h2{font-size:21px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:9px;border-bottom:1px solid #dce4eb;white-space:nowrap}a{color:#096b88}.note{border-left:4px solid #c28823;padding-left:14px}</style><main><h1>整带回收对照与实测观测</h1><p>阶段十四 · 18 个开发事件 / 356 篇有效文档 · 180 次运行</p><section><h2>已补齐的专利对照</h2><p>整带模式要求完整过渡带可执行、损失率达标且净收益非负。预算或归档边界不足时保持窗口，不退为部分回收；冷却期保持原收益估计。回收立即计入当前轮，新的窗口边界用于下一轮检索。</p><p>旧单轮预算20与总预算200/24轮派生的8.333分别比较。固定窗口是对应预算轴的对照。54份原默认输出与阶段十三完整一致。</p><p class="note">默认参数没有替换。这里验证机制差异，没有将开发样本称为独立评价，也没有宣称预测质量提高。</p></section><section><h2>预定对照汇总</h2><p>legacy为原部分带；full_band为整带；derived_budget为按计划轮数派生预算。计数累计18事件，同一文档可在多轮、多策略重复出现。</p>'''+table(['模式 / 配置','运行数','读取','模拟支出','扩窗','收缩移出','最终方向证据'],rows)+'''</section><section><h2>焦点事件逐项检查</h2><p>文档为提交解散议案的程序进展，不构成最终结算证明。点击配置查看逐轮净收益、预算和证据去向。</p>'''+table(['模式','配置','单轮预算','扩窗','收缩移出','最终方向证据','回收判据计数'],focus)+'''</section><section><h2>真实观测与独立评价门槛</h2><p>观测采集与完整标定分别记录。本地归档查询的实际响应时延不能冒充新闻发布者网络接口；配额、事件发生时刻等缺失字段不会用默认值填充。</p><p><a href="../phase14-observations-20261023/summary.json">真实观测采集结果</a> · <a href="../../docs/phase14-delivery.md">标定缺项、独立样本审计与交付状态</a></p><p>独立评价需先冻结有效参数与未暴露事件。本页180次运行均是开发回归，不是新的质量分数。</p></section><section><h2>复核材料</h2><p><a href="summary.json">运行索引</a> · <a href="execution-plan.json">运行前冻结方案</a> · <a href="../../docs/phase14-experiment-check.json">独立核验</a> · <a href="../phase13-chain-20261023/index.html">阶段十三</a></p><p>全程离线，新增模型请求0；原标注与历史结果保留。</p></section></main></html>'''
    (output/'index.html').write_text(page,encoding='utf-8')
    for name,digest in codes.items():assert sha(ROOT/name)==digest,'Code changed during run: '+name
    for name,digest in inputs.items():assert sha(ROOT/name)==digest,name
    write(output/'experiment-manifest.json',dict(artifact_type='phase14_comparison',code_sha256=codes,source_sha256=inputs,
        files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('records','totals','limitations')},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    execute(p.parse_args().output)
