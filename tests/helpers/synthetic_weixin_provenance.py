"""Independent SQL archive samples; never evidence of an enabled poll endpoint."""
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.config import canonical_json
from cn_contract.record_codec import sha
from cn_contract.weixin_offline import event_id
from tests.helpers.synthetic_weixin_generation_service import append, request
from tests.helpers.synthetic_weixin_generations import setup_history, state
from tests.integration.test_weixin_dispatch import message


def snapshot(database):
    value=state(database)
    with database.session() as db:
        for name in ('weixin_descriptor_generations','audit_events'):
            value[name]=[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))]
    return value


def insert(db,table,values):
    db.execute(text('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+','.join(':'+key for key in values)+')'),values)


def poll_sample(h,generation,identifier,*,reply=None,sidecar=True,peer=None):
    database=h['database'];mapping=peer or h['mapping']
    with database.session() as db:
        account=db.execute(text('SELECT * FROM weixin_accounts WHERE id=:id'),{'id':str(h['account'].id)}).mappings().one()
        at=generation.created_at+timedelta(microseconds=identifier)
        raw=message(identifier,peer=mapping.sender_peer_id,reply=reply)
        payload=d.TaskInboxEventInput(event_id=event_id(account['bot_account_id'],mapping.sender_peer_id,str(identifier)),
            text=raw['item_list'][0]['text_item']['text'],reply_to_event_id=(
                event_id(account['bot_account_id'],mapping.sender_peer_id,str(reply)) if reply is not None else None))
        poll_id,request_id=uuid4(),uuid4()
        descriptor=d.WeixinInboxDescriptor(id=uuid4(),poll_id=poll_id,ordinal=1,
            sender_peer_id=mapping.sender_peer_id,upstream_message_id=str(identifier),source_event_id=payload.event_id,
            source_sha256=sha(raw),status='accepted_pending_dispatch',mapping_id=mapping.id,payload=payload)
        request=d.WeixinPollInput(request_id=request_id,expected_revision=account['checkpoint_revision'],expected_cursor=account['upstream_cursor'])
        values=dict(id=str(poll_id),account_id=account['id'],request_id=str(request_id),request_sha256=sha(request.model_dump(mode='json')),
            response_sha256=sha(dict(ret=0,msgs=[raw],get_updates_buf='opaque:'+str(account['checkpoint_revision']+1))),
            expected_revision=account['checkpoint_revision'],next_revision=account['checkpoint_revision']+1,
            expected_cursor=account['upstream_cursor'],next_cursor='opaque:'+str(account['checkpoint_revision']+1),
            descriptor_count=1,created_at=at.isoformat().replace('+00:00','Z'),descriptors=[descriptor.model_dump(mode='json')])
        poll=d.WeixinPollReceipt(**values,receipt_sha256=sha(values))
        insert(db,'weixin_poll_receipts',poll.model_dump(mode='json',exclude={'descriptors'}))
        stored=descriptor.model_dump(mode='json',exclude={'payload'});stored['payload_json']=canonical_json(payload.model_dump(mode='json'))
        insert(db,'weixin_inbox_descriptors',stored)
        db.execute(text('UPDATE weixin_accounts SET checkpoint_revision=:revision,upstream_cursor=:cursor WHERE id=:id'),
            {'revision':poll.next_revision,'cursor':poll.next_cursor,'id':account['id']})
        if sidecar:
            record=dict(descriptor_id=str(descriptor.id),generation_id=str(generation.id),generation_sha256=generation.generation_sha256,
                task_binding_id=str(generation.task_binding_id),scope_sha256=generation.scope_sha256,
                payload_sha256=sha(payload.model_dump(mode='json')))
            insert(db,'weixin_descriptor_generations',dict(**record,provenance_sha256=sha(record)))
    return poll,descriptor


def chain(world):
    h=setup_history(world);h['first']=append(h);h['one']=poll_sample(h,h['first'],91)
    h['second']=append(h,request(h,h['first']));h['two']=poll_sample(h,h['second'],92)
    return h
