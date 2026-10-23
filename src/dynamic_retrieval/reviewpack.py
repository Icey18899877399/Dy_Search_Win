"""Local review packages; drafts never imply human or semantic approval."""
import hashlib
import html
import json
from pathlib import Path
from .cli import market_directory, write_json
from .evidence import prepare_task

ROOT=Path(__file__).resolve().parents[2]
STYLE='''body{margin:0;background:#f5f7f6;color:#183139;font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1100px;margin:auto;padding:32px 24px}h1{font-size:28px}h2{font-size:19px}a{color:#087f70}
.card{background:white;border:1px solid #dce5e7;border-radius:10px;padding:20px;margin:16px 0}
.note{background:#faf5e7;border-left:3px solid #b08935;padding:14px 18px}small{color:#627681}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 system-ui}table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:10px;border-bottom:1px solid #dce5e7}code{overflow-wrap:anywhere}'''


def page(title,body):
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+
            '</style><main><h1>'+html.escape(title)+'</h1>'+body+'</main></html>')


def validate_output(output,data_root=None):
    output=Path(output).resolve()
    if data_root is not None and output.is_relative_to(Path(data_root).resolve()):
        raise ValueError('Output must be outside the read-only raw data directory')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Review output must be a new or empty directory; existing review work is preserved')
    return output


def save_cohort(cohort,output):
    """Refuse to overwrite existing annotation work. Return compact cohort summary."""
    output=validate_output(output,cohort.get('provenance',{}).get('data_root'))
    names=[]
    for item in cohort['selected']:
        names.append(market_directory(item['task']['market_id']))
        if any(a.get('reviewed') is not False for a in item['annotations'].values()):
            raise ValueError('New review packages must contain only explicit reviewed:false drafts')
    if len(names)!=len(set(names)):raise ValueError('Duplicate task output directory')
    output.mkdir(parents=True,exist_ok=True)
    compact={k:v for k,v in cohort.items() if k!='selected'}
    compact['status']='draft_pending_semantic_review'
    compact['selected']=[]
    index_rows=[]
    for item,name in zip(cohort['selected'],names):
        task=item['task'];docs=item['documents'];folder=output/'tasks'/name
        prepared=prepare_task(task)
        rules={k:prepared.get(k,{}) for k in ('target_elements','element_aliases')}
        write_json(folder/'task.json',task)
        write_json(folder/'eligibility.json',item['eligibility'])
        write_json(folder/'task-rules.draft.json',rules)
        write_json(folder/'documents.json',docs)
        write_json(folder/'annotations.json',item['annotations'])
        compact['selected'].append(dict(task=task,eligibility=item['eligibility'],
                                        visible_documents=len(docs),directory='tasks/'+name))
        intro='<p><a href="../../index.html">← 候选清单</a></p><div class="note">待审核：元数据筛选通过不等于语义期限和证据支持已确认。全部标注为 reviewed:false，支持向量 [0,0]；本页不含预测成绩或官方结算真值。</div>'
        intro+='<section class="card"><h2>1. 先核对任务</h2><p>截止：'+html.escape(task['cutoff'])+'</p><pre>'+html.escape(task['description'])+'</pre>'
        intro+='<p>请核对题目期限、结算条件、当前是否仍可预测，再修正 <a href="task-rules.draft.json">目标要素草稿</a>。若期限或状态不一致，排除该任务。</p><details><summary>筛选依据</summary><pre>'+html.escape(json.dumps(item['eligibility'],ensure_ascii=False,indent=2))+'</pre></details></section>'
        intro+='<section class="card"><h2>2. 审核新闻支持度</h2><p>正文共 '+str(len(docs))+' 条。逐条核对原文、事实时间和五要素；支持顺序为 '+html.escape(str(task['outcomes']))+'。只有确认引用确实支持判定后才在 annotations.json 中把该条 reviewed 改为 true。未审核、无关和不确定内容保持弃权。</p><p><a href="annotations.json">待审核标注 JSON</a> · <a href="documents.json">全部版本正文 JSON</a></p></section>'
        cards=[]
        for doc in docs:
            cards.append('<section class="card"><h2>'+html.escape(doc['title'])+'</h2><small>'+html.escape(doc['source_id'])+' · 发布 '+html.escape(doc['published_at'])+' · 观测 '+html.escape(doc['observed_at'])+'</small><p><code>'+html.escape(doc['id'])+'</code></p><p>'+html.escape(doc.get('canonical_url',''))+'</p><details><summary>展开该版本全文（'+str(len(doc['text']))+' 字符）</summary><pre>'+html.escape(doc['text'])+'</pre></details></section>')
        (folder/'review.html').write_text(page(task['question'],intro+''.join(cards)),encoding='utf-8')
        index_rows.append('<tr><td>'+html.escape(task['market_id'])+'</td><td>'+html.escape(task['event_id'])+'</td><td><a href="tasks/'+name+'/review.html">'+html.escape(task['question'])+'</a></td><td>'+str(len(docs))+'</td><td>待审核</td></tr>')
    write_json(output/'cohort.json',compact)
    body='<div class="note">这是正式实验前的候选与标注准备包。所有任务仍需审核语义期限，所有新闻支持度仍待审核；尚未运行带方向性支持的真实预测质量实验。</div>'
    body+='<p>已选 '+str(cohort['completed'])+' / '+str(cohort['requested'])+' 个任务；每个事件最多一个市场。依据截止时可见的 active/closed/end_date、元数据新鲜度和正文数量筛选，未用价格或事后标签挑选任务。</p>'
    body+='<section class="card"><table><thead><tr><th>市场</th><th>事件</th><th>审核入口</th><th>正文数</th><th>状态</th></tr></thead><tbody>'+''.join(index_rows)+'</tbody></table></section>'
    body+='<p><a href="cohort.json">固定候选名单、筛选排除记录与来源指纹</a></p><p>后续顺序：核对任务 → 审核目标要素与支持度 → 同输入三方案重跑 → 核验官方结算 → 独立事件评估。当前不填充或编造缺失的审核与真值。</p>'
    (output/'index.html').write_text(page('真实预测实验 · 待审核准备包',body),encoding='utf-8')
    files={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(output.rglob('*')) if p.is_file()}
    code={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted((ROOT/'src').rglob('*.py'))}
    launcher=ROOT/'prepare_experiment.py'
    if launcher.is_file():code[launcher.name]=hashlib.sha256(launcher.read_bytes()).hexdigest()
    write_json(output/'manifest.json',dict(artifact_type='experiment_preparation',format_version=1,
                                         files=files,code_sha256=code,status=compact['status']))
    return compact
