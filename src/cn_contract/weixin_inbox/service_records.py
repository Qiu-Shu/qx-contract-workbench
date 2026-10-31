"""Service connection and immutable intake source records; no remote effects."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy import text
from .. import domain as d
from ..assistant import service
from ..config import canonical_json
from ..security import ServiceError
from . import accounts, ingress
from .runtime_records import stable


def bind(actor, workspace_id, bot, peer, database):
    with accounts._transaction(database) as db:
        service._current(actor, db)
        if service._workspace_id(db) != workspace_id:
            raise ServiceError('CROSS_MATTER_DENIED',403)
        row=db.execute(text('SELECT * FROM weixin_accounts WHERE workspace_id=:wid AND bot_account_id=:bot'),
            {'wid':str(workspace_id),'bot':bot}).mappings().first()
        if row:
            account,_=accounts._account(actor,row['id'],db,mode='weixin_personal')
        else:
            account=d.WeixinAccountSnapshot(id=uuid4(),workspace_id=workspace_id,owner_id=actor.user_id,
                bot_account_id=bot,mode='weixin_personal',initial_cursor='',upstream_cursor='',checkpoint_revision=0,
                created_at=service._at())
            ingress._insert('weixin_accounts',account.model_dump(mode='json'),db)
        row=db.execute(text('SELECT * FROM weixin_service_connections WHERE account_id=:id'),{'id':str(account.id)}).mappings().first()
        if row is None:
            row=dict(id=str(stable('connection',account.id)),account_id=str(account.id),workspace_id=str(workspace_id),
                owner_id=str(actor.user_id),peer_id=peer,initial_cursor=account.upstream_cursor,
                cursor=account.upstream_cursor,revision=0,created_at=service._at())
            ingress._insert('weixin_service_connections',row,db)
        if row['owner_id']!=str(actor.user_id) or row['peer_id']!=peer:
            raise ServiceError('CROSS_MATTER_DENIED',403)
        return account,dict(row)


def events(batch_id,db):
    return list(db.execute(text('''SELECT e.* FROM weixin_service_events e JOIN weixin_service_batch_events b
        ON b.event_id=e.id WHERE b.batch_id=:id ORDER BY e.rowid'''),{'id':str(batch_id)}).mappings())


def payload(row):
    value=d.TaskInboxEventInput.model_validate_json(row['payload_json'])
    if service._digest(value.model_dump(mode='json'))!=row['payload_sha256']:
        raise ServiceError('VERSION_CONFLICT',409)
    return value


def collect(connection, values, cursor, db, *, response_sha256, now=None):
    now=now or datetime.now(timezone.utc)
    current=db.execute(text('SELECT * FROM weixin_service_connections WHERE id=:id'),{'id':connection['id']}).mappings().one()
    if current['revision']!=connection['revision']:
        duplicates=all(db.scalar(text('SELECT source_sha256 FROM weixin_service_events WHERE connection_id=:id AND event_id=:event'),
            {'id':connection['id'],'event':request.event_id})==digest for request,digest,_ in values)
        if current['cursor']==cursor and duplicates:
            return []
        raise ServiceError('VERSION_CONFLICT',409)
    added=[]
    for request,digest,media in values:
        old=db.execute(text('SELECT * FROM weixin_service_events WHERE connection_id=:cid AND event_id=:event'),
            {'cid':connection['id'],'event':request.event_id}).mappings().first()
        if old:
            if old['source_sha256']!=digest:
                raise ServiceError('VERSION_CONFLICT',409)
            continue
        identifier=str(stable('service-event',connection['id'],request.event_id))
        ingress._insert('weixin_service_events',dict(id=identifier,connection_id=connection['id'],event_id=request.event_id,
            source_sha256=digest,payload_sha256=service._digest(request.model_dump(mode='json')),
            payload_json=canonical_json(request.model_dump(mode='json')),created_at=now.isoformat()),db)
        for media_id,data in media.items():
            ingress._insert('weixin_service_media',dict(event_id=identifier,media_id=media_id,data=data,
                sha256=hashlib.sha256(data).hexdigest()),db)
        new=any(x in request.text for x in ('新事项','另一个案件','新案件','另一份合同','新业务'))
        from .service_routing import decide,control
        acknowledgement=decide(request.text,[]).action=='ack' and not request.media
        batch=db.execute(text('''SELECT * FROM weixin_service_batches WHERE connection_id=:id
            AND state IN ('collecting','held','clarify','waiting') ORDER BY rowid DESC LIMIT 1'''),
            {'id':connection['id']}).mappings().first()
        if batch and (acknowledgement or new and any(payload(e).text.strip() for e in events(batch['id'],db))):
            batch=None
        if batch is None:
            batch=dict(id=str(uuid4()),connection_id=connection['id'],revision=1,state='collecting',
                deadline=(now+timedelta(seconds=5)).isoformat(),conversation_id=None,draft_id=None,workflow=None,
                decision_json=None,created_at=now.isoformat())
            ingress._insert('weixin_service_batches',batch,db)
        else:
            previous=events(batch['id'],db)
            if (len(previous)>=100 or sum(len(payload(e).media) for e in previous)+len(request.media)>20
                    or sum(len(payload(e).text) for e in previous)+len(request.text)>20000):
                raise ServiceError('FILE_LIMIT',413)
        ingress._insert('weixin_service_batch_events',dict(batch_id=batch['id'],event_id=identifier),db)
        directive=control(request)
        state='held' if directive in {'paused','cancelled'} or batch['state']=='held' and directive!='collecting' else 'collecting'
        immediate=acknowledgement or directive=='collecting' or request.text.strip().rstrip('。！!') in ('开始','开始处理','发送完毕','可以开始')
        db.execute(text('''UPDATE weixin_service_batches SET revision=revision+1,state=:state,deadline=:deadline
            WHERE id=:id'''),{'id':batch['id'],'state':state,
                'deadline':(now+timedelta(seconds=0 if immediate else 5)).isoformat()})
        added.append(identifier)
    receipt=dict(id=str(stable('service-poll',connection['id'],connection['revision']+1)),
        connection_id=connection['id'],revision=connection['revision']+1,
        expected_cursor=connection['cursor'],next_cursor=cursor,
        event_ids_json=canonical_json([str(stable('service-event',connection['id'],request.event_id)) for request,_,_ in values]),
        response_sha256=response_sha256,created_at=now.isoformat())
    ingress._insert('weixin_service_polls',{**receipt,'receipt_sha256':service._digest(receipt)},db)
    db.execute(text('''UPDATE weixin_service_connections SET cursor=:cursor,revision=revision+1
        WHERE id=:id AND revision=:revision'''),{'id':connection['id'],'revision':connection['revision'],'cursor':cursor})
    return added


def claim(connection_id,event_id,key,body,db):
    identifier=stable('service-reply',connection_id,key)
    if db.scalar(text('SELECT 1 FROM weixin_service_outbox WHERE client_id=:id'),{'id':str(identifier)}):
        return None
    ingress._insert('weixin_service_outbox',dict(client_id=str(identifier),connection_id=connection_id,
        source_event_id=str(event_id),result_key=key,payload_sha256=hashlib.sha256(body.encode()).hexdigest(),
        status='unknown',created_at=service._at()),db)
    return identifier


def validate_records(db, *, allowed=True):
    if not db.scalar(text("SELECT 1 FROM sqlite_master WHERE name='weixin_service_connections'")):
        return
    connections={row['id']:row for row in db.execute(text('SELECT * FROM weixin_service_connections')).mappings()}
    if not allowed and connections:
        raise ValueError('SERVICE_RECORDS_NOT_ALLOWED')
    for row in connections.values():
        account=db.execute(text('SELECT * FROM weixin_accounts WHERE id=:id'),{'id':row['account_id']}).mappings().one()
        if (row['workspace_id']!=account['workspace_id'] or row['owner_id']!=account['owner_id']
                or account['mode']!='weixin_personal' or row['id']!=str(stable('connection',account['id']))):
            raise ValueError('SERVICE_CONNECTION_INTEGRITY')
        d._weixin_identity(row['peer_id'])
        polls=list(db.execute(text('SELECT * FROM weixin_service_polls WHERE connection_id=:id ORDER BY revision'),
            {'id':row['id']}).mappings())
        if len(polls)!=row['revision']:
            raise ValueError('SERVICE_POLL_SEQUENCE')
        previous=row['initial_cursor']
        for index,poll in enumerate(polls,1):
            value=dict(poll);digest=value.pop('receipt_sha256')
            if (service._digest(value)!=digest or poll['revision']!=index
                    or poll['id']!=str(stable('service-poll',row['id'],index))
                    or poll['expected_cursor']!=previous):
                raise ValueError('SERVICE_POLL_INTEGRITY')
            for identifier in json.loads(poll['event_ids_json']):
                source=db.execute(text('SELECT connection_id,created_at FROM weixin_service_events WHERE id=:id'),{'id':identifier}).mappings().one()
                if source['connection_id']!=row['id'] or source['created_at']>poll['created_at']:
                    raise ValueError('SERVICE_POLL_SOURCE')
            previous=poll['next_cursor']
        if previous!=row['cursor']:
            raise ValueError('SERVICE_POLL_CURSOR')
    sources={row['id']:row for row in db.execute(text('SELECT * FROM weixin_service_events')).mappings()}
    for row in sources.values():
        event=payload(row)
        if row['event_id']!=event.event_id or row['id']!=str(stable('service-event',row['connection_id'],event.event_id)):
            raise ValueError('SERVICE_EVENT_INTEGRITY')
    for row in db.execute(text('SELECT * FROM weixin_service_media')).mappings():
        event=payload(sources[row['event_id']])
        if not any(m.media_id==row['media_id'] for m in event.media) or hashlib.sha256(row['data']).hexdigest()!=row['sha256']:
            raise ValueError('SERVICE_MEDIA_INTEGRITY')
    batches={row['id']:row for row in db.execute(text('SELECT * FROM weixin_service_batches')).mappings()}
    for row in batches.values():
        linked_events=events(row['id'],db)
        if row['revision']!=1+len(linked_events) or not linked_events:
            raise ValueError('SERVICE_BATCH_REVISION')
        if row['decision_json']:
            d.ServiceRouteDecision.model_validate_json(row['decision_json'])
        if row['conversation_id']:
            owner=db.scalar(text('SELECT owner_id FROM assistant_conversations WHERE id=:id'),{'id':row['conversation_id']})
            if owner!=connections[row['connection_id']]['owner_id']:
                raise ValueError('SERVICE_ROUTE_INTEGRITY')
        for event in linked_events:
            if event['connection_id']!=row['connection_id']:
                raise ValueError('SERVICE_ROUTE_INTEGRITY')
    for row in db.execute(text('SELECT * FROM weixin_service_runs')).mappings():
        batch=batches[row['batch_id']]
        run=db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),{'id':row['business_run_id']}).mappings().one()
        from ..assistant import business
        accepted,result=business._record(run,db)
        draft=db.execute(text('SELECT * FROM task_drafts WHERE id=:id'),{'id':row['draft_id']}).mappings().one()
        source_events=events(batch['id'],db)
        if (row['connection_id']!=batch['connection_id'] or run['conversation_id']!=batch['conversation_id']
                or row['draft_id']!=batch['draft_id'] or result.scope!=d.ScopeSnapshot.model_validate_json(row['scope_json'])
                or row['source_event_id']!=source_events[-1]['id']
                or draft['conversation_id']!=batch['conversation_id'] or draft['revision']<row['draft_revision']
                or row['id']!=str(stable('service-link',batch['id']))
                or accepted.request.request_id!=stable('service-business',batch['id'])
                or row['model_request_id']!=str(stable('service-model',batch['id']))):
            raise ValueError('SERVICE_RUN_INTEGRITY')
        for source in source_events:
            original=payload(source)
            imported=db.execute(text('''SELECT e.* FROM task_inbox_events e JOIN task_draft_events de ON de.event_id=e.id
                WHERE de.draft_id=:draft AND e.event_id=:event'''),{'draft':row['draft_id'],'event':original.event_id}).mappings().one()
            from ..task_drafts.service import _payload
            assigned=_payload(imported)
            if assigned.text!=original.text or {m.media_id for m in assigned.media}!={m.media_id for m in original.media}:
                raise ValueError('SERVICE_TASK_SOURCE_INTEGRITY')
    for row in db.execute(text('SELECT * FROM weixin_service_outbox')).mappings():
        if (sources[row['source_event_id']]['connection_id']!=row['connection_id']
                or row['client_id']!=str(stable('service-reply',row['connection_id'],row['result_key']))):
            raise ValueError('SERVICE_OUTBOX_INTEGRITY')
    from ..assistant.shared_judge import validate_records as validate_judge
    validate_judge(db)
