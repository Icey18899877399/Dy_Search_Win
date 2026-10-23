"""Check actual frozen model-read spans, not hypothetical selected passages."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_source_gaps import witnesses,sha,read,write


def main():
    source=ROOT/'artifacts/temporal-progress-20261023'
    cardsource=ROOT/'artifacts/fact-windows-20261023'
    hashes={}
    for base in (source,cardsource):
        m=read(base/'experiment-manifest.json')
        for name,h in m['files'].items():
            if sha(base/name)!=h:raise ValueError('Frozen input changed: '+name)
        hashes[str(base.relative_to(ROOT)/'experiment-manifest.json')]=sha(base/'experiment-manifest.json')
    cards={x['document_id']:x for x in read(cardsource/'fact-cards.json')}
    rows=[]
    for market in ('1171663','1423716','2354063'):
        for arm in ('head','fact_window_v1'):
            base=source/f'inputs/{market}/{arm}'
            docs=read(base/'documents.json');anns=read(base/'annotations.json')
            for d in docs:
                ann=anns[d['id']];full=d['title']+'\n'+d['text'];offset=len(d['title'])+1
                if hashlib.sha256(d['text'].encode()).hexdigest()!=ann['body_sha256']:raise ValueError('Body hash mismatch')
                if hashlib.sha256(d['title'].encode()).hexdigest()!=ann['title_sha256']:raise ValueError('Title hash mismatch')
                if arm=='head':
                    a,b=0,min(len(full),12000)
                else:
                    if hashlib.sha256(full.encode()).hexdigest()!=ann['context_source_sha256']:raise ValueError('Context hash mismatch')
                    a,b=ann['excerpt_start'],ann['excerpt_end']
                if ann['excerpt']!=full[a:b]:raise ValueError('Frozen excerpt span mismatch')
                snippets=[]
                for p in cards[d['id']]['snippets']:
                    if d['text'][p['start']:p['end']]!=p['text']:raise ValueError('Card span mismatch')
                    lo,hi=p['start']+offset,p['end']+offset
                    snippets.append(dict(body_start=p['start'],body_end=p['end'],text=p['text'],
                        fully_in_model_excerpt=a<=lo and hi<=b,overlap_chars=max(0,min(hi,b)-max(lo,a))))
                mentions=witnesses(d['text'])
                for p in mentions:p['in_model_excerpt']=a<=p['start']+offset and p['end']+offset<=b
                rows.append(dict(market_id=market,document_id=d['id'],title=d['title'],arm=arm,
                    body_sha256=ann['body_sha256'],excerpt_start=a,excerpt_end=b,full_source_chars=len(full),excerpt_chars=b-a,
                    card_passages=snippets,date_and_counter_mentions=mentions,
                    quote=ann['quote'],model_elements=ann['elements'],reviewed=False,
                    scope='actual_frozen_input_visibility_not_proof_of_model_comprehension_or_fact_truth'))
    summary=[]
    for arm in ('head','fact_window_v1'):
        subset=[r for r in rows if r['arm']==arm]
        summary.append(dict(arm=arm,documents=len(subset),card_passages=sum(len(r['card_passages']) for r in subset),
            card_passages_fully_in_excerpt=sum(p['fully_in_model_excerpt'] for r in subset for p in r['card_passages']),
            full_source_in_excerpt=sum(r['excerpt_start']==0 and r['excerpt_end']==r['full_source_chars'] for r in subset)))
    out=ROOT/'docs/source-gaps-extraction-coverage.json'
    write(out,dict(status='verified_frozen_read_spans',model_requests=0,independent_evaluation=False,reviewed=False,
        code_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__),'scripts/audit_source_gaps.py':sha(ROOT/'scripts/audit_source_gaps.py')},
        input_manifests_sha256=hashes,summary=summary,documents=rows,
        limits=['Fact card passages are purposively selected existing snippets, not an exhaustive evidence recall denominator.',
                'Being in the model excerpt proves input visibility only, not correct extraction or complete task satisfaction.']))
    print(json.dumps(summary))

if __name__=='__main__':main()
