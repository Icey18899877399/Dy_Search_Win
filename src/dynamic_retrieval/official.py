"""Small read-only official API collector; snapshots never enter prediction inputs."""
from datetime import datetime, timezone
import json
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse
from .quality import validate_resolution, validate_final_winner

GAMMA='https://gamma-api.polymarket.com/markets/'
CLOB='https://clob.polymarket.com/markets/'
EVENTS='https://gamma-api.polymarket.com/events/'
RESOLUTIONS='https://data-api.polymarket.com/v2/resolutions?condition='


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Official API redirect rejected')


def get_json(url):
    if not (re.fullmatch(re.escape(GAMMA)+r'\d+',url) or
            re.fullmatch(re.escape(EVENTS)+r'\d+',url) or
            re.fullmatch(re.escape(CLOB)+r'0x[0-9a-fA-F]{64}',url) or
            re.fullmatch(re.escape(RESOLUTIONS)+r'0x[0-9a-fA-F]{64}',url)):
        raise ValueError('Unsupported official endpoint')
    opener=build_opener(NoRedirect())
    request=Request(url,headers={'Accept':'application/json','User-Agent':'PatentResearch/1.0'})
    with opener.open(request,timeout=15) as response:
        if response.geturl()!=url:raise ValueError('Redirect rejected')
        raw=response.read(4_000_001)
        if len(raw)>4_000_000:raise ValueError('Response too large')
        return json.loads(raw)


def collect(task, getter=None, allow_final_winner=False):
    getter=getter or get_json
    snapshot=dict(market_id=str(task['market_id']),gamma=None,resolution=None,urls=[])
    try:
        if not re.fullmatch(r'\d+',snapshot['market_id']):raise ValueError('Invalid market id')
        url=GAMMA+snapshot['market_id'];snapshot['urls'].append(url)
        snapshot['gamma']=getter(url)
        condition=snapshot['gamma'].get('conditionId','')
        if not re.fullmatch(r'0x[0-9a-fA-F]{64}',condition):raise ValueError('Invalid condition id')
        url=RESOLUTIONS+condition;snapshot['urls'].append(url)
        snapshot['resolution']=getter(url)
        if not snapshot['gamma'].get('events'):
            event_id=str(task.get('event_id',''))
            if not re.fullmatch(r'\d+',event_id):raise ValueError('Invalid event id')
            url=EVENTS+event_id;snapshot['urls'].append(url)
            snapshot['event']=getter(url)
        snapshot['fetched_at']=datetime.now(timezone.utc).isoformat()
        snapshot['label']=validate_resolution(task,snapshot['gamma'],snapshot['resolution'],snapshot['fetched_at'],snapshot.get('event'))
        if allow_final_winner and snapshot['label']['status']=='nonbinary_or_missing_payout':
            url=CLOB+condition;snapshot['urls'].append(url)
            snapshot['clob']=getter(url)
            snapshot['fetched_at']=datetime.now(timezone.utc).isoformat()
            snapshot['label']=validate_final_winner(task,snapshot['gamma'],snapshot['resolution'],
                snapshot['clob'],snapshot['fetched_at'],snapshot.get('event'))
    except Exception as exc:
        snapshot['fetched_at']=datetime.now(timezone.utc).isoformat()
        snapshot['label']=dict(market_id=snapshot['market_id'],status='fetch_failed',outcome=None,
                               error_type=type(exc).__name__)
    return snapshot
