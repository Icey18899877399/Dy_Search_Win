"""Read-only catalog of saved runs and verified frozen replay inputs."""
import hashlib
import json
from pathlib import Path
import threading
from .engine import day, iso
from .models import Config


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()


def safe_file(path, base):
    path=Path(path).resolve(); base=Path(base).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError('File is outside the allowed artifact directory or unavailable')
    return path


def validate_result(value):
    if not isinstance(value,dict): raise ValueError('Invalid result object')
    for name in ('task','config','result','diagnostics','provenance'):
        if not isinstance(value.get(name),dict): raise ValueError('Invalid result '+name)
    task=value['task']; final=value['result']; provenance=value['provenance']
    for key in ('market_id','question','cutoff','outcomes'):
        if key not in task: raise ValueError('Missing task '+key)
    day(task['cutoff']); Config.from_dict(value['config'])
    if not isinstance(value.get('rounds'),list) or not isinstance(value.get('evidence'),list):
        raise ValueError('Missing replay data')
    if not isinstance(task['outcomes'],list) or len(task['outcomes'])<2: raise ValueError('Invalid outcomes')
    for key in ('probabilities','rounds','spent','evidence_count','supporting_evidence_count'):
        if key not in final: raise ValueError('Missing result '+key)
    if not isinstance(provenance.get('inputs'),list) or not isinstance(provenance.get('annotations'),dict):
        raise ValueError('Missing provenance')
    if digest(provenance['inputs'])!=provenance.get('input_sha256') or digest(provenance['annotations'])!=provenance.get('annotation_sha256'):
        raise ValueError('Corrupt provenance fingerprints')
    return value


class Catalog:
    def __init__(self,root):
        self.root=Path(root).resolve(); self.artifacts=self.root/'artifacts'
        self.lock=threading.RLock(); self.entries={}; self.rejected=0
        self.refresh()

    def refresh(self):
        entries={}; rejected=0; replay_cache={}
        if self.artifacts.exists():
            for path in sorted(self.artifacts.rglob('result.json')):
                relative=path.relative_to(self.artifacts)
                if any(x in ('code-archive','code_archive','__pycache__') for x in relative.parts): continue
                try:
                    path=safe_file(path,self.artifacts); value=validate_result(read_json(path))
                    ident=hashlib.sha256(path.relative_to(self.root).as_posix().encode()).hexdigest()[:24]
                    summary=self._summary(ident,path,value)
                    summary['result_integrity']=self._verify_manifest(path)
                    summary['computation_version']=self._computation_version(path)
                    key=(str(path.parent.parent),value['provenance']['input_sha256'],value['provenance']['annotation_sha256'],summary['result_integrity'],digest(value['task']),value['provenance'].get('extraction_mode'))
                    if key not in replay_cache:
                        try:
                            if summary['result_integrity']!='verified_saved_manifest': raise ValueError('Saved result manifest missing; replay disabled')
                            if value['provenance'].get('extraction_mode')=='on_demand':
                                raise ValueError('On-demand runs contain sparse extraction states; frozen replay is disabled to prevent lexical fallback. Saved history and full-text diagnostics remain available.')
                            self._validate_current_inputs(*self._inputs(path,value))
                            replay_cache[key]=(True,'Frozen body and annotation fingerprints verified; runs current engine without model calls.')
                        except (ValueError,OSError,KeyError,TypeError) as exc:
                            replay_cache[key]=(False,str(exc))
                    summary['replay_available'],summary['replay_reason']=replay_cache[key]
                    entries[ident]=(path,summary)
                except (ValueError,OSError,KeyError,TypeError,OverflowError): rejected+=1
        with self.lock: self.entries=entries; self.rejected=rejected

    def _summary(self,ident,path,value):
        task=value['task']; final=value['result']; provenance=value['provenance']
        relative=path.relative_to(self.artifacts)
        return dict(id=ident,question=task['question'],market_id=task['market_id'],event_id=task.get('event_id'),
            cutoff=task['cutoff'],mode=value['config']['mode'],group=path.parent.parent.relative_to(self.artifacts).as_posix(),
            batch=relative.parts[0],rounds=len(value['rounds']),spent=final['spent'],probabilities=final['probabilities'],
            outcomes=task['outcomes'],evidence_count=final['evidence_count'],supporting_evidence_count=final['supporting_evidence_count'],
            data_kind=value['diagnostics'].get('data_kind','historical_archive_unspecified'),
            input_sha256=provenance['input_sha256'],annotation_sha256=provenance['annotation_sha256'],
            config=value['config'],termination_reason=final.get('termination_reason'),cutoff_locked=True,
            replay_engine='current_local_engine',report_available=(path.parent/'report.html').is_file())

    def list(self):
        with self.lock: return dict(runs=[dict(row[1]) for row in self.entries.values()],rejected_count=self.rejected)

    def path(self,ident):
        with self.lock:
            if ident not in self.entries: raise KeyError('Unknown run')
            return safe_file(self.entries[ident][0],self.artifacts)

    def get(self,ident):
        path=self.path(ident); self._verify_manifest(path)
        value=validate_result(read_json(path))
        with self.lock: meta=dict(self.entries[ident][1])
        return dict(run=value,meta=meta)

    def _inputs(self,path,result):
        provenance=result['provenance']; task=result['task']; market=str(task['market_id'])
        # Never resolve user-derived market components as arbitrary filesystem paths.
        if market in ('.','..') or '/' in market or '\\' in market: raise ValueError('Unsafe market identifier')
        records=provenance['inputs']; wanted={str(row['id']):row for row in records}
        candidates=[]
        for ancestor in path.parents:
            if ancestor==self.artifacts.parent: break
            if not ancestor.is_relative_to(self.artifacts): continue
            for folder in (ancestor/'inputs/tasks'/market,ancestor/'inputs'/market,ancestor/'inputs'):
                for filename in ('forecast-documents.json','documents.json'):
                    candidate=folder/filename
                    if candidate.is_file(): candidates.append(candidate)
        if not candidates and str(task['market_id'])=='synthetic-demo':
            from .demo import demo_inputs
            manifest=read_json(safe_file(path.parent/'manifest.json',self.artifacts))
            demo_source=Path(__file__).parent/'demo.py'
            code={k.replace('\\','/'):v for k,v in manifest.get('code_sha256',{}).items()}
            if code.get('src/dynamic_retrieval/demo.py')!=hashlib.sha256(demo_source.read_bytes()).hexdigest():
                raise ValueError('Synthetic fixture source version no longer matches saved manifest')
            candidates.append(demo_inputs()[1])
        if not candidates: raise ValueError('No frozen full-text corpus found; historical replay remains available')
        for candidate in candidates:
            try:
                if not isinstance(candidate,list): self._verify_frozen_file(candidate)
                docs=candidate if isinstance(candidate,list) else read_json(safe_file(candidate,self.artifacts))
                if not isinstance(docs,list): continue
                selected={str(d['id']):d for d in docs if isinstance(d,dict) and str(d.get('id')) in wanted}
                if set(selected)!=set(wanted): continue
                verified=[]
                for ident,record in wanted.items():
                    document=selected[ident]
                    metadata={k:document.get(k) for k in ('id','canonical_url','published_at','observed_at','source_file','source_id')}
                    metadata['published_at']=iso(day(metadata['published_at'])); metadata['observed_at']=iso(day(metadata['observed_at']))
                    metadata['body_sha256']=hashlib.sha256(document.get('text','').encode('utf-8')).hexdigest()
                    if metadata!=record: raise ValueError('Frozen document fingerprint mismatch')
                    if task.get('event_id') and document.get('event_id')!=task['event_id']: raise ValueError('Foreign event document')
                    verified.append(document)
                annotations=provenance['annotations']
                if digest(annotations)!=provenance['annotation_sha256']: raise ValueError('Annotation fingerprint mismatch')
                return task,verified,annotations
            except (ValueError,OSError,KeyError,TypeError): continue
        raise ValueError('Frozen corpus is missing or its content fingerprint does not match the saved run')

    def replay_inputs(self,ident):
        path=self.path(ident)
        if self._verify_manifest(path)!='verified_saved_manifest': raise ValueError('Saved result manifest missing')
        result=validate_result(read_json(path))
        if result['provenance'].get('extraction_mode')=='on_demand':
            raise ValueError('On-demand frozen replay is disabled: unread or failed annotations must not fall back to lexical evidence')
        inputs=self._inputs(path,result)
        self._validate_current_inputs(*inputs)
        return inputs

    def evidence(self,ident,evidence_id):
        result=self.get(ident)['run']
        evidence=next((e for e in result['evidence'] if str(e.get('id'))==evidence_id),None)
        if evidence is None:
            diagnostic=self.diagnostics_evidence(ident)
            evidence=next((e for e in diagnostic['evidence'] if str(e.get('id'))==evidence_id),None)
            if evidence is None: raise KeyError('Unknown evidence')
        document=None
        try:
            _,docs,_=self._inputs(self.path(ident),result)
            document=next((d for d in docs if str(d['id'])==evidence_id),None)
        except (ValueError,OSError): pass
        return dict(evidence=evidence,document=document,full_text_available=document is not None)


    def _verify_manifest(self,path):
        manifest_path=path.parent/'manifest.json'
        if not manifest_path.is_file(): return 'missing_saved_manifest'
        manifest=read_json(safe_file(manifest_path,self.artifacts))
        expected=manifest.get('files',{}).get('result.json')
        if not expected: return 'missing_saved_manifest'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Saved result differs from its manifest fingerprint')
        return 'verified_saved_manifest'

    def diagnostics_evidence(self,ident):
        from .evidence import prepare_task,extract
        origin='current_extraction_diagnostic_not_saved_prediction'
        result=self.get(ident)['run']
        try: task,documents,annotations=self._inputs(self.path(ident),result)
        except (ValueError,OSError) as exc:
            return dict(origin=origin,evidence=[],available=False,reason=str(exc))
        task=prepare_task(task)
        read_ids={str(item) for row in result['rounds'] for item in row.get('retrieved_ids',[])}
        saved_ids={str(item['id']) for item in result['evidence']}
        threshold=result['config']['admission']; rows=[]
        on_demand=result['provenance'].get('extraction_mode')=='on_demand'
        for document in documents:
            error=None
            try:
                if on_demand and document['id'] not in annotations:
                    evidence={k:v for k,v in document.items() if k!='text'}
                    evidence.update(elements={},support=[0]*len(task['outcomes']),quote=None,relevance=None,
                        extraction_method='on_demand_annotation_unavailable',diagnostic_origin=origin,admitted=None,
                        admission_threshold=threshold,read_in_saved_run=str(document['id']) in read_ids,
                        in_saved_evidence=str(document['id']) in saved_ids,diagnostic_error=None,
                        rejection_reason='read_but_no_validated_annotation' if str(document['id']) in read_ids else 'not_read_no_frozen_annotation')
                    rows.append(evidence)
                    continue
                evidence=extract(document,task,annotations,
                    comparison_policy=result['provenance'].get('comparison_policy'),
                    evidence_policy=result['provenance'].get('evidence_policy'))
                admitted=evidence['relevance']>=threshold
                rejection=None if admitted else 'relevance_below_admission_threshold'
            except (ValueError,KeyError,TypeError) as exc:
                evidence=dict(document)
                annotation=annotations.get(document['id']) or {}
                evidence.update(elements=annotation.get('elements'),support=annotation.get('support'),quote=annotation.get('quote'),
                    extraction_method='frozen_annotation_unvalidated_current',relevance=None)
                admitted=None; rejection='current_extraction_validation_failed'; error=str(exc)
            evidence.pop('text',None)
            evidence.update(diagnostic_origin=origin,admitted=admitted,admission_threshold=threshold,
                read_in_saved_run=str(document['id']) in read_ids,in_saved_evidence=str(document['id']) in saved_ids,
                rejection_reason=rejection,diagnostic_error=error)
            rows.append(evidence)
        return dict(origin=origin,evidence=rows,available=True,reason=None)

    def _validate_current_inputs(self,task,documents,annotations):
        from .evidence import prepare_task,extract
        prepared=prepare_task(task)
        for document in documents:
            normalized=dict(document)
            normalized['published_at']=iso(day(document['published_at']))
            normalized['observed_at']=iso(day(document['observed_at']))
            try: extract(normalized,prepared,annotations)
            except (ValueError,KeyError,TypeError) as exc:
                raise ValueError('Current extraction cannot replay this historical annotation: '+str(exc)) from None

    def _verify_frozen_file(self,path):
        path=safe_file(path,self.artifacts)
        for ancestor in path.parents:
            if not ancestor.is_relative_to(self.artifacts): break
            manifest_path=ancestor/'manifest.json'
            if not manifest_path.is_file(): continue
            manifest=read_json(safe_file(manifest_path,self.artifacts))
            files={key.replace('\\','/'):value for key,value in manifest.get('files',{}).items()}
            name=path.relative_to(ancestor).as_posix()
            if name not in files: continue
            if hashlib.sha256(path.read_bytes()).hexdigest()!=files[name]:
                raise ValueError('Frozen document file differs from saved manifest')
            return
        raise ValueError('Frozen document file has no saved manifest binding')

    def _computation_version(self,path):
        manifest_path=path.parent/'manifest.json'
        if not manifest_path.is_file(): return None
        manifest=read_json(safe_file(manifest_path,self.artifacts))
        code={key.replace('\\','/'):value for key,value in manifest.get('code_sha256',{}).items()}
        required=['src/dynamic_retrieval/'+name+'.py' for name in ('engine','core','evidence','matching','models','semantic')]
        if not all(name in code for name in required): return None
        # All saved package modules affect semantics, including evidence policies
        # and adapter/execution code. Historical manifests remain independently bound.
        return digest({name:value for name,value in code.items()
            if name.startswith('src/dynamic_retrieval/') and name.endswith('.py')})

