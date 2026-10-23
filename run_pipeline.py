"""One-command automatic offline pipeline; no human review or external API needed."""
import argparse
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='backslashreplace')
    p=argparse.ArgumentParser(description='自动筛选、抽取、预测、比较和报告')
    p.add_argument('--db',type=Path,default=ROOT/'artifacts/index.sqlite')
    p.add_argument('--data',type=Path,default=Path(r'D:\agents-main\agents\polymarket\data'))
    p.add_argument('--cutoff',required=True);p.add_argument('--count',type=int,default=5)
    p.add_argument('--min-documents',type=int,default=5)
    p.add_argument('--max-metadata-age-days',type=float,default=7)
    p.add_argument('--seed',default='patent-v1');p.add_argument('--config',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        from dynamic_retrieval.pipeline import run_pipeline
        from dynamic_retrieval.data.store import Store
        from dynamic_retrieval.models import Config
        from dynamic_retrieval.cli import read_json
        cfg=Config.from_dict(read_json(args.config)) if args.config else Config()
        with Store(args.db) as store:
            result=run_pipeline(store,args.data,args.cutoff,args.output,count=args.count,
                                min_documents=args.min_documents,max_metadata_age_days=args.max_metadata_age_days,
                                seed=args.seed,config=cfg)
        print(f"{result['status']}: {result['completed_tasks']} tasks, {result['completed_runs']} runs")
        print(args.output.resolve()/'index.html')
        return 0 if result['completed_tasks']==args.count else 2
    except (ValueError,OSError,KeyError,sqlite3.Error) as exc:p.exit(2,f'Error: {exc}\n')


if __name__=='__main__':raise SystemExit(main())
