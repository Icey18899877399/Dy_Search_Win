"""Verify bounded source-gap artifacts and refresh the D-drive delivery manifest."""
from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
base=R/'artifacts/source-gaps-final-20261023';m=read(base/'experiment-manifest.json')
for name,h in m['files'].items():assert sha(base/name)==h,name
for name,h in m['code_sha256'].items():assert sha(R/name)==h,name
for name,h in m['raw_sources_sha256'].items():assert sha(Path('D:/agents-main/agents/polymarket/data')/name)==h,name
coverage=read(R/'docs/source-gaps-extraction-coverage.json')
for name,h in coverage['code_sha256'].items():assert sha(R/name)==h,name
for name,h in coverage['input_manifests_sha256'].items():assert sha(R/name)==h,name
old=read(R/'artifacts/temporal-progress-20261023/experiment-manifest.json')
unchanged={n:h for n,h in old['code_sha256'].items() if n.startswith('src/')}
assert all(sha(R/n)==h for n,h in unchanged.items())
log=(R/'docs/source-gaps-python-tests.log').read_text(encoding='utf8')
assert 'Ran 606 tests' in log and log.rstrip().endswith('OK')
verification=dict(status='passed',python_tests_passed=606,verified_artifact_files=len(m['files']),raw_source_files_verified=len(m['raw_sources_sha256']),
 previous_prediction_source_files_unchanged=len(unchanged),model_requests=0,label_access=False,independent_evaluation=False,
 scope='bounded_source_gap_audit_not_all_saved_forecasts_or_prediction_accuracy',artifact=str(base.relative_to(R)))
(R/'docs/source-gaps-verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
p=R/'delivery-manifest.json';backup=R/'.runtime/delivery-manifest-before-source-gaps.json'
if not backup.exists():shutil.copy2(p,backup)
delivery=read(p);names=set(delivery.get('files',{}))
for folder in ('src','tests','web','docs','scripts','configs','artifacts'):
 for q in (R/folder).rglob('*'):
  if q.is_file():names.add(str(q.relative_to(R)))
for q in R.iterdir():
 if q.is_file():names.add(str(q.relative_to(R)))
files={}
for name in sorted(names):
 q=R/name
 if not q.is_file() or q==p or not q.resolve().is_relative_to(R):continue
 if any(part in {'.runtime','.git','__pycache__','.venv','node_modules'} for part in q.relative_to(R).parts):continue
 if q.name.startswith('.env') or q.name=='audit.json' or q.suffix in {'.pyc','.sqlite','.db','.wal','.shm','.building'}:continue
 files[name]=sha(q)
delivery['files']=files;delivery['source_gap_delivery']=verification
p.write_text(json.dumps(delivery,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
assert all(sha(R/name)==h for name,h in files.items())
print(json.dumps(dict(verification,verified_delivery_files=len(files))))
