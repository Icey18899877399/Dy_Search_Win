"""Server-owned new-event previews and bounded semantic workers."""
from dataclasses import asdict
import hashlib,json,os,re,sys,time,uuid
from pathlib import Path
from .cli import write_json
from .data.store import Store,utc_iso
from .expansion import prepare_expansion,load_expansion
from .models import Config
from .web_catalog import read_json
from .web_jobs import validated_config
MODEL='deepseek-flash'
RAW=Path(r'D:\agents-main\agents\polymarket\data')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class FreshService:
    def __init__(self,root,data_root=None):
        self.root=Path(root).resolve()
        self.data_root=Path(data_root or RAW).resolve()
        self.db=self.root/'artifacts/index.sqlite'
        self.directory=self.root/'.runtime/fresh-previews'
        self.directory.mkdir(parents=True,exist_ok=True)

    def status(self):
        value=dict(available=False,credential_configured=bool(os.environ.get('DEEPSEEK_API_KEY')),
                   model=MODEL,latest_cutoff=None,earliest_cutoff=None)
        try:
            with Store(self.db) as store:
                low,high=store.connection.execute('select min(observed_at),max(observed_at) from tasks').fetchone()
            value.update(available=bool(high),latest_cutoff=high[:10]+'T23:59:59Z' if high else None,earliest_cutoff=low)
        except Exception:
            value['reason']='Local archive index unavailable'
        return value

    def preview(self,payload):
        if not isinstance(payload,dict) or set(payload)-{'cutoff','count','max_documents','config','execution','extraction_mode'}:
            raise ValueError('Only cutoff, count, max_documents, config, execution and extraction_mode are accepted')
        cutoff=utc_iso(payload.get('cutoff'))
        count=payload.get('count',10);max_docs=payload.get('max_documents',20)
        if type(count) is not int or not 1<=count<=20:raise ValueError('count must be 1..20')
        if type(max_docs) is not int or not 12<=max_docs<=40:raise ValueError('max_documents must be 12..40')
        config=validated_config(asdict(Config()),payload.get('config',{}))
        from .semantic_pipeline import execution_modes
        execution,_=execution_modes(payload.get('execution'),config)
        extraction_mode=payload.get('extraction_mode','shared')
        if extraction_mode not in ('shared','on_demand'):raise ValueError('Unknown extraction_mode')
        status=self.status()
        if not status['available']:raise ValueError('Local archive index unavailable')
        if cutoff>utc_iso(status['latest_cutoff']):raise ValueError('Cutoff exceeds available archive date')
        ident=uuid.uuid4().hex;folder=self.directory/ident
        with Store(self.db) as store:
            plan=prepare_expansion(store,self.data_root,cutoff,folder,history=self.root/'artifacts',
                 count=count,max_documents=max_docs,source_cap=3,seed='web-fresh-v1',config=config)
        plan.update(execution=execution,extraction_mode=extraction_mode)
        write_json(folder/'plan.json',plan)
        manifest=read_json(folder/'manifest.json')
        manifest['files']['plan.json']=sha(folder/'plan.json')
        write_json(folder/'manifest.json',manifest)
        cohort=read_json(folder/'cohort.json')
        return dict(preview_id=ident,cutoff=cutoff,requested_count=count,retained_count=len(cohort['selected']),
            max_documents=max_docs,model=MODEL,model_request_upper_bound=sum(len(x['documents']) for x in cohort['selected'])*(3 if extraction_mode=='on_demand' else 1),
            execution=execution,extraction_mode=extraction_mode,
            excluded_event_count=len(plan['excluded_events']),selection_policy=plan['policy'],config=asdict(config),
            tasks=[dict(market_id=i['task']['market_id'],event_id=i['task']['event_id'],question=i['task']['question'],
                documents=len(i['documents']),sampling=i['sampling']) for i in cohort['selected']])

    def freeze(self,preview_id,market_ids,directory):
        if not isinstance(preview_id,str) or not re.fullmatch('[a-f0-9]{32}',preview_id):raise ValueError('Invalid preview identifier')
        if (not isinstance(market_ids,list) or not market_ids or len(market_ids)>20 or
            any(not isinstance(x,str) for x in market_ids) or len(set(market_ids))!=len(market_ids)):
            raise ValueError('Select distinct market IDs')
        source=self.directory/preview_id
        plan=read_json(source/'plan.json')
        cohort,plan=load_expansion(source,plan['cutoff'],Config.from_dict(plan['config']))
        selected=[i for i in cohort['selected'] if i['task']['market_id'] in market_ids]
        if len(selected)!=len(market_ids):raise ValueError('Selection is outside frozen preview')
        cohort['selected']=selected;cohort['requested']=cohort['completed']=len(selected)
        plan['selected']=[i for i in plan['selected'] if i['market_id'] in market_ids]
        plan['retained_tasks']=plan['target_tasks']=len(selected)
        chosen_events={i['task']['event_id'] for i in selected}
        plan['split']['assignments']={k:v for k,v in plan['split']['assignments'].items() if k in market_ids}
        plan['split']['events']={k:v for k,v in plan['split']['events'].items() if k in chosen_events}
        plan['preview_manifest_sha256']=sha(source/'manifest.json')
        folder=Path(directory)/'cohort'
        write_json(folder/'cohort.json',cohort);write_json(folder/'plan.json',plan)
        # load_expansion verifies the exact selected corpus and policy before extraction.
        write_json(folder/'manifest.json',dict(artifact_type='expanded_preparation',
            files={n:sha(folder/n) for n in ('cohort.json','plan.json')}))
        return dict(prepared_cohort=str(folder),config=plan['config'],cutoff=plan['cutoff'],
            execution=plan.get('execution',{}),extraction_mode=plan.get('extraction_mode','shared'),
            model_request_upper_bound=sum(len(i['documents']) for i in selected)*(3 if plan.get('extraction_mode')=='on_demand' else 1),
            db=str(self.db),data_root=str(self.data_root),model=MODEL,matching_policy='typed_v5',
            total_documents=sum(len(i['documents']) for i in selected),
            expected_cohort_manifest_sha256=sha(folder/'manifest.json'),
            preview_id=preview_id,market_ids=sorted(market_ids))

def worker(payload_path,output,client=None):
    from .semantic import DeepSeekClient
    from .semantic_pipeline import run_semantic_pipeline
    payload_path=Path(payload_path);payload=read_json(payload_path)
    directory=payload_path.parent;cohort=Path(payload['prepared_cohort'])
    if sha(cohort/'manifest.json')!=payload['expected_cohort_manifest_sha256']:raise ValueError('Frozen selection changed')
    plan=read_json(cohort/'plan.json')
    if payload.get('execution',{})!=plan.get('execution',{}) or payload.get('extraction_mode','shared')!=plan.get('extraction_mode','shared'):
        raise ValueError('Frozen execution changed')
    state=dict(stage='validating',completed_documents=0,total_documents=payload.get('model_request_upper_bound',payload['total_documents']),
               validated_documents=0,failed_documents=0,completed_runs=0,completed_rounds=0)
    def observe(event):
        state.update(event)
        tmp=directory/'progress.json.tmp';write_json(tmp,state)
        for attempt in range(100):
            try:os.replace(tmp,directory/'progress.json');break
            except PermissionError:
                if attempt==99:raise
                time.sleep(.005)
    # One HTTP attempt per uncached document; explicit retry creates a new job.
    model_client=client
    if model_client is None and payload.get('extraction_mode','shared')=='shared':
        from .call_cost import CallCostLedger
        model_client=DeepSeekClient(cache_dir=Path(output).parents[1]/'deepseek-cache',model=MODEL,max_attempts=1,
            cost_ledger=CallCostLedger(Path(output)/'model-call-attempts.jsonl'))
    with Store(payload['db']) as store:
        summary=run_semantic_pipeline(store,payload['data_root'],payload['cutoff'],Path(output),
            prepared_cohort=cohort,config=Config.from_dict(payload['config']),repair_policies=True,
            execution=payload.get('execution'),extraction_mode=payload.get('extraction_mode','shared'),
            matching_policy=payload.get('matching_policy','typed_v4'),observer=observe,client=model_client,workers=3,max_chars=12000,
            cache=Path(output).parents[1]/'deepseek-cache')
    observe(dict(stage='completed' if summary['status']=='completed_semantic_experiment' else 'partial',
                 completed_runs=summary['completed_runs'],model_usage=summary['llm_preprocessing']))
    return summary

def watch_parent(parent_pid):
    """Stop an orphaned API worker; the handle binds the original Windows process."""
    import threading
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.WaitForSingleObject.restype=wintypes.DWORD
        handle=kernel.OpenProcess(0x00100000,False,parent_pid)
        if not handle:raise ValueError('Cannot observe parent process')
        def watch():
            result=kernel.WaitForSingleObject(handle,0xFFFFFFFF)
            os._exit(3 if result==0 else 4)
    else:
        def watch():
            while True:
                if os.getppid()!=parent_pid:os._exit(3)
                time.sleep(.5)
    threading.Thread(target=watch,daemon=True,name='parent-lifetime').start()

if __name__=='__main__':
    try:
        if len(sys.argv)!=4 or sys.argv[1]!='--worker':raise ValueError('Invalid worker arguments')
        watch_parent(os.getppid())
        worker(sys.argv[2],sys.argv[3])
    except Exception as exc:
        # Never emit exception args: a transport could embed a credential.
        print('Fresh worker failed: '+type(exc).__name__,file=sys.stderr)
        raise SystemExit(2)
