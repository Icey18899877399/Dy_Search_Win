"""Offline candidate routing within patent-authorized scopes.

Adapted conceptually from the user's chunk BM25 implementation. No model,
annotation, direction, price, or label enters ranking. Full-text indexing is
explicit offline preprocessing, NOT a paid model read or a measured free service.
"""
from collections import Counter
import math
import re
from .grid_budget import validate_grid_policy, literal_cells

POLICIES=('read_guard_v1','bm25_read_guard_v1')
TOKEN=re.compile(r'[\u3400-\u9fff]|[^\W_]+',re.UNICODE)
# Keep negation words; lexical ranking still cannot establish entailment.
STOP=set('a an the of to in on at by for with from as is are was were be been being this that these those it its and or will would shall should'.split())

def tokens(text):
    return [m.group().casefold() for m in TOKEN.finditer(text) if m.group().casefold() not in STOP]

def validate_retrieval_policy(policy,cfg,budget_policy,grid_policy):
    if policy is None:return None
    if not isinstance(policy,str) or policy not in POLICIES:
        raise ValueError('Unknown retrieval policy')
    if budget_policy!='patent_budget_v1':raise ValueError('retrieval policy requires patent_budget_v1')
    baseline=cfg.total_budget/cfg.rounds
    minimum=cfg.query_cost+cfg.read_cost
    if baseline+1e-12<minimum:raise ValueError('Round budget cannot afford one query and fresh read')
    if cfg.mode=='enhanced':
        if grid_policy is None:raise ValueError('Guarded enhanced retrieval requires patent_grid_v1')
        grid=validate_grid_policy(grid_policy,cfg)
        cells=literal_cells(1,1,grid['width_fraction'],baseline*grid['cap_fraction'],cfg.grid_decay)
        smallest=min(c['budget'] for c in cells)
        if smallest+1e-12<minimum:
            raise ValueError(f'Grid budget {smallest:.6g} cannot afford query and fresh read {minimum:.6g}; '
                             'choose compatible grid width/cap or a declared budget before execution')
    elif cfg.mode=='basic' and baseline*cfg.band_fraction+1e-12<minimum:
        raise ValueError('Probe budget cannot afford query and fresh read')
    return dict(policy=policy,minimum_query_and_fresh_read=minimum,regular_baseline=baseline,
                grid_preflight='passed' if cfg.mode=='enhanced' else 'not_applicable',
                scope='offline_frozen_archive_only',empirical_calibration=False)

class ScopedBM25:
    """Cache local chunks; calculate IDF only over the permitted source/time scope."""
    def __init__(self,task):
        self.query=set(tokens(str(task.get('question',''))+' '+str(task.get('description',''))))
        self.cache={};self.indexed_ids=set();self.chunk_count=0
    def chunks(self,doc):
        key=doc['id']
        if key not in self.cache:
            text=doc.get('text','');matches=list(TOKEN.finditer(text));rows=[]
            for i in range(0,len(matches),320):
                end=min(i+384,len(matches));left=matches[i].start();right=matches[end-1].end()
                ts=tokens(doc.get('title','')+' '+text[left:right])
                rows.append(dict(start_char=left,end_char=right,terms=Counter(ts),length=len(ts)))
                if end==len(matches):break
            if not rows:
                ts=tokens(doc.get('title',''));rows=[dict(start_char=0,end_char=0,terms=Counter(ts),length=len(ts))]
            self.cache[key]=rows;self.indexed_ids.add(key);self.chunk_count+=len(rows)
        return self.cache[key]
    def rank(self,docs):
        rows=[(d,c) for d in docs for c in self.chunks(d)]
        if not rows:return [],{}
        average=sum(c['length'] for _,c in rows)/len(rows);df=Counter()
        for _,c in rows:df.update(c['terms'].keys())
        best={}
        for doc,c in rows:
            score=0.
            for term in sorted(self.query):
                tf=c['terms'][term]
                if tf:
                    idf=math.log1p((len(rows)-df[term]+.5)/(df[term]+.5))
                    score+=idf*tf*2.5/(tf+1.5*(.25+.75*c['length']/max(average,1)))
            item=dict(score=score,start_char=c['start_char'],end_char=c['end_char'])
            if doc['id'] not in best or score>best[doc['id']]['score']:best[doc['id']]=item
        ordered=sorted(docs,key=lambda d:(-best[d['id']]['score'],-d['_day'],str(d['id'])))
        return ordered,best
