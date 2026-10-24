"""Independent fictional SQL history; this is not a runtime ingress implementation."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.config import canonical_json
from cn_contract.record_codec import sha
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_offline import event_id


TABLES = ('weixin_accounts','weixin_peer_bindings','weixin_poll_receipts','weixin_inbox_descriptors')


def snapshot(db):
    return {table:[tuple(row) for row in db.execute(text('SELECT * FROM '+table+' ORDER BY rowid'))]
            for table in TABLES}


def insert(db, table, values):
    db.execute(text('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+
        ','.join(':'+key for key in values)+')'), values)


def poll_receipt(account_id, revision, before, after, descriptors, at):
    """Calculate the documented receipt digest from actual domain JSON fields."""
    identifier = descriptors[0].poll_id if descriptors else uuid4()
    values = dict(id=str(identifier),account_id=str(account_id),request_id=str(uuid4()),
        request_sha256=sha(['independent-fiction-request',revision]),
        response_sha256=sha(['independent-fiction-response',revision]),
        expected_revision=revision,next_revision=revision+1,expected_cursor=before,next_cursor=after,
        descriptor_count=len(descriptors),created_at=at.isoformat().replace('+00:00','Z'),
        descriptors=[value.model_dump(mode='json') for value in descriptors])
    return d.WeixinPollReceipt(**values,receipt_sha256=sha(values))


def seed_history(database, actor, *, bot_account_id='synthetic-d2a-bot'):
    """Seed two exact fictional peers plus all outcome kinds and an empty poll."""
    with database.session() as db:
        workspace_id=UUID(db.scalar(text('SELECT id FROM local_workspace_identity')))
        views=tuple(conversations.create_conversation(actor,d.AssistantConversationCreateInput(
            request_id=uuid4(),display_title='独立虚构微信历史'+str(index)),db) for index in (1,2))
        bindings=tuple(tasks.create_binding(actor,view.scope.conversation_id,db) for view in views)
        at=datetime.now(timezone.utc)
        account=d.WeixinAccountSnapshot(id=uuid4(),workspace_id=workspace_id,owner_id=actor.user_id,
            bot_account_id=bot_account_id,initial_cursor='SYNTHETIC:opaque:start',
            checkpoint_revision=0,upstream_cursor='SYNTHETIC:opaque:start',created_at=at)
        account_row=account.model_dump(mode='json')
        insert(db,'weixin_accounts',account_row)
        mappings=tuple(d.WeixinPeerBindingSnapshot(id=uuid4(),account_id=account.id,
            sender_peer_id='synthetic-d2a-peer-'+str(index),task_binding_id=binding.id,
            scope=view.scope,scope_sha256=sha(view.scope.model_dump(mode='json')),
            created_at=at+timedelta(seconds=1))
            for index,(view,binding) in enumerate(zip(views,bindings),1))
        for mapping in mappings:
            row=mapping.model_dump(mode='json',exclude={'scope'})
            row['scope_json']=canonical_json(mapping.scope.model_dump(mode='json'))
            insert(db,'weixin_peer_bindings',row)

        def entry(poll,ordinal,peer=None,message_id=None,*,status='blocked',reason='message_invalid',
                  mapping=None,prior=None,source_hash=None,payload=None):
            source=event_id(account.bot_account_id,peer,message_id) if peer is not None else None
            return d.WeixinInboxDescriptor(id=uuid4(),poll_id=poll,ordinal=ordinal,
                sender_peer_id=peer,upstream_message_id=message_id,source_event_id=source,
                source_sha256=source_hash or sha(['independent-fiction-message',peer,message_id]),
                status=status,reason=reason,mapping_id=mapping.id if mapping else None,
                prior_descriptor_id=prior.id if prior else None,payload=payload)

        first_poll=uuid4()
        sources=tuple(event_id(account.bot_account_id,mapping.sender_peer_id,str(index))
                      for index,mapping in enumerate(mappings,101))
        first=(
            entry(first_poll,1,mappings[0].sender_peer_id,'101',status='accepted_pending_dispatch',
                reason=None,mapping=mappings[0],payload=d.TaskInboxEventInput(event_id=sources[0],
                    text='仅为独立虚构合同的待分发说明',media=(
                        d.TaskMediaInput(media_id=sources[0]+':1',name='独立虚构合同.docx',
                            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                        d.TaskMediaInput(media_id=sources[0]+':2',name='独立虚构附件.pdf',mime='application/pdf')))),
            entry(first_poll,2,mappings[1].sender_peer_id,'102',status='accepted_pending_dispatch',
                reason=None,mapping=mappings[1],payload=d.TaskInboxEventInput(event_id=sources[1],
                    text='第二位独立虚构发送者的文字')),
            entry(first_poll,3,'synthetic-unbound-peer','103',reason='sender_unbound'),
            entry(first_poll,4))
        receipt1=poll_receipt(account.id,0,account.initial_cursor,'SYNTHETIC:opaque:one',first,at+timedelta(seconds=2))
        second_poll=uuid4()
        second=(
            entry(second_poll,1,mappings[0].sender_peer_id,'101',status='duplicate',reason='replayed',
                mapping=mappings[0],prior=first[0],source_hash=first[0].source_sha256),
            entry(second_poll,2,mappings[0].sender_peer_id,'101',reason='event_conflict',
                mapping=mappings[0],prior=first[0],source_hash=sha('changed-independent-fiction')),
            entry(second_poll,3,'synthetic-unbound-peer','103',reason='previously_blocked',prior=first[2],
                source_hash=first[2].source_sha256),
            entry(second_poll,4,mappings[1].sender_peer_id,'104',reason='binding_revoked',mapping=mappings[1]))
        receipt2=poll_receipt(account.id,1,receipt1.next_cursor,'SYNTHETIC:opaque:two',second,at+timedelta(seconds=4))
        receipt3=poll_receipt(account.id,2,receipt2.next_cursor,receipt2.next_cursor,(),at+timedelta(seconds=5))
        receipts=(receipt1,receipt2,receipt3)
        for receipt in receipts:
            insert(db,'weixin_poll_receipts',receipt.model_dump(mode='json',exclude={'descriptors'}))
            for value in receipt.descriptors:
                row=value.model_dump(mode='json',exclude={'payload'})
                row['payload_json']=canonical_json(value.payload.model_dump(mode='json')) if value.payload else None
                insert(db,'weixin_inbox_descriptors',row)
            db.execute(text('''UPDATE weixin_accounts SET checkpoint_revision=:revision,upstream_cursor=:cursor
                WHERE id=:id'''),{'revision':receipt.next_revision,'cursor':receipt.next_cursor,'id':str(account.id)})
        revoked=dict(revoked_at=(at+timedelta(seconds=3)).isoformat().replace('+00:00','Z'),
            revoked_by=str(actor.user_id),revoke_reason='independent-fiction-revocation')
        db.execute(text('''UPDATE weixin_peer_bindings SET revoked_at=:revoked_at,revoked_by=:revoked_by,
            revoke_reason=:revoke_reason WHERE id=:id'''),{**revoked,'id':str(mappings[1].id)})
        mappings=(mappings[0],d.WeixinPeerBindingSnapshot(**{
            **mappings[1].model_dump(mode='python'),**revoked}))
        account=d.WeixinAccountSnapshot(**{**account.model_dump(mode='python'),
            'checkpoint_revision':3,'upstream_cursor':receipt3.next_cursor})
    return dict(account_id=account.id,mapping_ids=tuple(value.id for value in mappings),
        poll_ids=tuple(value.id for value in receipts),receipts=receipts,account=account,
        mappings=mappings,descriptors=first+second,actor=actor,
        conversation_ids=tuple(view.scope.conversation_id for view in views),
        task_binding_ids=tuple(binding.id for binding in bindings))
