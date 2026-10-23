"""Post-hoc diagnostics and official-resolution evaluation; never a forecast input."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re


def instant(value):
    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(int(value), timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone required')
    return parsed


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode('utf-8')).hexdigest()


def validate_resolution(task, gamma, response, fetched_at, event=None):
    """Require final on-chain payout evidence exposed by official resolution API.

    outcomePrices and proposed_price are deliberately never used.
    This is official-API verification, not an independent blockchain audit.
    """
    base = dict(market_id=str(task['market_id']), event_id=str(task['event_id']),
                status='unverified', outcome=None, fetched_at=fetched_at,
                evidence_sha256=digest(dict(gamma=gamma, resolution=response, event=event)))
    def reject(status):
        return dict(base, status=status)
    try:
        condition = gamma.get('conditionId', '')
        events = gamma.get('events', [])
        event_matches = base['event_id'] in {str(e['id']) for e in events}
        if event is not None:
            event_matches = (str(event.get('id')) == base['event_id'] and
                any(str(m.get('id')) == base['market_id'] and m.get('conditionId') == condition
                    for m in event.get('markets', [])))
        if (str(gamma.get('id')) != base['market_id'] or
            not re.fullmatch(r'0x[0-9a-fA-F]{64}', condition) or
            not event_matches):
            return reject('identity_mismatch')
        if gamma.get('question', '').strip() != task['question'].strip():
            return reject('definition_changed')
        if task.get('description') and gamma.get('description') != task['description']:
            return reject('definition_changed')
        outcomes = gamma.get('outcomes')
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        if not isinstance(outcomes, list) or len(outcomes) != 2 or {x.casefold() for x in outcomes} != {'yes','no'}:
            return reject('unsupported_outcomes')
        rows = response.get('data')
        if not isinstance(rows, list):
            return reject('invalid_response')
        if not rows:
            return reject('no_resolution_record')
        if len(rows) != 1 or rows[0].get('condition_id') != condition:
            return reject('resolution_identity_mismatch')
        row = rows[0]
        if gamma.get('closed') is not True or row.get('status', '').casefold() != 'resolved':
            return reject('not_final_resolved')
        payouts = row.get('payouts')
        if (not isinstance(payouts, list) or len(payouts) != 2 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in payouts)
            or min(payouts) != 0 or max(payouts) <= 0):
            return reject('nonbinary_or_missing_payout')
        has_transaction = bool(re.fullmatch(r'0x[0-9a-fA-F]{64}', row.get('transaction_hash', '')))
        has_block = type(row.get('resolved_block')) is int and row['resolved_block'] > 0
        if not (has_transaction or has_block):
            return reject('missing_resolution_transaction')
        resolved = instant(row.get('resolved_at'))
        fetched = instant(fetched_at)
        if resolved <= instant(task['cutoff']):
            return reject('resolved_before_prediction')
        if resolved > fetched:
            return reject('resolution_after_observation')
        return dict(base, status='official_resolved',
                    outcome=outcomes[payouts.index(max(payouts))].capitalize(),
                    condition_id=condition, resolved_at=resolved.isoformat(),
                    transaction_hash=row.get('transaction_hash'), resolved_block=row.get('resolved_block'),
                    verification='official_api_terminal_payout_not_price_proxy')
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return reject('invalid_response')


def event_split(tasks, seed='patent-quality-v1'):
    markets = {}
    for task in tasks:
        market, event = str(task['market_id']), str(task.get('event_id', ''))
        if not event or market in markets:
            raise ValueError('Unique market and nonempty event IDs required')
        markets[market] = event
    events = sorted(set(markets.values()), key=lambda e: hashlib.sha256((seed+'\0'+e).encode()).hexdigest())
    size = max(1, min(len(events)-1, math.floor(len(events)*.4))) if len(events)>1 else 0
    groups = {event: 'validation' if i<size else 'test' for i,event in enumerate(events)}
    return dict(seed=seed, policy='event_hash_rank_40pct_validation_v1',
                assignments={m:groups[e] for m,e in sorted(markets.items())},
                events=groups, independent_holdout_claim=False,
                limitation='Existing pilot was already inspected; these are retrospective development partitions.')


def yes_probability(run):
    names = [str(x).casefold() for x in run['task']['outcomes']]
    values = run['result']['probabilities']
    if (len(names) != 2 or set(names) != {'yes','no'} or len(values) != 2 or
        any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in values)
        or abs(sum(values)-1)>1e-8):
        raise ValueError('Invalid binary prediction')
    return values[names.index('yes')]


def binary_metrics(pairs):
    for p,y in pairs:
        if type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1 or type(y) is not int or y not in (0,1):
            raise ValueError('Invalid probability or target')
    n=len(pairs)
    bins=[]
    for i in range(10):
        group=[(p,y) for p,y in pairs if min(9,int(p*10))==i]
        bins.append(dict(lower=i/10,upper=(i+1)/10,n=len(group),
                         mean_probability=sum(p for p,y in group)/len(group) if group else None,
                         observed_yes_rate=sum(y for p,y in group)/len(group) if group else None))
    return dict(n=n,brier=sum((p-y)**2 for p,y in pairs)/n if n else None,
                log_loss=sum(-(y*math.log(max(1e-15,p))+(1-y)*math.log(max(1e-15,1-p))) for p,y in pairs)/n if n else None,
                reliability_bins=bins,
                ece=sum(b['n']*abs(b['mean_probability']-b['observed_yes_rate']) for b in bins if b['n'])/n if n else None,
                log_epsilon=1e-15)


def coverage_diagnostic(task, documents, annotations, config):
    cutoff=instant(task['cutoff'])
    counts=dict(documents=len(documents),initial_window=0,initial_transition_band=0,
                older_than_initial_reach=0,outside_earliest_horizon=0,
                directional_documents=0,directional_outside_initial_reach=0)
    reach=config['initial_window_days']+config['band_days']
    for doc in documents:
        age=(cutoff-instant(doc['published_at'])).total_seconds()/86400
        if age<0:
            raise ValueError('Future document in frozen input')
        if age<=config['initial_window_days']:counts['initial_window']+=1
        elif age<=reach:counts['initial_transition_band']+=1
        else:counts['older_than_initial_reach']+=1
        if age>config['earliest_days']:counts['outside_earliest_horizon']+=1
        if any(annotations.get(doc['id'],{}).get('support',[])):
            counts['directional_documents']+=1
            counts['directional_outside_initial_reach']+=int(age>reach)
    return counts

def validate_final_winner(task,gamma,response,clob,fetched_at,event=None):
    """Optional terminal-winner protocol. Never interprets any price as an outcome.
    This is cross-endpoint official metadata, not a payout or blockchain audit.
    last_update_timestamp bounds the observed final update, not exact resolution time.
    """
    original=validate_resolution(task,gamma,response,fetched_at,event)
    if original['status']!='nonbinary_or_missing_payout':return original
    def reject(reason):return dict(original,status=reason,outcome=None)
    try:
        row=response['data'][0]
        if row.get('payouts') is not None:return reject('conflicting_or_fractional_payout')
        gamma_question=gamma.get('questionID',gamma.get('questionId'))
        question_link=(clob.get('question_id')==row.get('question_id') and
                       (gamma_question is None or gamma_question==clob.get('question_id')))
        negative_risk=gamma.get('negRisk') is True or clob.get('neg_risk') is True
        if negative_risk:
            request=gamma.get('negRiskRequestID',gamma.get('negRiskRequestId'))
            market=gamma.get('negRiskMarketID',gamma.get('negRiskMarketId'))
            question_link=(gamma.get('negRisk') is True and clob.get('neg_risk') is True
                and all(isinstance(v,str) and re.fullmatch(r'0x[0-9a-fA-F]{64}',v)
                        for v in (gamma_question,request,market))
                and gamma_question==clob.get('question_id')
                and request==clob.get('neg_risk_request_id')==row.get('question_id')
                and market==clob.get('neg_risk_market_id'))
        if (clob.get('closed') is not True or clob.get('condition_id')!=gamma['conditionId']
            or clob.get('question')!=task['question']
            or not re.fullmatch(r'0x[0-9a-fA-F]{64}',row.get('question_id',''))
            or not question_link):
            return reject('winner_identity_mismatch')
        outcomes=gamma['outcomes']
        if isinstance(outcomes,str):outcomes=json.loads(outcomes)
        ids=gamma.get('clobTokenIds')
        if isinstance(ids,str):ids=json.loads(ids)
        tokens=clob.get('tokens')
        if (not isinstance(ids,list) or len(ids)!=2 or len(set(ids))!=2 or
            not isinstance(tokens,list) or len(tokens)!=2 or
            {x.get('token_id') for x in tokens}!=set(ids)):
            return reject('winner_token_mismatch')
        mapping=dict(zip(ids,outcomes))
        if any(type(t.get('winner')) is not bool or t.get('outcome')!=mapping[t['token_id']] for t in tokens):
            return reject('invalid_winner_flags')
        winners=[t for t in tokens if t['winner']]
        if len(winners)!=1:return reject('ambiguous_winner')
        if not re.fullmatch(r'0x[0-9a-fA-F]{64}',row.get('transaction_hash','')):
            return reject('missing_resolution_transaction')
        if row.get('resolved_at') is not None:
            resolved=instant(row['resolved_at'])
            if not instant(task['cutoff'])<resolved<=instant(fetched_at):
                return reject('invalid_explicit_resolution_time')
        updated=instant(row['last_update_timestamp'])
        if not instant(task['cutoff'])<updated<=instant(fetched_at):return reject('invalid_final_update_time')
        return dict(original,status='official_resolved',outcome=winners[0]['outcome'].capitalize(),
            verification='official_api_terminal_winner_not_payout_audit',
            terminal_update_at=updated.isoformat(),transaction_hash=row['transaction_hash'],
            condition_id=gamma['conditionId'],
            evidence_sha256=digest(dict(gamma=gamma,resolution=response,clob=clob,event=event)),
            limitation='Terminal update time is not independently verified resolution time.')
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):return reject('invalid_winner_response')
