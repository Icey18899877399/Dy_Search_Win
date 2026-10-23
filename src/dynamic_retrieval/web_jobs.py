"""Single-worker frozen-input queue. No model client or remote data access."""
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
from .cli import write_json,save_run
from .models import Config
from .web_catalog import read_json,digest,safe_file

ALLOWED_OVERRIDES={'mode','initial_window_days','earliest_days','min_window_days','band_days','grid_days','total_budget','round_budget','rounds'}
TERMINAL={'completed','partial','failed','cancelled'}


def validated_config(base,overrides):
    if not isinstance(overrides,dict) or set(overrides)-ALLOWED_OVERRIDES:
        raise ValueError('Only mode, budget, rounds and window parameters can be changed; cutoff is frozen')
    config=Config.from_dict(dict(base,**overrides))
    if config.rounds>1000 or config.total_budget>100000 or config.earliest_days>36500 or config.grid_days<.01:
        raise ValueError('Configuration exceeds local interactive resource limits')
    return config


def validated_execution(value,config,source=None):
    """Execution options stay outside Config and never accept server file paths."""
    if value is None:
        provenance=(source or {}).get('provenance',{})
        value={}
        if provenance.get('budget_policy') is not None:
            value=dict(budget_policy=provenance['budget_policy'],
                grid_policy=provenance.get('grid_policy') if config.mode=='enhanced' else None,
                source_cost_profile=provenance.get('source_cost_profile',{}).get('profile'))
            if provenance.get('retrieval_policy') is not None:
                value['retrieval_policy']=provenance['retrieval_policy']
        if provenance.get('evidence_policy') is not None:
            value['evidence_policy']=provenance['evidence_policy']
    if not isinstance(value,dict) or set(value)-{'budget_policy','grid_policy','source_cost_profile','retrieval_policy','evidence_policy'}:
        raise ValueError('Unknown execution fields; only budget_policy, grid_policy, source_cost_profile, retrieval_policy and evidence_policy are allowed')
    if value.get('budget_policy') not in (None,'patent_budget_v1'):
        raise ValueError('Unknown budget_policy')
    if value.get('evidence_policy') not in (None,'patent_elements_v1','patent_elements_v2','patent_elements_v3','patent_elements_v4'):
        raise ValueError('Unknown evidence_policy')
    grid=value.get('grid_policy')
    if grid is not None:
        if config.mode!='enhanced' or value.get('budget_policy')!='patent_budget_v1':
            raise ValueError('patent_grid_v1 requires enhanced mode and patent_budget_v1')
        from .grid_budget import validate_grid_policy
        validate_grid_policy(grid,config)
    profile=value.get('source_cost_profile')
    if profile is not None:
        if value.get('budget_policy')!='patent_budget_v1':
            raise ValueError('source_cost_profile requires patent_budget_v1')
        allowed={'version','observations','weights','base_cost','budget_unit','base_time_unit'}
        if not isinstance(profile,dict) or set(profile)-allowed or profile.get('version')!='patent_source_cost_v1':
            raise ValueError('Invalid source_cost_profile JSON object')
        if not isinstance(profile.get('observations'),list) or any(not isinstance(row,dict) for row in profile['observations']):
            raise ValueError('source_cost_profile observations must be an array of objects')
        if not isinstance(profile.get('weights'),dict) or set(profile['weights'])!={'response_latency_seconds','rate_limit_quota','returned_items'}:
            raise ValueError('source_cost_profile weights must name latency, quota and returned items')
        if any(type(w) not in (int,float) or not math.isfinite(w) or w<0 for w in profile['weights'].values()) or not math.isclose(sum(profile['weights'].values()),1.):
            raise ValueError('source_cost_profile weights must be nonnegative and sum to one')
        if type(profile.get('base_cost')) not in (int,float) or not math.isfinite(profile['base_cost']) or profile['base_cost']<=0:
            raise ValueError('source_cost_profile base_cost must be positive and finite')
        if profile.get('budget_unit')!='simulation_units':
            raise ValueError('source_cost_profile budget_unit must be simulation_units')
        if 'base_time_unit' in profile and not isinstance(profile['base_time_unit'],str):
            raise ValueError('source_cost_profile base_time_unit must be a string')
    from .retrieval_policy import validate_retrieval_policy
    validate_retrieval_policy(value.get('retrieval_policy'),config,value.get('budget_policy'),grid)
    # Copy the request and reject NaN even in nested observation metadata.
    try:return json.loads(json.dumps(value,allow_nan=False))
    except (ValueError,TypeError) as exc:raise ValueError('Execution options must contain finite JSON values') from exc


# Only constant, allowlisted validation messages cross the worker boundary.
# Source IDs, observation provenance, paths and arbitrary exception text do not.
VALIDATION_MESSAGES={
    'cost_source_coverage':'来源成本 source_ids 必须与全部可见来源完全一致；请补齐缺失来源并移除多余来源。',
    'cost_cutoff':'来源成本 observed_at 晚于冻结截止时间，拒绝使用未来观测。',
    'cost_duplicate_source':'来源成本包含重复 source_id；每个来源只能有一份观测。',
    'cost_positive':'来源成本必须得到正数 cost_per_day，并使用兼容时间单位。',
    'validation':'冻结执行配置未通过校验，请检查输入配置；未生成有效结果。',
}
for _field in ('rate_limit_quota','response_latency_seconds','returned_items','observation_window',
        'quota_unit','observation_id','provenance','observed_at','interface_id','measurement_kind',
        'weights','base_cost','base_time_unit','budget_unit','observations'):
    VALIDATION_MESSAGES['cost_'+_field]='来源成本 '+_field+' 缺失或无效；请核对测量记录与配置。'


def safe_validation_code(error):
    message=str(error)
    if message.startswith('profile source_ids must match'):return 'cost_source_coverage'
    if message.startswith('observed_at for ') and 'after task cutoff' in message:return 'cost_cutoff'
    if message.startswith('Duplicate source_id:'):return 'cost_duplicate_source'
    if message.startswith('Engine requires positive compatible cost_per_day'):return 'cost_positive'
    for code in VALIDATION_MESSAGES:
        if code.startswith('cost_') and code[5:] in message:return code
    return 'validation'


def frozen_failure_message(directory):
    try:
        code=read_json(safe_file(Path(directory)/'validation-error.json',directory)).get('code')
        if isinstance(code,str) and code in VALIDATION_MESSAGES:return VALIDATION_MESSAGES[code]
    except (OSError,ValueError,AttributeError):pass
    return 'Local worker or result validation failed'


def now(): return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self,root,catalog,start=True):
        self.root=Path(root).resolve(); self.catalog=catalog; self.directory=self.root/'.runtime/web-jobs'
        self.directory.mkdir(parents=True,exist_ok=True)
        self.jobs={}; self.keys={}; self.queue=queue.Queue(); self.lock=threading.RLock()
        self.stopping=False; self.process=None; self.active_id=None
        for path in self.directory.glob('*/job.json'):
            try:
                row=read_json(safe_file(path,self.directory))
                if row['status'] not in TERMINAL:
                    row.update(status='failed',stage='interrupted',error='Service stopped before completion; not resumed automatically',updated_at=now())
                    if row.get('mode')=='fresh_semantic':
                        self._attach_fresh_results(row,self.root/'artifacts/web-semantic'/row['id'])
                    write_json(path,row)
                self.jobs[row['id']]=row
                self.keys[row['idempotency_key']]=row['id']
            except (ValueError,KeyError,OSError): continue
        self.thread=threading.Thread(target=self._work,daemon=True,name='frozen-run-queue') if start else None
        if self.thread: self.thread.start()

    def _save(self,row):
        row['updated_at']=now(); write_json(self.directory/row['id']/'job.json',row)

    def list(self):
        with self.lock: return [self._view(row) for row in sorted(self.jobs.values(),key=lambda x:x['created_at'],reverse=True)]

    def get(self,ident):
        with self.lock:
            if ident not in self.jobs: raise KeyError('Unknown job')
            return self._view(self.jobs[ident])

    def submit(self,source_id,overrides,idempotency_key,*,execution=None):
        if not isinstance(idempotency_key,str) or not 1<=len(idempotency_key)<=128:
            raise ValueError('A nonempty idempotency_key of at most 128 characters is required')
        with self.lock:
            source=self.catalog.get(source_id)['run']; config=validated_config(source['config'],overrides)
            execution=validated_execution(execution,config,source)
            if idempotency_key in self.keys:
                existing=self.jobs[self.keys[idempotency_key]]
                if existing['source_id']!=source_id or existing['overrides']!=overrides or existing.get('execution',{})!=execution: raise ValueError('Idempotency key was already used for a different request')
                return dict(existing)
            if self.stopping: raise ValueError('Service is shutting down')
            if sum(row['status'] in ('queued','running') for row in self.jobs.values())>=20: raise ValueError('Local job queue is full')
            task,docs,annotations=self.catalog.replay_inputs(source_id)
            ident=uuid.uuid4().hex
            row=dict(id=ident,source_id=source_id,status='queued',stage='queued',created_at=now(),updated_at=now(),
                config=asdict(config),overrides=overrides,execution=execution,result_id=None,error=None,mode='frozen_cached_replay',model_requests=0,
                idempotency_key=idempotency_key,input_sha256=source['provenance']['input_sha256'],annotation_sha256=source['provenance']['annotation_sha256'],
                replay_engine='current_local_engine',partial_result_available=False)
            directory=self.directory/ident
            write_json(directory/'payload.json',dict(task=task,documents=docs,annotations=annotations,config=asdict(config),
                source_id=source_id,execution=execution,comparison_policy=None if execution.get('evidence_policy') else source['provenance'].get('comparison_policy'),expected_input_sha256=row['input_sha256'],expected_annotation_sha256=row['annotation_sha256'],
                data_kind=source['diagnostics'].get('data_kind','historical_archive_unspecified')))
            self.jobs[ident]=row; self.keys[idempotency_key]=ident; self._save(row); self.queue.put(ident)
            return dict(row)

    def submit_fresh(self,preview_id,market_ids,idempotency_key):
        if not isinstance(idempotency_key,str) or not 1<=len(idempotency_key)<=128:
            raise ValueError('A nonempty idempotency_key of at most 128 characters is required')
        if not isinstance(market_ids,list) or any(not isinstance(x,str) for x in market_ids):
            raise ValueError('Select market IDs')
        with self.lock:
            if idempotency_key in self.keys:
                existing=self.jobs[self.keys[idempotency_key]]
                if existing.get('preview_id')!=preview_id or existing.get('market_ids')!=sorted(market_ids):
                    raise ValueError('Idempotency key was already used for a different request')
                return self._view(existing)
            if self.stopping:raise ValueError('Service is shutting down')
            if sum(r['status'] in ('queued','running') for r in self.jobs.values())>=20:raise ValueError('Local job queue is full')
            if not os.environ.get('DEEPSEEK_API_KEY'):raise ValueError('Set DEEPSEEK_API_KEY in the server process environment before model extraction')
            ident=uuid.uuid4().hex;directory=self.directory/ident
            payload=self.fresh.freeze(preview_id,market_ids,directory)
            row=dict(id=ident,source_id=None,preview_id=preview_id,market_ids=sorted(market_ids),
                status='queued',stage='queued',created_at=now(),updated_at=now(),config=payload['config'],
                overrides={},result_id=None,result_ids=[],error=None,mode='fresh_semantic',model='deepseek-flash',
                idempotency_key=idempotency_key,total_documents=payload['total_documents'],
                model_request_upper_bound=payload.get('model_request_upper_bound',payload['total_documents']),
                extraction_mode=payload.get('extraction_mode','shared'),execution=payload.get('execution',{}),partial_result_available=False)
            write_json(directory/'payload.json',payload)
            self.jobs[ident]=row;self.keys[idempotency_key]=ident;self._save(row);self.queue.put(ident)
            return self._view(row)

    def cancel(self,ident):
        with self.lock:
            row=self.jobs.get(ident)
            if row is None: raise KeyError('Unknown job')
            if row['status'] in TERMINAL: return dict(row)
            row.update(status='cancelled',stage='cancelled',error=None,
                partial_result_available=False)
            self._save(row)
            if self.active_id==ident and self.process is not None and self.process.poll() is None:
                self.process.terminate()
            return dict(row)

    def _work(self):
        while True:
            ident=self.queue.get()
            if ident is None: return
            with self.lock:
                row=self.jobs[ident]
                if self.stopping or row['status']!='queued': continue
                row.update(status='running',stage='validating'); self._save(row)
            directory=self.directory/ident
            fresh=row.get('mode')=='fresh_semantic'
            output=self.root/'artifacts'/('web-semantic' if fresh else 'web-runs')/ident
            try:
                environment=os.environ.copy()
                if not fresh:environment.pop('DEEPSEEK_API_KEY',None)
                environment.pop('OPENAI_API_KEY',None)
                temp=self.root/'.runtime/tmp'; temp.mkdir(parents=True,exist_ok=True)
                environment.update(TEMP=str(temp),TMP=str(temp),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',
                    PYTHONPATH=str(Path(__file__).resolve().parents[1]))
                with (directory/'worker.log').open('w',encoding='utf-8') as log:
                    with self.lock:
                        if row['status']=='cancelled': continue
                        self.active_id=ident
                        self.process=subprocess.Popen([sys.executable,'-B','-m',('dynamic_retrieval.web_fresh' if fresh else 'dynamic_retrieval.web_jobs'),'--worker',str(directory/'payload.json'),str(output)],
                            cwd=self.root,env=environment,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        row['stage']='extracting' if fresh else 'running_engine'; self._save(row)
                    code=self.process.wait()
                with self.lock:
                    self.process=None; self.active_id=None
                    if row['status']=='cancelled':
                        if fresh:self._attach_fresh_results(row,output)
                        else:self._attach_verified_result(row,output)
                        self._save(row)
                        continue
                    if code!=0: raise ValueError('Worker failed; inspect the local job worker.log')
                    if fresh:
                        summary=read_json(output/'summary.json');manifest=read_json(output/'manifest.json')
                        if hashlib.sha256((output/'summary.json').read_bytes()).hexdigest()!=manifest['files']['summary.json']:
                            raise ValueError('Completed summary integrity failed')
                        self._attach_fresh_results(row,output)
                        if len(row['result_ids'])!=summary['completed_runs']:raise ValueError('Result catalog count mismatch')
                        status='completed' if summary['status']=='completed_semantic_experiment' else 'partial' if row['result_ids'] else 'failed'
                        row.update(status=status,stage=status,model_usage=summary['llm_preprocessing'],
                            error='No validated evidence produced a prediction' if status=='failed' else None)
                        self._save(row)
                        continue
                    row['stage']='saving'; self._save(row)
                    self.catalog.refresh()
                    result_path=output/'result.json'
                    result_id=hashlib.sha256(result_path.relative_to(self.root).as_posix().encode()).hexdigest()[:24]
                    if result_id not in self.catalog.entries: raise ValueError('Completed result failed catalog integrity checks')
                    row.update(status='completed',stage='completed',result_id=result_id)
                    self._save(row)
            except Exception as exc:
                with self.lock:
                    self.process=None; self.active_id=None
                    if row.get('mode')=='fresh_semantic':
                        self._attach_fresh_results(row,output)
                    if row['status']!='cancelled':
                        row.update(status='failed',stage='failed',error=frozen_failure_message(directory) if not fresh else 'Local worker or result validation failed',partial_result_available=bool(row.get('result_ids'))); self._save(row)

    def _attach_fresh_results(self,row,output):
        self.catalog.refresh()
        ids=[ident for ident,(path,_) in self.catalog.entries.items() if path.is_relative_to(output)]
        row['result_ids']=ids
        enhanced=[i for i in ids if self.catalog.entries[i][1]['mode']=='enhanced']
        row['result_id']=(enhanced or ids or [None])[0]
        row['partial_result_available']=bool(ids)

    def _view(self,row):
        value=dict(row)
        value['completed_rounds']=0
        value['total_round_limit']=row['config']['rounds']
        try:
            progress=read_json(self.directory/row['id']/'progress.json')
            value['completed_rounds']=progress['completed_rounds']
            value['last_round']=progress['last_round']
        except (OSError,ValueError,KeyError): pass
        if not value['completed_rounds']:
            trace=self.directory/row['id']/'rounds.jsonl'
            try:
                complete=[]
                for line in trace.read_text(encoding='utf-8').splitlines():
                    try: complete.append(json.loads(line))
                    except ValueError: break
                if complete:
                    value['completed_rounds']=len(complete)
                    value['last_round']=complete[-1]
            except (OSError,UnicodeError): pass
        if row.get('mode')=='fresh_semantic':
            try:
                progress=read_json(self.directory/row['id']/'progress.json')
                for key in ('completed_documents','total_documents','validated_documents','failed_documents',
                            'completed_runs','model_usage','completed_rounds','last_round'):
                    if key in progress:value[key]=progress[key]
                if row['status']=='running':value['stage']=progress.get('stage',row['stage'])
            except (OSError,ValueError):pass
            value['partial_trace_available']=False
            value['progress_available']=False
            return value
        value['partial_trace_available']=value['completed_rounds']>0
        value['progress_available']=value['partial_trace_available']
        return value

    def progress(self,ident):
        job=self.get(ident); rows=[]
        path=self.directory/ident/'rounds.jsonl'
        if path.is_file():
            lines=path.read_text(encoding='utf-8').splitlines()
            for line in lines:
                try: rows.append(json.loads(line))
                except ValueError: break # Cancellation can interrupt the last line write.
        return dict(job=job,trace_only=True,rounds=rows,completed_rounds=len(rows),
            note='Completed round observations only; this trace is not a final prediction or evaluation.')

    def _attach_verified_result(self,row,output):
        try:
            manifest=read_json(output/'manifest.json')
            if hashlib.sha256((output/'result.json').read_bytes()).hexdigest()!=manifest['files']['result.json']: return
            self.catalog.refresh()
            ident=hashlib.sha256((output/'result.json').relative_to(self.root).as_posix().encode()).hexdigest()[:24]
            if ident in self.catalog.entries: row['result_id']=ident
        except (OSError,ValueError,KeyError): pass

    def close(self):
        with self.lock:
            self.stopping=True
            if self.active_id: self.cancel(self.active_id)
        self.queue.put(None)
        if self.thread: self.thread.join(timeout=10)


def worker(payload_path,output):
    from .engine import run
    payload=read_json(payload_path); output=Path(output)
    config=Config.from_dict(payload['config'])
    progress_directory=Path(payload_path).parent
    trace_path=progress_directory/'rounds.jsonl'
    def observed(row):
        with trace_path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            stream.flush()
        temporary=progress_directory/'progress.json.tmp'
        write_json(temporary,dict(completed_rounds=row['round'],last_round=row,updated_at=now()))
        # Windows readers briefly hold a non-delete-sharing handle; retry the
        # atomic replacement rather than failing a deterministic engine run.
        for attempt in range(100):
            try:
                os.replace(temporary,progress_directory/'progress.json')
                break
            except PermissionError:
                if attempt==99: raise
                time.sleep(.005)
    try:
        execution=validated_execution(payload.get('execution'),config)
        # Typed extraction is inherited from the source, never user-controlled.
        if payload.get('comparison_policy')=='typed_v6':execution['comparison_policy']='typed_v6'
        result=run(payload['task'],payload['documents'],config,payload['annotations'],observer=observed,**execution)
    except ValueError as exc:
        code=safe_validation_code(exc)
        write_json(progress_directory/'validation-error.json',dict(code=code,message=VALIDATION_MESSAGES[code]))
        raise
    if result['provenance']['input_sha256']!=payload['expected_input_sha256'] or result['provenance']['annotation_sha256']!=payload['expected_annotation_sha256']:
        raise ValueError('Frozen replay provenance differs from source')
    result['diagnostics'].update(data_kind=payload['data_kind'],web_replay=dict(source_id=payload['source_id'],model_requests=0,
        engine='current_local_engine',cutoff_locked=True,extraction='cached_annotations_or_existing_rules'))
    inputs=output/'inputs'
    write_json(inputs/'task.json',payload['task']); write_json(inputs/'documents.json',payload['documents']); write_json(inputs/'annotations.json',payload['annotations'])
    save_run(result,output)
    manifest=read_json(output/'manifest.json')
    for path in inputs.iterdir(): manifest['files'][path.relative_to(output).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest['web_replay']=result['diagnostics']['web_replay']; write_json(output/'manifest.json',manifest)


if __name__=='__main__':
    if len(sys.argv)!=4 or sys.argv[1]!='--worker': raise SystemExit('Internal worker requires a frozen payload and output directory')
    worker(sys.argv[2],sys.argv[3])



