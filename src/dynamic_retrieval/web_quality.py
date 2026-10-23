"""Read existing, hash-bound quality reports; never fetch labels or score new jobs."""
import hashlib
import json
from pathlib import Path

def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def _inside(root, path):
    path=path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Artifact path outside allowed directory')
    return path

class QualityCatalog:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.artifacts=self.root/'artifacts'
        self.entries={}
        self.rejected_count=0
        for path in sorted(self.artifacts.glob('*/evaluation-plan.json')):
            try:
                folder=_inside(self.artifacts,path.parent)
                manifest=_read(folder/'manifest.json')
                if manifest.get('artifact_type')!='quality_evaluation':
                    continue
                plan,report=self._verify(folder)
                identity=hashlib.sha256(folder.relative_to(self.root).as_posix().encode()).hexdigest()[:24]
                self.entries[identity]=folder
            except (OSError,ValueError,KeyError,TypeError):
                self.rejected_count+=1

    def _verify(self,folder):
        manifest=_read(folder/'manifest.json')
        for name in ('evaluation-plan.json','report.json','index.html'):
            path=_inside(folder,folder/name)
            if _sha(path)!=manifest['files'][name]:
                raise ValueError('Saved quality report changed')
        plan=_read(folder/'evaluation-plan.json')
        source=_inside(self.artifacts,Path(plan['source_experiment']))
        if _sha(source/'manifest.json')!=plan['source_manifest_sha256']:
            raise ValueError('Quality source no longer matches frozen experiment')
        for name,expected in plan.get('prediction_files',{}).items():
            path=_inside(source,source/name)
            if _sha(path)!=expected:
                raise ValueError('Scored prediction changed')
        report=_read(folder/'report.json')
        if len(report['tasks'])!=report['requested_tasks']:
            raise ValueError('Quality denominator mismatch')
        if sum(t.get('label',{}).get('status')=='official_resolved' for t in report['tasks'])!=report['official_resolved_tasks']:
            raise ValueError('Quality resolved denominator mismatch')
        return plan,report

    def _entry(self,identity):
        if identity not in self.entries:
            raise KeyError('Unknown quality report')
        folder=self.entries[identity]
        plan,report=self._verify(folder)
        meta={key:report.get(key) for key in ('requested_tasks','official_resolved_tasks','label_protocol','metrics','status','evidence_grade_counts','limitations')}
        meta.update(id=identity,batch=folder.name,source_batch=Path(plan['source_experiment']).name,
                    saved_evaluation_only=True,report_url='/api/quality/'+identity+'/report')
        return folder,meta,report

    def list_reports(self):
        rows=[]
        for identity in self.entries:
            try:rows.append(self._entry(identity)[1])
            except (OSError,ValueError,KeyError,TypeError):continue
        return dict(reports=rows,rejected_count=self.rejected_count+len(self.entries)-len(rows))

    def get(self,identity):
        _,meta,report=self._entry(identity)
        return dict(report=report,meta=meta)

    def report_path(self,identity):
        folder,_,_=self._entry(identity)
        return folder/'index.html'
