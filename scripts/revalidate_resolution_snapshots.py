"""Re-evaluate frozen official snapshots with current explicit terminal-winner protocol."""
import argparse,json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dynamic_retrieval.quality_pipeline import build_quality_report
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--snapshots',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    manifest=json.loads((a.snapshots/'manifest.json').read_text(encoding='utf-8'))
    assert Path(manifest['source_experiment']).resolve()==a.experiment.resolve()
    for name,expected in manifest['files'].items():
        assert hashlib.sha256((a.snapshots/name).read_bytes()).hexdigest()==expected
    def collector(task):
        return json.loads((a.snapshots/'official'/(str(task['market_id'])+'.json')).read_text(encoding='utf-8'))['snapshot']
    report=build_quality_report(a.experiment,a.output,fetch=True,collector=collector,allow_final_winner=True)
    print(json.dumps(dict(status=report['status'],official_resolved_tasks=report['official_resolved_tasks'],source='saved_snapshots_no_new_requests')))
if __name__=='__main__':main()
