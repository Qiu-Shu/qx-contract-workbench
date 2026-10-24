"""Independent SQL generation fixtures; no runtime target-switch service exists."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.config import canonical_json
from cn_contract.record_codec import sha
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_inbox import accounts, dispatch
from tests.integration.test_weixin_dispatch import message, poll, seed
from tests.integration.test_weixin_reauthorization import advance, request


HISTORY_TABLES = ('weixin_accounts','weixin_peer_bindings','weixin_peer_scope_grants',
    'weixin_poll_receipts','weixin_inbox_descriptors','weixin_dispatch_receipts',
    'weixin_peer_generations','task_channel_bindings','task_inbox_events','task_drafts',
    'task_draft_events','task_executions','assistant_runs','review_runs')


def state(database, *, generations=True):
    with database.session() as db:
        return {name:[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))]
            for name in HISTORY_TABLES if generations or name != 'weixin_peer_generations'}


def setup_history(world):
    root,database,actor,view,binding = world
    account,mapping,received = seed(world,[message(1),message(2,file=True)])
    with database.session() as db:
        peer_view = conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        peer_binding = tasks.create_binding(actor,peer_view.scope.conversation_id,db)
    peer = accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id='synthetic-peer-two',
        task_binding_id=peer_binding.id,expected_scope=peer_view.scope),database=database)
    peer_poll = poll(world,account,[message(3,peer=peer.sender_peer_id)])
    grant_request = request(mapping,advance(world,input_revision=1))
    grant = accounts.refresh_synthetic_peer(actor,mapping.id,grant_request,database=database)
    dispatched = dispatch.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    peer_dispatch = dispatch.dispatch_synthetic_descriptor(actor,peer_poll.descriptors[0].id,database=database)
    targets = []
    with database.session() as db:
        for _ in range(2):
            target = conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
            targets.append((target,tasks.create_binding(actor,target.scope.conversation_id,db)))
    return dict(root=root,database=database,actor=actor,view=view,binding=binding,
        account=account,mapping=mapping,received=received,grant_request=grant_request,grant=grant,
        dispatched=dispatched,peer=peer,peer_view=peer_view,peer_poll=peer_poll,
        peer_dispatch=peer_dispatch,targets=targets)


def append_generation(history, previous=None):
    assert hasattr(d,'WeixinPeerGeneration'), 'D2f generation DTO required'
    database,actor,mapping = (history[key] for key in ('database','actor','mapping'))
    ordinal = previous.generation+1 if previous else 1
    target,binding = history['targets'][ordinal-1]
    with database.session() as db:
        stamps = []
        for name in ('weixin_accounts','weixin_peer_bindings','weixin_poll_receipts',
                     'weixin_dispatch_receipts','weixin_peer_scope_grants','weixin_peer_generations',
                     'task_channel_bindings','assistant_conversations'):
            stamps.extend(datetime.fromisoformat(value.replace('Z','+00:00'))
                for value in db.scalars(text('SELECT created_at FROM '+name)))
        at = max([datetime.now(timezone.utc),*stamps])+timedelta(microseconds=1)
        scope = target.scope.model_dump(mode='json')
        values = dict(id=str(uuid4()),root_mapping_id=str(mapping.id),generation=ordinal,
            request_id=str(uuid4()),actor_id=str(actor.user_id),task_binding_id=str(binding.id),
            scope=scope,scope_sha256=sha(scope),
            previous_generation_sha256=previous.generation_sha256 if previous else None,
            previous_scope_sha256=previous.scope_sha256 if previous else history['grant'].scope_sha256,
            checkpoint_revision=db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts WHERE id=:id'),
                {'id':str(history['account'].id)}),created_at=at.isoformat().replace('+00:00','Z'),
            reason='独立合成代际存储验收；非运行时切换')
        generation = d.WeixinPeerGeneration(**values,generation_sha256=sha(values))
        stored = generation.model_dump(mode='json',exclude={'scope'})
        stored['scope_json'] = canonical_json(scope)
        db.execute(text('INSERT INTO weixin_peer_generations ('+','.join(stored)+') VALUES ('+
            ','.join(':'+key for key in stored)+')'),stored)
    return generation
