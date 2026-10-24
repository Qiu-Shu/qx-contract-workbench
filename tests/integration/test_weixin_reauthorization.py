"""Explicit local refresh keeps the target and historical source immutable."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import accounts,dispatch,ingress
from tests.integration.test_weixin_dispatch import message,poll,seed,world


def api():
    assert hasattr(accounts,'refresh_synthetic_peer'), 'D2d explicit refresh service required'
    assert hasattr(accounts,'find_peer_scope_grant'), 'D2d unknown-result lookup required'
    return accounts


def advance(world,**changes):
    _,database,actor,view,*_=world
    with database.session() as db:
        for key,value in changes.items():
            assert key in ('input_revision','materials_revision','binding_revision','scope_kind','scope_ref','archived_at')
            db.execute(text('UPDATE assistant_conversations SET '+key+'=:value WHERE id=:id'),
                {'value':value,'id':str(view.scope.conversation_id)})
        row=db.execute(text('SELECT * FROM assistant_conversations WHERE id=:id'),
            {'id':str(view.scope.conversation_id)}).mappings().one()
        return conversations._snapshot(row)


def request(mapping,scope,previous=None,**changes):
    return d.WeixinPeerRefreshInput(**{**dict(request_id=uuid4(),
        expected_grant_revision=previous.revision if previous else 0,
        expected_scope_sha256=previous.scope_sha256 if previous else mapping.scope_sha256,
        expected_scope=scope,reason='explicit independent fictional refresh'),**changes})


def state(database):
    tables=('weixin_peer_bindings','weixin_poll_receipts','weixin_inbox_descriptors',
        'weixin_peer_scope_grants','task_inbox_events','task_channel_bindings','weixin_dispatch_receipts')
    with database.session() as db:
        return {name:[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))] for name in tables}


def denied(code,function,*args,**kwargs):
    with pytest.raises(ServiceError) as failure:function(*args,**kwargs)
    assert failure.value.code==code


@pytest.mark.parametrize('field',['input_revision','materials_revision'])
def test_refresh_changes_only_effective_scope_and_replays_fixed_grant(world,field):
    service=api();_,database,actor,*_=world
    account,mapping,received=seed(world,[message(1)])
    before=state(database);scope=advance(world,**{field:1})
    denied('VERSION_CONFLICT',dispatch.dispatch_synthetic_descriptor,actor,received.descriptors[0].id,database=database)
    value=request(mapping,scope)
    grant=service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    assert grant.revision==1 and grant.actor_id==actor.user_id and grant.checkpoint_revision==1
    assert grant.previous_scope_sha256==mapping.scope_sha256 and grant.scope==scope
    after=state(database)
    for table in before:
        if table!='weixin_peer_scope_grants':assert before[table]==after[table],table
    assert service.read_synthetic_peer(actor,mapping.id,database=database)==mapping
    assert service.refresh_synthetic_peer(actor,mapping.id,value,database=database)==grant
    assert service.find_peer_scope_grant(actor,mapping.id,value.request_id,database=database)==grant
    assert state(database)==after
    receipt=dispatch.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    assert receipt.next_task_cursor==1
    assert ingress.find_poll_receipt(actor,account.id,received.request_id,database=database)==received
    assert poll(world,account,[message(2)]).descriptors[0].status=='accepted_pending_dispatch'


def test_blocked_message_stays_blocked_and_new_messages_use_explicit_authorization(world):
    service=api();_,database,actor,*_=world
    account,mapping,_=seed(world,[])
    scope=advance(world,materials_revision=1)
    blocked=poll(world,account,[message(1)])
    assert blocked.descriptors[0].reason=='scope_stale'
    service.refresh_synthetic_peer(actor,mapping.id,request(mapping,scope),database=database)
    received=poll(world,account,[message(1),message(2)])
    assert received.descriptors[0].status=='blocked' and received.descriptors[0].reason=='previously_blocked'
    assert received.descriptors[1].status=='accepted_pending_dispatch'
    denied('STATE_CONFLICT',dispatch.dispatch_synthetic_descriptor,actor,received.descriptors[0].id,database=database)
    assert dispatch.dispatch_synthetic_descriptor(actor,received.descriptors[1].id,database=database).next_task_cursor==1


@pytest.mark.parametrize('change',['hash','revision','scope','reason'])
def test_same_request_conflicts_never_change_original_grant(world,change):
    service=api();_,database,actor,*_=world
    _,mapping,_=seed(world,[]);scope=advance(world,input_revision=1)
    value=request(mapping,scope);grant=service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    changes={'hash':{'expected_scope_sha256':'0'*64},'revision':{'expected_grant_revision':1},
        'scope':{'expected_scope':scope.model_copy(update={'materials_revision':1})},'reason':{'reason':'changed reason'}}[change]
    before=state(database)
    denied('VERSION_CONFLICT',service.refresh_synthetic_peer,actor,mapping.id,value.model_copy(update=changes),database=database)
    assert state(database)==before and service.find_peer_scope_grant(actor,mapping.id,value.request_id,database=database)==grant


def test_refresh_cas_and_old_receipt_lookup_follow_current_authority(world):
    service=api();_,database,actor,*_=world
    _,mapping,_=seed(world,[])
    first_scope=advance(world,input_revision=1)
    first_request=request(mapping,first_scope)
    first=service.refresh_synthetic_peer(actor,mapping.id,first_request,database=database)
    second_scope=advance(world,input_revision=2,materials_revision=1)
    before=state(database)
    denied('VERSION_CONFLICT',service.refresh_synthetic_peer,actor,mapping.id,request(mapping,second_scope),database=database)
    denied('VERSION_CONFLICT',service.find_peer_scope_grant,actor,mapping.id,first.request_id,database=database)
    assert state(database)==before
    second=service.refresh_synthetic_peer(actor,mapping.id,request(mapping,second_scope,first),database=database)
    assert second.revision==2 and second.previous_scope_sha256==first.scope_sha256
    assert service.find_peer_scope_grant(actor,mapping.id,first.request_id,database=database)==first
    assert service.refresh_synthetic_peer(actor,mapping.id,first_request,database=database)==first


@pytest.mark.parametrize('change',['unchanged','binding','other_conversation','other_workspace','lower_version','future_version'])
def test_refresh_never_changes_target_or_reduces_versions(world,change):
    service=api();_,database,actor,*_=world
    _,mapping,_=seed(world,[])
    scope=advance(world,input_revision=1)
    if change=='unchanged':scope=mapping.scope
    elif change=='binding':scope=advance(world,binding_revision=2)
    elif change=='other_conversation':scope=scope.model_copy(update={'conversation_id':uuid4()})
    elif change=='other_workspace':scope=scope.model_copy(update={'workspace_id':uuid4()})
    elif change=='future_version':scope=scope.model_copy(update={'materials_revision':99})
    else:
        scope=advance(world,input_revision=2,materials_revision=1)
        previous=service.refresh_synthetic_peer(actor,mapping.id,request(mapping,scope),database=database)
        scope=advance(world,input_revision=1,materials_revision=2)
    before=state(database)
    value=request(mapping,scope,previous if change=='lower_version' else None)
    denied('VERSION_CONFLICT',service.refresh_synthetic_peer,actor,mapping.id,value,database=database)
    assert state(database)==before


@pytest.mark.parametrize('change',['peer','account','session','role','archived','restore'])
def test_refresh_and_lookup_never_bypass_current_guards(world,change):
    from cn_contract.ops.storage import RestoreFenceRow
    from cn_contract.persistence import SessionRow,UserRow
    service=api();_,database,actor,*_=world
    account,mapping,_=seed(world,[]);scope=advance(world,input_revision=1)
    value=request(mapping,scope);grant=service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    if change in ('peer','account'):
        function=accounts.revoke_synthetic_peer if change=='peer' else accounts.revoke_synthetic_account
        function(actor,mapping.id if change=='peer' else account.id,d.WeixinRevokeInput(reason='fictional revoke'),database=database)
    else:
        with database.session() as db:
            if change=='session':db.get(SessionRow,str(actor.session_id)).revoked=True
            elif change=='role':db.get(UserRow,str(actor.user_id)).roles='["assistant"]'
            elif change=='archived':db.execute(text('UPDATE assistant_conversations SET archived_at=:at'),{'at':'2026-10-24T15:00:00Z'})
            else:db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='1'*64,manifest_sha256='2'*64,payload='{}'))
    before=state(database)
    expected='BLOCKED_LIVE' if change=='restore' else 'AUTHORIZATION_REQUIRED' if change=='session' else 'CROSS_MATTER_DENIED' if change=='role' else 'VERSION_CONFLICT' if change=='archived' else 'STATE_CONFLICT'
    denied(expected,service.refresh_synthetic_peer,actor,mapping.id,value,database=database)
    if change=='restore':assert service.find_peer_scope_grant(actor,mapping.id,value.request_id,database=database)==grant
    else:denied(expected,service.find_peer_scope_grant,actor,mapping.id,value.request_id,database=database)
    assert state(database)==before


def test_refresh_and_lookup_authenticate_before_mapping_lookup(world):
    from cn_contract.persistence import SessionRow
    service=api();_,database,actor,view,*_=world
    with database.session() as db:db.get(SessionRow,str(actor.session_id)).revoked=True
    denied('AUTHORIZATION_REQUIRED',service.refresh_synthetic_peer,actor,uuid4(),
        d.WeixinPeerRefreshInput(request_id=uuid4(),expected_grant_revision=0,
            expected_scope_sha256='a'*64,expected_scope=view.scope,reason='fictional check'),database=database)
    denied('AUTHORIZATION_REQUIRED',service.find_peer_scope_grant,actor,uuid4(),uuid4(),database=database)


@pytest.mark.parametrize('kind',['matter_membership','matter_archived','intake_converted','projection_owner'])
@pytest.mark.parametrize('replay',[False,True])
def test_refresh_rechecks_current_case_and_intake_access_without_side_effects(world,kind,replay):
    from cn_contract.matters import create_matter
    from cn_contract.persistence import MatterRow,MembershipRow
    from cn_contract.security import provision_user
    from cn_contract.task_drafts import service as tasks
    service=api();root,database,actor,*_=world
    with database.session() as db:
        matter=create_matter(d.MatterCreateInput(title='独立虚构授权案件',contract_type='sales',
            review_mode='pre_sign',position='buyer',objectives=('仅权限测试',)),actor,db)
        intake_id=uuid4()
        db.execute(text('''INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES(:id,:owner,:request,:sha,1,:matter)'''),dict(id=str(intake_id),owner=str(actor.user_id),
                request=str(uuid4()),sha='a'*64,matter=str(matter.id)))
        view=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4(),
            scope_kind='intake' if kind=='intake_converted' else 'matter',
            scope_ref=intake_id if kind=='intake_converted' else matter.id),db)
        binding=tasks.create_binding(actor,view.scope.conversation_id,db)
        if kind=='projection_owner':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                {'intake':str(intake_id),'id':str(view.scope.conversation_id)})
    selected=(root,database,actor,view,binding)
    _,mapping,_=seed(selected,[]);value=request(mapping,advance(selected,input_revision=1))
    if replay:service.refresh_synthetic_peer(actor,mapping.id,value,database=database)
    with database.session() as db:
        if kind=='matter_archived':db.get(MatterRow,str(matter.id)).status='archived'
        elif kind=='projection_owner':
            provision_user('fictional-foreign','fiction123',{d.Role.HANDLING_LAWYER},db,local_workbench_password=True)
            foreign=db.scalar(text("SELECT id FROM users WHERE username='fictional-foreign'"))
            db.execute(text('UPDATE intake_cases SET owner_id=:owner WHERE id=:id'),{'owner':foreign,'id':str(intake_id)})
        else:db.delete(db.get(MembershipRow,(str(matter.id),str(actor.user_id))))
    before=state(database)
    denied('CROSS_MATTER_DENIED',service.refresh_synthetic_peer,actor,mapping.id,value,database=database)
    denied('CROSS_MATTER_DENIED' if replay else 'VERSION_CONFLICT',service.find_peer_scope_grant,
        actor,mapping.id,value.request_id,database=database)
    assert state(database)==before
