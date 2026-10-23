"""Hand-authored synthetic acceptance fixture, never represented as real outcomes."""
from .engine import run
from .models import Config


def demo_inputs():
    task={'market_id':'synthetic-demo','event_id':'synthetic','question':'Will Aurora launch the satellite in 2026?',
          'outcomes':['Yes','No'],'cutoff':'2026-06-20T00:00:00+00:00',
          'target_elements':{'subject':'aurora','action':'launch','object':'satellite','time':'2026'}}
    docs=[];annotations={}
    for i,(date,source,positive) in enumerate([
        ('2026-06-18','Wire A',False),('2026-06-19','Wire B',False),
        ('2026-06-12','Agency',True),('2026-06-13','Wire A',True),
        ('2026-06-11','Observatory',True),('2026-06-08','Agency',True)]):
        text='Aurora launched the satellite in 2026.' if positive else 'Aurora delayed the satellite launch in 2026.'
        ident=f'demo-{i}'
        docs.append(dict(id=ident,event_id='synthetic',source_id=source,provider='synthetic_fixture',
                         title=text,text=text,canonical_url=f'https://example.test/{ident}',
                         published_at=date+'T00:00:00+00:00',observed_at='2026-06-19T12:00:00+00:00'))
        annotations[ident]={'reviewed':True,'elements':{'subject':'aurora','action':'launch' if positive else 'delay',
                                        'object':'satellite','time':'2026'},
                            'support':[1,-1] if positive else [-1,1], 'quote':text}
    return task,docs,annotations


def demo_result(mode='enhanced'):
    task,docs,annotations=demo_inputs()
    cfg=Config(mode=mode,initial_window_days=5,min_window_days=2,earliest_days=30,
               band_days=5,grid_days=5,rounds=12,total_budget=120,round_budget=20,
               high_loss=.15,band_fraction=.3,recovery_fraction=.4)
    result=run(task,docs,cfg,annotations)
    result['diagnostics']['data_kind']='synthetic_hand_annotated_acceptance_fixture'
    return result
