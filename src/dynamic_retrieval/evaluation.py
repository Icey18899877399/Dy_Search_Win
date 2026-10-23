"""Post-prediction scoring. Stored price proxies are never upgraded to verified truth."""
from collections import Counter
import hashlib
import json


def summarize_comparison(results, labels):
    observed={str(x.get('resolved_outcome','')).casefold() for x in labels}
    observed.discard('')
    status='no_labels' if not observed else 'proxy_only' if len(observed)==1 and observed<={'yes','no'} else 'conflicting_proxies'
    y=1. if observed=={'yes'} else 0. if observed=={'no'} else None
    modes={}
    for mode,result in results.items():
        final=result['result']
        names=[str(x).casefold() for x in result['task']['outcomes']]
        yes_index=names.index('yes') if 'yes' in names else None
        modes[mode]=dict(probabilities=final['probabilities'],spent=final['spent'],rounds=final['rounds'],
                         evidence_count=final['evidence_count'],supporting_evidence_count=final['supporting_evidence_count'],
                         termination_reason=final['termination_reason'],
                         proxy_brier=(final['probabilities'][yes_index]-y)**2 if y is not None and yes_index is not None else None)
    return dict(label_status=status,verified_brier=None,proxy_label_count=len(labels),
                label_records=labels,label_sha256=hashlib.sha256(json.dumps(labels,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest(),
                input_sha256={mode:r.get('provenance',{}).get('input_sha256') for mode,r in results.items()},
                label_types=dict(Counter(str(x.get('resolve_type','unknown')) for x in labels)),
                metric='binary Yes Brier: (p_yes-y)^2; proxy-only, not verified accuracy',modes=modes)
