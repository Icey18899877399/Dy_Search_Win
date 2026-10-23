"""Correct target-element audit exports only; preserve complete original artifacts first."""
import argparse,json,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();source=a.source.resolve()
    if not source.is_relative_to(ROOT/'artifacts'):raise ValueError('Only project experiment artifacts')
    manifest=read(source/'manifest.json')
    for n,h in manifest['files'].items():assert sha(source/n)==h
    backup=ROOT/'verification-history'/(source.name+'-before-target-amendment')
    if backup.exists() or (source/'amendment.json').exists():raise ValueError('Already amended or backup exists')
    backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,backup)
    assert sha(source/'manifest.json')==sha(backup/'manifest.json')
    changes=[]
    for taskfile in (source/'inputs/tasks').glob('*/task.json'):
        task=read(taskfile);target=taskfile.parent/'target-elements.json';old=read(target)
        fixed=dict(target_elements=task['target_elements'],element_aliases=task.get('element_aliases',{}),origin=old['origin'])
        if fixed==old:continue
        prior=sha(target);target.write_text(json.dumps(fixed,ensure_ascii=False,indent=2),encoding='utf-8')
        changes.append(dict(path=target.relative_to(source).as_posix(),old_sha256=prior,new_sha256=sha(target),
                            task_sha256=sha(taskfile)))
    amendment=dict(reason='Correct cross-task target-elements audit export; model requests, task.json and predictions unchanged',
        original=str(backup),original_manifest_sha256=sha(backup/'manifest.json'),changes=changes,
        correction_script_sha256=sha(Path(__file__)))
    (source/'amendment.json').write_text(json.dumps(amendment,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest['amendment']='amendment.json'
    manifest['files']={p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file() and p!=source/'manifest.json'}
    (source/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(corrected_exports=len(changes),original_backup=str(backup)),ensure_ascii=False))
if __name__=='__main__':main()
