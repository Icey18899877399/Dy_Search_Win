"""Prepare an offline, label-blind candidate cohort and pending review bundle."""
import argparse
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='backslashreplace')
    p=argparse.ArgumentParser(description='筛选截止时开放的候选市场，导出待审核证据包')
    p.add_argument('--db',type=Path,default=ROOT/'artifacts/index.sqlite')
    p.add_argument('--data',type=Path,default=Path(r'D:\agents-main\agents\polymarket\data'))
    p.add_argument('--cutoff',required=True)
    p.add_argument('--count',type=int,default=5)
    p.add_argument('--min-documents',type=int,default=5)
    p.add_argument('--max-metadata-age-days',type=float,default=7)
    p.add_argument('--seed',default='patent-v1')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        from dynamic_retrieval.reviewpack import validate_output
        validate_output(args.output,args.data)
        if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
            raise ValueError('Output must be new or empty; existing review work is preserved')
        from dynamic_retrieval.preparation import prepare_cohort
        from dynamic_retrieval.reviewpack import save_cohort
        from dynamic_retrieval.data.store import Store
        with Store(args.db) as store:
            cohort=prepare_cohort(store,args.data,args.cutoff,count=args.count,min_documents=args.min_documents,
                                  max_metadata_age_days=args.max_metadata_age_days,seed=args.seed)
        save_cohort(cohort,args.output)
        print(f"Prepared {cohort['completed']}/{cohort['requested']} distinct-event tasks; all semantic review pending")
        print(args.output.resolve()/'index.html')
        return 0 if cohort['completed']==cohort['requested'] else 2
    except (ValueError,OSError,KeyError,sqlite3.Error) as exc:
        p.exit(2,f'Error: {exc}\n')


if __name__=='__main__':raise SystemExit(main())
