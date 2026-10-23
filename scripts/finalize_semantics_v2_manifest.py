from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).resolve().parents[1];p=R/'delivery-manifest.json'
backup=R/'.runtime/delivery-manifest-before-semantics-v2.json'
if not backup.exists():shutil.copy2(p,backup)
old=json.loads(p.read_text(encoding='utf-8-sig'));names=set(old.get('files',{}))
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
 files[name]=hashlib.sha256(q.read_bytes()).hexdigest()
old['files']=files;old['semantics_v2_delivery']={'final_artifact':'artifacts/semantics-v2-final-20261023','model_requests':0,'independent_evaluation':False}
p.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert all(hashlib.sha256((R/name).read_bytes()).hexdigest()==digest for name,digest in files.items())
print(json.dumps({'verified_delivery_files':len(files),'status':'passed'}))
