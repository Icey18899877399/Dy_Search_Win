"""Bounded DeepSeek semantic pilot. Credentials are read only from the environment."""
import argparse
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description='DeepSeek 自动语义抽取、固定样本三方案预测与报告')
    parser.add_argument('--db', type=Path, default=ROOT / 'artifacts/index.sqlite')
    parser.add_argument('--data', type=Path, default=Path(r'D:\agents-main\agents\polymarket\data'))
    parser.add_argument('--cutoff', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=5)
    parser.add_argument('--min-documents', type=int, default=5)
    parser.add_argument('--max-documents', type=int, default=10)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--max-chars', type=int, default=12000)
    parser.add_argument('--max-metadata-age-days', type=float, default=7)
    parser.add_argument('--seed', default='patent-v1')
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--cache', type=Path, default=ROOT / 'artifacts/deepseek-cache')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--repair-policies', action='store_true', help='Enable typed matching, executable grid scheduling and fact_v3 policy')
    parser.add_argument('--prepared-cohort', type=Path)
    parser.add_argument('--matching-policy', choices=['typed_v3','typed_v4','typed_v5'], default='typed_v3')
    args = parser.parse_args(argv)
    from dynamic_retrieval.cli import read_json
    from dynamic_retrieval.data.store import Store
    from dynamic_retrieval.models import Config
    from dynamic_retrieval.semantic import DeepSeekError
    from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
    try:
        config = Config.from_dict(read_json(args.config)) if args.config else Config()
        with Store(args.db) as store:
            summary = run_semantic_pipeline(store, args.data, args.cutoff, args.output,
                count=args.count, min_documents=args.min_documents,
                max_metadata_age_days=args.max_metadata_age_days, seed=args.seed, config=config,
                max_documents=args.max_documents, workers=args.workers, max_chars=args.max_chars,
                model=args.model, cache=args.cache, prepared_cohort=args.prepared_cohort,repair_policies=args.repair_policies,matching_policy=args.matching_policy)
        print(f"{summary['status']}: {summary['completed_tasks']} tasks, {summary['completed_runs']} runs")
        print(args.output.resolve() / 'index.html')
        return 0 if summary['status'] == 'completed_semantic_experiment' else 2
    except (ValueError, OSError, KeyError, sqlite3.Error, DeepSeekError) as exc:
        # Avoid exposing environment credentials through unexpected transport messages.
        parser.exit(2, 'Error: ' + type(exc).__name__ + '; pipeline did not complete.\n')


if __name__ == '__main__':
    raise SystemExit(main())
