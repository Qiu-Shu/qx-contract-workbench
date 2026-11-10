"""Source provenance and health; titles and search snippets remain leads."""
from contextlib import nullcontext
import ipaddress
import json
import socket
from datetime import datetime,timezone
from urllib.parse import urlsplit, urlunsplit

from . import domain as d
from .store import encoded


def canonical_url(value):
    url = urlsplit(value)
    if url.scheme not in ('https','http') or not url.hostname or url.username or url.password:
        raise ValueError('UNSAFE_URL')
    if url.port not in (None,80,443) or any(c in value for c in '\r\n\0\\'):
        raise ValueError('UNSAFE_URL')
    return urlunsplit((url.scheme,url.netloc.lower(),url.path or '/',url.query,''))


def safe_url(value, allowed_hosts, resolver=socket.getaddrinfo):
    value=canonical_url(value); url=urlsplit(value)
    if url.hostname not in allowed_hosts: raise ValueError('HOST_NOT_ALLOWED')
    port=url.port or (443 if url.scheme=='https' else 80)
    ips=list(dict.fromkeys(row[4][0] for row in resolver(url.hostname,port,0,socket.SOCK_STREAM)))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('UNSAFE_ADDRESS')
    return value,ips


class MediaSources:
    def __init__(self,store): self.store=store

    def _save(self,value,*,transaction=None,prior=...):
        value=d.MediaSourceItem.model_validate(value).model_dump(mode='json')
        semantic=lambda item:{k:v for k,v in item.items() if k not in ('fetched_at','verification')}
        with (nullcontext(transaction) if transaction is not None else self.store.db(write=True)) as db:
            matches=[row for row in self.store.list('source',transaction=db) if
                     (value.get('url') and row['value'].get('url')==value['url']) or
                     (not value.get('url') and semantic(row['value'])==semantic(value))]
            current=matches[0] if matches else None
            if prior is not ... and (prior['ref'] if prior else None)!=(current['ref'] if current else None):
                raise ValueError('STALE_SOURCE_REFRESH')
            prior=current
            if prior and semantic(prior['value'])==semantic(value): return d.MediaRevisionRef.model_validate(prior['ref'])
            return self.store.save('source',value,expected_revision=prior['ref']['revision'] if prior else 0,
                                   entity_id=prior['ref']['entity_id'] if prior else None,transaction=db)

    def import_source(self,value):
        value=d.MediaSourceImport.model_validate(value).model_dump(mode='json')
        if value['url']: value['url']=canonical_url(value['url'])
        if value['content_origin']=='metadata' and value['text']: raise ValueError('METADATA_HAS_TEXT')
        scope='excerpt' if value['text'].strip() else 'metadata'
        value.update(content_scope=scope,verification='unverified',fetched_at=None,heat=None,source_id=None)
        return self._save(value)

    def confirm(self,ref):
        row=self.store.load(ref,current=True)
        if row['value']['content_scope']=='metadata' or not row['value']['text'].strip():
            raise ValueError('NO_EVIDENCE')
        return self.store.save('source',{**row['value'],'verification':'verified'},
                               entity_id=ref.entity_id,expected_revision=ref.revision)

    def health(self,source_id):
        with self.store.db() as db:
            row=db.execute('SELECT value FROM media_source_state WHERE workspace_id=? AND owner_user_id=? AND source_id=?',
                (self.store.actor.workspace_id,self.store.actor.user_id,source_id)).fetchone()
            return json.loads(row['value']) if row else None

    def prepare_refresh(self,config,fetch):
        previous=self.health(config['id'])
        if previous and previous['state']=='fresh' and config.get('refresh_minutes',0)>0:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(previous['checked_at'])).total_seconds()
            if 0<=age<config['refresh_minutes']*60:
                return {'config':config,'previous':previous,'state':previous,'cached':True}
        priors=self.store.list('source')
        value=None;prior=None
        try:
            result=fetch(config)  # No transaction is held while fetching/parsing.
            text=result['text'][:20000]
            value=dict(title=result['title'][:20000] or config['id'],url=canonical_url(result['url']),
                       text=text,source_kind=config.get('source_kind','news'),content_origin='fetched_page',
                       content_scope='excerpt' if result.get('truncated') or len(result['text'])>20000 else 'full_text',
                       published_at=result.get('published_at'),event_at=None,verification='unverified',
                       fetched_at=d.utc_stamp(),heat=None,source_id=config['id'])
            if not text.strip(): value['content_scope']='metadata'
            value=d.MediaSourceItem.model_validate(value).model_dump(mode='json')
            prior=next((row for row in priors if row['value'].get('url')==value['url']),None)
            state={'source_id':config['id'],'state':'fresh',
                   'last_success_at':d.utc_stamp(),'checked_at':d.utc_stamp(),'error':None}
        except Exception as error:
            state={**(previous or {}),'source_id':config['id'],'state':'stale' if previous and previous.get('source_ref') else 'error',
                   'checked_at':d.utc_stamp(),'error':type(error).__name__}
        return {'config':config,'previous':previous,'prior':prior,'value':value,'state':state}

    def publish_refresh(self,db,prepared):
        config=prepared['config'];state=prepared['state']
        row=db.execute('SELECT value FROM media_source_state WHERE workspace_id=? AND owner_user_id=? AND source_id=?',
            (self.store.actor.workspace_id,self.store.actor.user_id,config['id'])).fetchone()
        if (json.loads(row['value']) if row else None)!=prepared['previous']: raise ValueError('STALE_SOURCE_REFRESH')
        if prepared.get('cached'): return state
        if state['state']=='fresh':
            ref=self._save(prepared['value'],transaction=db,prior=prepared['prior'])
            state={**state,'source_ref':ref.model_dump()}
        db.execute('INSERT INTO media_source_state VALUES(?,?,?,?) ON CONFLICT(workspace_id,owner_user_id,source_id) DO UPDATE SET value=excluded.value',
                       (self.store.actor.workspace_id,self.store.actor.user_id,config['id'],encoded(state)))
        return state

    def refresh(self,config,fetch):
        prepared=self.prepare_refresh(config,fetch)
        with self.store.db(write=True) as db: return self.publish_refresh(db,prepared)
