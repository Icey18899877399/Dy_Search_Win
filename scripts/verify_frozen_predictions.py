"""Replay saved valid subsets without API calls; trace directional evidence attrition."""
import argparse,json,sys,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.engine import run,day
from dynamic_retrieval.models import Config
from dynamic_retrieval.evidence import extract,prepare_task
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    src=a.experiment.resolve();summary=read(src/'summary.json');manifest=read(src/'manifest.json')
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((src/name).read_bytes()).hexdigest()==digest,name
    count=0;uniform=0;rows=[]
    for item in summary['tasks']:
        market=item['market_id'];folder=src/'inputs/tasks'/market
        task=read(folder/'task.json');docs=read(folder/'forecast-documents.json')
        annotations=read(src/'runs'/market/'machine-annotations.json')
        for mode in ('fixed','basic','enhanced'):
            original=read(src/'runs'/market/mode/'result.json')
            replay=run(task,docs,Config.from_dict(original['config']),annotations)
            for field in ('result','rounds','evidence','provenance'):
                assert original[field]==replay[field],(market,mode,field)
            assert all(original['diagnostics'][k]==v for k,v in replay['diagnostics'].items()),(market,mode,'engine diagnostics')
            count+=1;uniform+=int(original['result']['probabilities']==[.5,.5])
            read_ids={i for r in original['rounds'] for i in r['retrieved_ids']+r.get('recovered_ids',[])}
            final_ids={d['id'] for d in original['evidence'] if d.get('in_final_window')}
            for doc in docs:
                if not any(annotations[doc['id']]['support']):continue
                evidence=extract(doc,prepare_task(task),annotations)
                age=day(task['cutoff'])-day(doc['published_at'])
                cfg=original['config']
                rows.append(dict(market_id=market,mode=mode,id=doc['id'],title=doc['title'],
                    age_days=age,relevance=evidence['relevance'],admission=cfg['admission'],
                    relevance_pass=evidence['relevance']>=cfg['admission'],
                    initial_zone='window' if age<=cfg['initial_window_days'] else 'band' if age<=cfg['initial_window_days']+cfg['band_days'] else 'history',
                    body_read=doc['id'] in read_ids,in_final_window=doc['id'] in final_ids,
                    before_final_boundary=day(doc['published_at'])<day(original['result']['final_boundary']),
                    support=evidence['support'],target_elements=task['target_elements'],
                    extracted_elements=evidence['elements']))
    report=dict(status='passed',compared_runs=count,uniform_runs=uniform,new_model_calls=0,
                experiment=str(src),source_manifest_sha256=hashlib.sha256((src/'manifest.json').read_bytes()).hexdigest(),
                extraction_status=summary['status'],failed_documents=summary['llm_preprocessing']['failed_documents'],
                directional_paths=rows)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='directional_paths'},ensure_ascii=False))
    for row in rows:
        if row['mode']=='enhanced':print(json.dumps(row,ensure_ascii=False))
if __name__=='__main__':main()
