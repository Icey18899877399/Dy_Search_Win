"""Preserve exact prior run sources before changing shared prediction modules."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'artifacts/code-archive'


def main():
    DEST.mkdir(parents=True,exist_ok=True)
    saved=set()
    manifests=list((ROOT/'artifacts').rglob('manifest.json'))
    manifests+=list((ROOT/'artifacts').rglob('experiment-manifest.json'))
    for manifest_path in manifests:
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        for name,expected in manifest.get('code_sha256',{}).items():
            target=DEST/(expected+'.py')
            if target.exists():
                assert hashlib.sha256(target.read_bytes()).hexdigest()==expected
            else:
                source=(ROOT/name).resolve()
                assert source.is_relative_to(ROOT)
                data=source.read_bytes()
                assert hashlib.sha256(data).hexdigest()==expected, (name,'archive before editing')
                target.write_bytes(data)
            saved.add(expected)
    print(json.dumps({'archived_code_blobs':len(saved)}))


if __name__=='__main__':main()
