"""Deterministic evidence-based recommendations, never audience forecasts."""
from datetime import datetime

from . import domain as d


def confirm_region(store, source_ref, region_key, relation, quote, *, manual_confirmation=False):
    source=store.load(source_ref,current=True)['value']
    if source_ref.kind!='source' or source['verification']!='verified' or not quote or quote not in source['text']:
        raise ValueError('NO_EVIDENCE')
    if not manual_confirmation:
        places=region_key.split('/')
        if len(places)>1 and places[-2] not in quote and places[-2].rstrip('市省区') not in quote:
            raise ValueError('AMBIGUOUS_REGION')
        if '朝阳' in quote and not any(city in quote for city in ('长春','北京','辽宁')):
            raise ValueError('AMBIGUOUS_REGION')
        if any(word in quote for word in ('报道机构','机构地址','记者站')):
            raise ValueError('PUBLISHER_IS_NOT_EVENT_REGION')
    return d.MediaRegionEvidence(region_key=region_key,relation=relation,source_ref=source_ref,
        evidence_quote=quote,status='confirmed',confirmed_by=store.actor.user_id).model_dump(mode='json')


def recommend(event, profile, now, *, repeated=False):
    confirmed=[r for r in event.get('regions',[]) if r['status']=='confirmed' and r['relation'] in
               ('local_event','local_rule','national_local_angle','other_region')]
    local=[r for r in confirmed if r['relation'] in ('local_event','local_rule') and any(
           r['region_key']==p or r['region_key'].startswith(p+'/') or p.startswith(r['region_key']+'/')
           for p in profile['regions'])]
    if local: relation=local[0]['relation']
    elif any(r['relation']=='national_local_angle' and r['region_key']=='全国' for r in confirmed): relation='national_local_angle'
    elif confirmed: relation='other_region'
    else: relation='unknown'
    tags=event.get('business_tags',[])
    business=30 if profile['primary_business'] in tags else 15 if set(profile['secondary_business']) & set(tags) else 0
    basis='event_at' if event.get('event_at') else 'published_at' if event.get('published_at') else None
    freshness=0
    if basis:
        time=datetime.fromisoformat(event[basis])
        if time.tzinfo is None: raise ValueError('UTC_DATE_REQUIRED')
        hours=(now-time).total_seconds()/3600
        freshness=15 if 0<=hours<=24 else 10 if 24<hours<=72 else 5 if 72<hours<=168 else 0
    scores={'business':business,'region':{'local_event':25,'local_rule':25,'national_local_angle':15,'other_region':5,'unknown':0}[relation],
            'source':20 if event.get('verified') else 0 if event.get('conflict') else 5,
            'freshness':freshness,'heat':5 if event.get('comparable_heat') and event.get('heat') is not None else 0,
            'novelty':0 if repeated else 5}
    labels={'local_event':'已确认本地事件','local_rule':'已确认本地规则','national_local_angle':'全国规则，可结合服务地区说明',
            'other_region':'外地事件或规则，仅供借鉴','unknown':'地区关系待核'}
    return {'relation':relation,'scores':scores,'total_score':sum(scores.values()),'heat':event.get('heat'),
            'freshness_basis':basis,'reasons':[labels[relation],f'业务匹配 {business}/30',
                '来源可回查' if event.get('verified') else '事实仍需核实',f'时效 {freshness}/15'],
            'audience':profile['audience']}


def save_event(store, value, *, entity_id=None, expected_revision=0):
    event=d.MediaEventInput.model_validate(value)
    source_refs={ref.model_dump_json() for ref in event.source_refs}
    for ref in event.source_refs:
        if ref.kind!='source': raise ValueError('REFERENCE_MISMATCH')
        store.load(ref,current=True)
    for claim in event.claims:
        if claim.source_ref.model_dump_json() not in source_refs: raise ValueError('UNKNOWN_SOURCE')
        source=store.load(claim.source_ref,current=True)['value']
        if claim.evidence_quote not in source['text'] or source['content_scope']=='metadata': raise ValueError('NO_EVIDENCE')
        if claim.status=='confirmed' and source['verification']!='verified': raise ValueError('UNVERIFIED_SOURCE')
    for region in event.regions:
        if region.source_ref.model_dump_json() not in source_refs: raise ValueError('UNKNOWN_SOURCE')
        source=store.load(region.source_ref,current=True)['value']
        if region.evidence_quote not in source['text']: raise ValueError('NO_EVIDENCE')
        if region.status=='confirmed' and (source['verification']!='verified' or region.confirmed_by!=store.actor.user_id):
            raise ValueError('UNCONFIRMED_REGION')
    return store.save('event',event.model_dump(mode='json'),entity_id=entity_id,expected_revision=expected_revision)
