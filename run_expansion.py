"""Freeze expanded cohorts without model calls or outcome access."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))

def main():
    for s in (sys.stdout,sys.stderr):
        if hasattr(s,'reconfigure'):s.reconfigure(encoding='utf-8',errors='backslashreplace')
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=ROOT/'artifacts/index.sqlite')
    p.add_argument('--data',type=Path,default=Path(r'D:\agents-main\agents\polymarket\data'))
    p.add_argument('--cutoff',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--count',type=int,default=20)
    p.add_argument('--max-documents',type=int,default=20)
    p.add_argument('--source-cap',type=int,default=3)
    p.add_argument('--seed',default='patent-expansion-v1')
    a=p.parse_args()
    from dynamic_retrieval.data.store import Store
    from dynamic_retrieval.expansion import prepare_expansion
    with Store(a.db) as store:
        plan=prepare_expansion(store,a.data,a.cutoff,a.output,count=a.count,max_documents=a.max_documents,source_cap=a.source_cap,seed=a.seed)
    print(f"Frozen {plan['retained_tasks']}/{plan['target_tasks']} new events")
    return 0 if plan['retained_tasks'] else 2
if __name__=='__main__':raise SystemExit(main())
