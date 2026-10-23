"""Publish this built project to the user-selected folder, with no deletion.

Source files are compared by SHA-256; unrelated existing destination files are not
overwritten. The target's independently built archive index and audit are preserved.
"""
import hashlib
import json
from pathlib import Path
import shutil

SOURCE=Path(__file__).resolve().parents[1]
TARGET=Path(r'D:\27专利\事件预测动态检索窗口')


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    target=TARGET.resolve()
    if target!=TARGET or SOURCE==target:raise RuntimeError('Unexpected publication location')
    target.mkdir(parents=True,exist_ok=True)
    manifest_path=target/'delivery-manifest.json'
    old=json.loads(manifest_path.read_text(encoding='utf-8'))['files'] if manifest_path.exists() else {}
    files={}
    for source in sorted(SOURCE.rglob('*')):
        if not source.is_file():continue
        rel=source.relative_to(SOURCE)
        if any(x in ('.git','__pycache__','.venv') for x in rel.parts):continue
        if '.building' in source.name or source.suffix in ('.pyc','.sqlite') or source.name in ('audit.json','delivery-manifest.json'):continue
        destination=target/rel
        if not destination.resolve().is_relative_to(target):raise RuntimeError('Output path escapes target')
        sha=digest(source)
        if destination.exists() and digest(destination)!=sha:
            if str(rel) not in old or digest(destination)!=old[str(rel)]:
                raise RuntimeError(f'Refusing to replace unowned destination: {destination}')
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        if digest(destination)!=sha:raise RuntimeError(f'Copy verification failed: {destination}')
        files[str(rel)]=sha
    manifest_path.write_text(json.dumps({'files':files,'verified_file_count':len(files)},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'target':str(target),'verified_files':len(files)},ensure_ascii=False))


if __name__=='__main__':main()
