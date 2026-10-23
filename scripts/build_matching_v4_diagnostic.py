"""Reproduce label-free v3/v4 diagnostics from the same frozen corpus."""
import hashlib,json,sys
from collections import Counter
from pathlib import Path
from html import escape
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.evidence import prepare_task,extract
from dynamic_retrieval.core import fact_key


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    old=ROOT/'artifacts/remediation-next30-20261022'
    new=ROOT/'artifacts/remediation-v4-next30-20261022'
    for folder in (old,new):
        manifest=read(folder/'manifest.json')
        assert manifest['artifact_type']=='remediation_ablation'
        for name,digest in manifest['files'].items():
            assert sha(folder/name)==digest,(folder,name)
    rows=[];tasks=[]
    plan=read(new/'plan.json')
    for item in plan['tasks']:
        market=item['market_id']
        before=read(old/'runs'/market/'combined/enhanced/result.json')
        after=read(new/'runs'/market/'combined/enhanced/result.json')
        assert before['provenance']==after['provenance']
        assert before['config']==after['config']
        for name in ('task.json','documents.json','annotations.json'):
            assert sha(old/'inputs'/market/name)==sha(new/'inputs'/market/name)
        docs=read(new/'inputs'/market/'documents.json')
        ann=read(new/'inputs'/market/'annotations.json')
        versions={}
        for label,result in [('v3',before),('v4',after)]:
            versions[label]=dict(task=prepare_task(result['task']),
                read_ids={i for r in result['rounds'] for i in r['retrieved_ids']},
                admitted_ids={e['id'] for e in result['evidence']},
                final_ids={e['id'] for e in result['evidence'] if e['in_final_window']},
                threshold=result['config']['admission'])
        for doc in docs:
            pair={label:extract(doc,data['task'],ann) for label,data in versions.items()}
            assert pair['v3']['elements']==pair['v4']['elements']
            assert pair['v3']['support']==pair['v4']['support']
            assert fact_key(pair['v3']['elements'])==fact_key(pair['v4']['elements'])
            if not any(pair['v4']['support']):continue
            row=dict(market_id=market,id=doc['id'],question=after['task']['question'],
                     support=pair['v4']['support'],elements=pair['v4']['elements'],
                     quote=pair['v4']['quote'],fact_key=list(fact_key(pair['v4']['elements'])))
            for label,data in versions.items():
                row[label]=dict(relevance=pair[label]['relevance'],
                    passes_matching=pair[label]['relevance']>=data['threshold'],
                    body_read=doc['id'] in data['read_ids'],
                    admitted_in_saved_run=doc['id'] in data['admitted_ids'],
                    in_final_window=doc['id'] in data['final_ids'],
                    matching_trace=pair[label].get('matching_trace'))
            rows.append(row)
        tasks.append(dict(market_id=market,question=after['task']['question'],
            v3=before['result'],v4=after['result']))
    summary={}
    for version in ('v3','v4'):
        summary[version]={key:sum(r[version][key] for r in rows)
            for key in ('passes_matching','body_read','admitted_in_saved_run','in_final_window')}
        summary[version]['distinct_raw_fact_keys_in_final_window']=len({tuple(r['fact_key']) for r in rows if r[version]['in_final_window']})
    report=dict(status='completed_development_replay',model_requests=0,independent_holdout_claim=False,
        scored=False,tasks=len(tasks),documents_checked=sum(len(read(new/'inputs'/i['market_id']/'documents.json')) for i in plan['tasks']),
        directional_documents=len(rows),summary=summary,
        source_manifests={str(p.relative_to(ROOT)):sha(p) for p in (old/'manifest.json',new/'manifest.json')},
        rejected_v4_reasons=dict(Counter(reason for r in rows for reason in r['v4']['matching_trace']['blockers'])),
        invariants=['identical frozen input and annotation hashes','identical configs','raw elements unchanged','support unchanged','raw fact keys unchanged'],
        limitations=['Development corpus already inspected; not a new holdout.',
                    'Matching is relation to the event, not proof of completion or source truth.',
                    'Current-year time scope is a conservative policy assumption; older context may be excluded.',
                    'Machine support remains unreviewed. Raw fact keys are not independently verified real-world facts.',
                    'No prediction quality score is computed here.'],rows=rows,event_results=tasks)
    out=ROOT/'docs/matching-v4-diagnostic.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    labels={'passes_matching':'通过匹配门槛','body_read':'实际读取','admitted_in_saved_run':'读取且准入','in_final_window':'进入最终窗口','distinct_raw_fact_keys_in_final_window':'最终窗口原始五要素键数'}
    lines=''.join('<tr><td>'+escape(label)+'</td><td>'+str(summary['v3'][key])+'</td><td>'+str(summary['v4'][key])+'</td></tr>' for key,label in labels.items())
    changed=''.join('<tr><td>'+escape(t['question'])+'</td><td>'+escape(str(t['v3']['probabilities']))+'</td><td>'+escape(str(t['v4']['probabilities']))+'</td></tr>' for t in tasks if t['v3']['probabilities']!=t['v4']['probabilities'])
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>五要素匹配 v4 · 同输入回归</title><style>body{max-width:1100px;margin:40px auto;font:16px/1.7 system-ui;color:#183240;padding:20px}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #cbd6dc;padding:10px;text-align:left}h1{font-size:28px}a{color:#087a8e}.note{background:#eef5f6;padding:18px}</style><h1>五要素匹配 v4 · 同输入回归</h1>
<p>30 个原有事件，589 篇冻结文档，33 条具有方向性的机器标注；最终四组合 × 三策略共 360 次运行。新增模型调用为 0。</p>
<p class="note">这是检查过样本后的开发回归，不是独立测试成绩。准入与概率变化不代表预测变准。原始五要素、支持向量、事实键、全文与标注哈希均保持一致。</p>
<table><tr><th>方向性证据指标（33 条分母）</th><th>v3 组合 / 增强策略</th><th>v4 组合 / 增强策略</th></tr>'''+lines+'''</table><h2>发生概率变化的事件</h2><table><tr><th>事件</th><th>v3</th><th>v4</th></tr>'''+changed+'''</table>
<p>匹配轨迹区分同一事件的反向表述、军事进展、解封公开、离职压力。明确主体、客体、地点冲突及时间越界会阻断；未知时间不补造成发布日期。时间范围暂按预测年与冻结截止日界定，旧年背景可能被保守排除。</p>
<p>仍未解决：泛化的政府代表归属、跨句事件参与方关系、复杂复合任务、自然语言相对日期，以及模型支持向量本身的语义可靠性。</p>
<p><a href="matching-v4-diagnostic.json">逐条诊断与源文件哈希</a> · <a href="../artifacts/remediation-v4-next30-20261022/index.html">完整开发消融报告</a> · <a href="http://127.0.0.1:8765/">交互工作台</a></p></html>'''
    (ROOT/'docs/matching-v4-summary.html').write_text(html,encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','event_results')},ensure_ascii=False))
if __name__=='__main__':main()
