"""Localhost-only stdlib HTTP boundary for artifact browsing and frozen runs."""
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit,unquote
from .web_catalog import Catalog,safe_file
from .web_jobs import JobManager


class Handler(BaseHTTPRequestHandler):
    server_version='FrozenResearch/1.0'

    def log_message(self,format,*args):
        # Request URLs may include source text. Do not persist user-controlled request logs.
        pass

    def _trusted(self,mutating=False):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        host=self.headers.get('Host','')
        if host not in allowed: return False
        origin=self.headers.get('Origin')
        if origin is not None and origin not in {'http://'+host}: return False
        if self.headers.get('Sec-Fetch-Site') in ('cross-site','same-site'): return False
        if mutating and not hmac.compare_digest(self.headers.get('X-Run-Token',''),self.server.token): return False
        return True

    def _send(self,status,payload,content_type='application/json; charset=utf-8',filename=None,report=False):
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8') if content_type.startswith('application/json') else payload
        self.send_response(status)
        self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'"+(" 'unsafe-inline'" if report else '')+"; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if filename: self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def _file(self,path,base,filename=None,report=False):
        path=safe_file(path,base)
        content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if path.suffix in ('.js','.mjs'): content_type='text/javascript'
        if content_type.startswith('text/'): content_type+='; charset=utf-8'
        self._send(200,path.read_bytes(),content_type,filename,report)

    def do_GET(self):
        if not self._trusted(): return self._send(403,{'error':'Untrusted local request origin or host'})
        try:
            path=unquote(urlsplit(self.path).path)
            if '\\' in path or any(p in ('.','..') for p in path.split('/')): return self._send(404,{'error':'Not found'})
            if path=='/api/fresh/status': return self._send(200,self.server.fresh.status())
            if path=='/api/session': return self._send(200,dict(token=self.server.token))
            if path=='/api/catalog': return self._send(200,self.server.catalog.list())
            if path=='/api/jobs': return self._send(200,dict(jobs=self.server.jobs.list()))
            match=re.fullmatch(r'/api/jobs/([a-f0-9]{32})/progress',path)
            if match: return self._send(200,self.server.jobs.progress(match[1]),filename='round-trace-'+match[1]+'.json')
            match=re.fullmatch(r'/api/jobs/([a-f0-9]{32})',path)
            if match: return self._send(200,dict(job=self.server.jobs.get(match[1])))
            if path=='/api/quality': return self._send(200,self.server.quality.list_reports())
            match=re.fullmatch(r'/api/quality/([A-Za-z0-9_-]+)(/report)?',path)
            if match:
                if match[2]: return self._file(self.server.quality.report_path(match[1]),self.server.root/'artifacts',report=True)
                return self._send(200,self.server.quality.get(match[1]))
            match=re.fullmatch(r'/api/runs/([a-f0-9]{24})(?:/(export|report|evidence|diagnostics-evidence)(?:/([^/]+))?)?',path)
            if match:
                ident,action,evidence_id=match.groups()
                if action=='diagnostics-evidence': return self._send(200,self.server.catalog.diagnostics_evidence(ident))
                if action=='evidence' and evidence_id: return self._send(200,self.server.catalog.evidence(ident,evidence_id))
                if action=='export': return self._send(200,self.server.catalog.get(ident)['run'],filename='run-'+ident+'.json')
                if action=='report': return self._file(self.server.catalog.path(ident).parent/'report.html',self.server.root/'artifacts',report=True)
                if action is None: return self._send(200,self.server.catalog.get(ident))
            if path.startswith('/api/'): return self._send(404,{'error':'Not found'})
            relative='index.html' if path=='/' else path.lstrip('/')
            return self._file(self.server.root/'web'/relative,self.server.root/'web')
        except KeyError: self._send(404,{'error':'Not found'})
        except (ValueError,OSError,TypeError): self._send(404,{'error':'Artifact unavailable or invalid'})

    def do_POST(self):
        if not self._trusted(mutating=True): return self._send(403,{'error':'Valid same-origin session token required'})
        try:
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self._send(415,{'error':'JSON required'})
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>65536: return self._send(413,{'error':'Request too large'})
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise ValueError('JSON object required')
            path=urlsplit(self.path).path
            if path=='/api/fresh/preview':
                return self._send(200,self.server.fresh.preview(payload))
            if path=='/api/fresh/jobs':
                if set(payload)-{'preview_id','market_ids','idempotency_key'}:raise ValueError('Unknown request fields')
                return self._send(202,dict(job=self.server.jobs.submit_fresh(payload.get('preview_id'),payload.get('market_ids'),payload.get('idempotency_key'))))
            if path=='/api/jobs':
                if set(payload)-{'source_id','config','idempotency_key','execution'}: raise ValueError('Unknown request fields')
                if not isinstance(payload.get('source_id'),str): raise ValueError('source_id required')
                job=self.server.jobs.submit(payload['source_id'],payload.get('config',{}),payload.get('idempotency_key'),execution=payload.get('execution'))
                return self._send(202,dict(job=job))
            match=re.fullmatch(r'/api/jobs/([a-f0-9]{32})/cancel',path)
            if match: return self._send(200,dict(job=self.server.jobs.cancel(match[1])))
            self._send(404,{'error':'Not found'})
        except KeyError: self._send(404,{'error':'Unknown run or job'})
        except (ValueError,TypeError,UnicodeError) as exc: self._send(400,{'error':str(exc)})
        except OSError: self._send(500,{'error':'Local artifact write failed'})


class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True


def create_server(root,port=8765):
    from .web_quality import QualityCatalog
    root=Path(root).resolve()
    server=LocalServer(('127.0.0.1',port),Handler)
    server.root=root; server.token=secrets.token_urlsafe(32)
    server.catalog=Catalog(root); server.quality=QualityCatalog(root)
    from .web_fresh import FreshService
    server.fresh=FreshService(root)
    server.jobs=JobManager(root,server.catalog)
    server.jobs.fresh=server.fresh
    return server



