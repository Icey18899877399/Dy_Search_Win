"""Measure bounded read-only local archive queries; do not infer publisher costs.

Elapsed time covers the executed SQLite metadata retrieval and materialization,
not network latency or body decompression. Unknown quota remains None. Historical
logs are audited conservatively; field-name matches alone prove no calibration.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from time import perf_counter_ns
from uuid import uuid4
from .data.store import utc_iso


def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()


def _scope(scope):
    if not isinstance(scope,dict): raise ValueError('scope must be an object')
    for key in ('event_id','market_id','source_id'):
        if not isinstance(scope.get(key),str) or not scope[key].strip():
            raise ValueError(f'{key} must be nonempty')
    cutoff=utc_iso(scope.get('cutoff'))
    days=scope.get('window_days')
    if type(days) not in (int,float) or not math.isfinite(days) or not 0<days<=3660:
        raise ValueError('window_days must be positive and bounded at 3660 days')
    lower=datetime.fromisoformat(cutoff.replace('Z','+00:00'))-timedelta(days=days)
    return dict(scope,cutoff=cutoff,window_start=utc_iso(lower.isoformat()))


def collect_query(query, *, scope, provenance, repeats=3):
    scope=_scope(scope)
    if type(repeats) is not int or not 1<=repeats<=100:
        raise ValueError('repeats must be an integer in [1,100]')
    if not isinstance(provenance,dict) or not provenance:
        raise ValueError('nonempty provenance object required')
    json.dumps(provenance,allow_nan=False)
    rows=[];collection_id=str(uuid4())
    for repeat in range(1,repeats+1):
        started=datetime.now(timezone.utc).isoformat();tick=perf_counter_ns()
        status='success';error=None;count=None;result_hash=None
        try:
            result=list(query())
            elapsed=(perf_counter_ns()-tick)/1_000_000_000
            count=len(result)
            result_hash=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False,
                separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
        except Exception as exc:
            elapsed=(perf_counter_ns()-tick)/1_000_000_000
            status='failed';error=type(exc).__name__;count=None
        ended=datetime.now(timezone.utc).isoformat()
        rows.append(dict(observation_id=f'{collection_id}:{repeat}',collection_id=collection_id,
            repeat_index=repeat,repeat_count=repeats,scope=deepcopy(scope),source_id=scope['source_id'],
            backend='local_archive',measurement_kind='sqlite_metadata_query',
            response_latency_seconds=elapsed,latency_unit='seconds',returned_items=count,
            returned_items_unit='unique_eligible_archived_document_records',rate_limit_quota=None,
            quota_unit=None,quota_status='not_observed',status=status,error_type=error,
            started_at=started,ended_at=ended,result_sha256=result_hash,
            observation_window=f"{scope['window_start']}/{scope['cutoff']}",
            provenance=deepcopy(provenance),empirical_calibration=False,applied=False))
    return rows


class ArchiveQueries:
    """Retrieve latest eligible PIT metadata, then filter source/publication window.

    Source is a publisher identifier in the archive; the service being measured
    is local SQLite. This deliberately excludes labels and network requests.
    """
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.connection=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        self.connection.row_factory=sqlite3.Row
        self.connection.execute('PRAGMA query_only=ON')
    def __enter__(self): return self
    def __exit__(self,*args): self.connection.close()
    def query(self,scope):
        scope=_scope(scope)
        rows=self.connection.execute('''
          SELECT id,canonical_url,source_id,published_at,observed_at,content_hash,event_id,source_file
          FROM (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_id,canonical_url
              ORDER BY observed_at DESC,id ASC) AS rn FROM documents
              WHERE event_id=? AND observed_at<=? AND published_at<=?
                AND has_text=1
                AND lower(scrape_status) NOT LIKE '%fail%'
                AND lower(scrape_status) NOT LIKE '%error%')
          WHERE rn=1 AND source_id=? AND published_at>=? ORDER BY published_at,source_id,id
        ''',(scope['event_id'],scope['cutoff'],scope['cutoff'],scope['source_id'],scope['window_start']))
        return [dict(row) for row in rows]


def prepare_output(output, *, project_root, raw_root):
    output=Path(output).resolve();project=Path(project_root).resolve();raw=Path(raw_root).resolve()
    artifacts=project/'artifacts'
    if output.is_relative_to(raw) or output==artifacts or not output.is_relative_to(artifacts):
        raise ValueError('Output must be a child of project artifacts, outside raw data')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Output must be new or empty; existing artifacts are preserved')
    output.mkdir(parents=True,exist_ok=True)
    return output


def audit_telemetry(raw_root):
    """Read only the named logs, at most 4 MiB each; never emit message contents.

    This is a bounded schema/availability audit, not a claim that absent keywords
    prove a field never existed. Inaccessible files remain explicitly unknown.
    """
    required=['response_latency_seconds','rate_limit_quota','returned_items',
              'first_relevant_evidence_at','event_occurred_at']
    files=[]
    patterns={
        'latency_or_duration':re.compile(r'\b(?:latency|elapsed|duration)\b|耗时',re.I),
        'quota':re.compile(r'\b(?:quota|ratelimit|rate.limit)\b',re.I),
        'returned_count':re.compile(r'\b(?:returned|retrieved|count)\b|返回',re.I),
        'request_identifier':re.compile(r'\brequest[_ -]?id\b',re.I)}
    for name in ('run_log.json','daily_run.log','error.log'):
        path=Path(raw_root)/name
        row=dict(path=str(path),status='uninspected',sha256=None,line_count=None,
                 available_fields=[],candidate_field_lines={},verified_request_observations=0)
        try:
            row['file_bytes']=path.stat().st_size
            if row['file_bytes']>4*1024*1024:
                row['status']='size_limit_not_read';files.append(row);continue
            raw=path.read_bytes();row['sha256']=hashlib.sha256(raw).hexdigest()
            text=raw.decode('utf-8-sig',errors='replace');lines=text.splitlines()
            row.update(status='readable',line_count=len(lines))
            row['candidate_field_lines']={k:[n for n,line in enumerate(lines,1) if p.search(line)]
                                           for k,p in patterns.items()}
            if name.endswith('.json'):
                try:
                    value=json.loads(text);fields=set()
                    def visit(item,depth=0):
                        if depth>6:return
                        if isinstance(item,dict):
                            for key,child in item.items():
                                # Only ordinary schema-like names; no values or arbitrary identifiers.
                                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',key):fields.add(key)
                                visit(child,depth+1)
                        elif isinstance(item,list):
                            for child in item[:1000]:visit(child,depth+1)
                    visit(value);row['available_fields']=sorted(fields)
                    row['schema_scan_bounds']=dict(max_depth=6,max_list_items=1000)
                except json.JSONDecodeError:row['json_status']='invalid_json'
        except FileNotFoundError:row['status']='missing'
        except PermissionError:row['status']='permission_denied'
        except OSError as exc:row.update(status='read_error',error_type=type(exc).__name__)
        files.append(row)
    return dict(files=files,verified_request_observations=0,unverified_required_fields=required,
        status='historical_request_calibration_unverified',empirical_calibration=False,
        reasoning=['Aggregate run counts and log timestamp differences are not per-request latency.',
          'Schema/keyword candidates alone lack request pairing, units, source and quota provenance.',
          'Publication/observation/resolution timestamps are not independent event-occurrence evidence.',
          'Inaccessible files remain unknown; no claim that their contents lack telemetry.'])


def select_sources(documents):
    """At most three IDs ordered by SHA256(source_id UTF-8); content ignored."""
    sources={row['source_id'] for row in documents}
    if any(not isinstance(s,str) or not s for s in sources):
        raise ValueError('source identifiers must be nonempty strings')
    return sorted(sources,key=lambda s:(hashlib.sha256(s.encode('utf-8')).hexdigest(),s))[:3]
