"""Post-prediction quality diagnostics and optional read-only official resolution fetch."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))

def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='backslashreplace')
    parser=argparse.ArgumentParser(description='冻结预测的覆盖诊断、事件划分与官方结算评价')
    parser.add_argument('--experiment',type=Path,default=ROOT/'artifacts/deepseek-v2-20260515')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fetch-official',action='store_true')
    parser.add_argument('--allow-final-winner',action='store_true',help='Explicit supplementary terminal-winner metadata protocol')
    parser.add_argument('--seed',default='patent-quality-v1')
    args=parser.parse_args()
    from dynamic_retrieval.quality_pipeline import build_quality_report
    try:
        report=build_quality_report(args.experiment,args.output,fetch=args.fetch_official,seed=args.seed,allow_final_winner=args.allow_final_winner)
    except (OSError,ValueError,KeyError) as exc:
        parser.exit(2,'Quality run failed: '+type(exc).__name__+'\n')
    print(f"{report['status']}: {report['official_resolved_tasks']}/{report['requested_tasks']} official outcomes")
    return 2 if report['failed_fetches'] else 0

if __name__=='__main__':raise SystemExit(main())
