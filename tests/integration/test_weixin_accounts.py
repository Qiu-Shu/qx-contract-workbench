"""Native fictional workspaces exercise durable account ownership and exact ACL mapping."""
import importlib
import importlib.util
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.config import load_settings
from cn_contract.persistence import Database, MatterRow, MembershipRow, SessionRow, UserRow
from cn_contract.security import ServiceError, authenticate, login, provision_user
from cn_contract.storage_bootstrap import mark_storage_initialized
from cn_contract.task_drafts import service as tasks
from cn_contract.web.local_server import initialize_workspace


def api():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.accounts') is not None, 'D2b durable accounts required'
    return importlib.import_module('cn_contract.weixin_inbox.accounts')


@pytest.fixture
def source(tmp_path):
    root = tmp_path/'fictional-weixin-accounts'
    initialize_workspace(root, 'lawyer', 'fiction123', data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected', load_settings(),
                        initialize_schema=False)
    mark_storage_initialized(database)
    actors = {}
    with database.session() as db:
        for name, role in (('lawyer', d.Role.HANDLING_LAWYER), ('reviewer', d.Role.REVIEWING_LAWYER),
                           ('assistant', d.Role.ASSISTANT), ('admin', d.Role.ADMIN)):
            if name != 'lawyer':
                provision_user(name, 'fiction123', {role}, db, local_workbench_password=True)
            token, _ = login(name, 'fiction123', db)
            actors[name] = authenticate(token, db)
    try:
        yield database, actors
    finally:
        database.engine.dispose()


def account(source, **options):
    database, actors = source
    return api().create_synthetic_account(actors['lawyer'],
        d.WeixinAccountCreateInput(bot_account_id='synthetic-bot', **options), database=database)


def channel(source, *, actor='lawyer', **options):
    database, actors = source
    with database.session() as db:
        view = conversations.create_conversation(actors[actor],
            d.AssistantConversationCreateInput(request_id=uuid4(), **options), db)
        binding = tasks.create_binding(actors[actor], view.scope.conversation_id, db)
    return view, binding


def mapping(source, current_account=None, **options):
    database, actors = source
    current_account = current_account or account(source)
    view, binding = channel(source, **options)
    value = api().bind_synthetic_peer(actors['lawyer'], current_account.id,
        d.WeixinPeerBindInput(sender_peer_id='synthetic-peer', task_binding_id=binding.id,
                             expected_scope=view.scope), database=database)
    return current_account, value, view, binding


def denied(code, function, *args, **kwargs):
    with pytest.raises(ServiceError) as failure:
        function(*args, **kwargs)
    assert failure.value.code == code
    assert all(secret not in str(failure.value) for secret in ('synthetic-bot', 'synthetic-peer', 'fiction123'))


def counts(database):
    with database.session() as db:
        return tuple(db.scalar(text('SELECT count(*) FROM '+table)) for table in
                     ('weixin_accounts', 'weixin_peer_bindings', 'audit_events'))


def test_create_commits_before_return_and_replays_only_owner_and_initial_cursor(source):
    database, actors = source
    service = api()
    first = account(source, initial_cursor='opaque:before')
    assert first.owner_id == actors['lawyer'].user_id and first.mode == 'synthetic'
    assert first.checkpoint_revision == 0 and first.initial_cursor == first.upstream_cursor == 'opaque:before'
    with database.session() as db:
        assert db.scalar(text('SELECT id FROM weixin_accounts')) == str(first.id)
        assert str(first.workspace_id) == db.scalar(text('SELECT id FROM local_workspace_identity'))
    # The database's current roles win in both directions over caller-supplied roles.
    unstamped = actors['lawyer'].model_copy(update={'roles':frozenset()})
    assert service.read_synthetic_account(unstamped, first.id, database=database) == first
    assert account(source, initial_cursor='opaque:before') == first
    denied('VERSION_CONFLICT', service.create_synthetic_account, actors['lawyer'],
           d.WeixinAccountCreateInput(bot_account_id='synthetic-bot', initial_cursor='different'), database=database)
    denied('CROSS_MATTER_DENIED', service.create_synthetic_account, actors['reviewer'],
           d.WeixinAccountCreateInput(bot_account_id='synthetic-bot', initial_cursor='opaque:before'), database=database)
    denied('CROSS_MATTER_DENIED', service.read_synthetic_account, actors['reviewer'], first.id, database=database)
    assert counts(database) == (1, 0, 0)


@pytest.mark.parametrize('change', ['assistant', 'admin', 'role_changed', 'revoked', 'expired', 'disabled', 'foreign_user'])
def test_current_principal_prevents_forged_or_dead_session_access_without_writes(source, change):
    database, actors = source
    service = api()
    first = account(source)
    actor = actors['lawyer']
    with database.session() as db:
        if change in ('assistant', 'admin'):
            actor = actors[change].model_copy(update={'roles':frozenset({d.Role.HANDLING_LAWYER})})
        elif change == 'foreign_user':
            actor = actor.model_copy(update={'user_id':actors['reviewer'].user_id})
        elif change == 'role_changed':
            db.get(UserRow, str(actor.user_id)).roles = '["assistant"]'
        elif change == 'disabled':
            db.get(UserRow, str(actor.user_id)).disabled = True
        elif change == 'expired':
            db.get(SessionRow, str(actor.session_id)).expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        else:
            db.get(SessionRow, str(actor.session_id)).revoked = True
    expected = 'CROSS_MATTER_DENIED' if change in ('assistant', 'admin', 'role_changed') else 'AUTHORIZATION_REQUIRED'
    before = counts(database)
    denied(expected, service.read_synthetic_account, actor, first.id, database=database)
    denied(expected, service.create_synthetic_account, actor,
           d.WeixinAccountCreateInput(bot_account_id='another-fictional-bot'), database=database)
    assert counts(database) == before


def test_workspace_identity_cannot_reuse_an_account(source):
    database, actors = source
    first = account(source)
    with database.session() as db:
        db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
    denied('CROSS_MATTER_DENIED', api().read_synthetic_account, actors['lawyer'], first.id, database=database)


def test_exact_mapping_replays_but_never_implicitly_rebinds_peer_or_task(source):
    database, actors = source
    service = api()
    first, bound, view, binding = mapping(source)
    request = d.WeixinPeerBindInput(sender_peer_id=bound.sender_peer_id, task_binding_id=binding.id,
                                   expected_scope=view.scope)
    assert service.bind_synthetic_peer(actors['lawyer'], first.id, request, database=database) == bound
    assert service.read_synthetic_peer(actors['lawyer'], bound.id, database=database) == bound
    other, other_binding = channel(source)
    for changed in (request.model_copy(update={'sender_peer_id':'another-peer'}),
                    request.model_copy(update={'task_binding_id':other_binding.id, 'expected_scope':other.scope})):
        denied('VERSION_CONFLICT', service.bind_synthetic_peer, actors['lawyer'], first.id, changed, database=database)
    second = service.create_synthetic_account(actors['lawyer'],
        d.WeixinAccountCreateInput(bot_account_id='another-bot'), database=database)
    denied('VERSION_CONFLICT', service.bind_synthetic_peer, actors['lawyer'], second.id, request, database=database)
    denied('CROSS_MATTER_DENIED', service.read_synthetic_peer, actors['reviewer'], bound.id, database=database)
    assert counts(database) == (2, 1, 0)


@pytest.mark.parametrize('change', ['scope', 'wrong_binding', 'other_owner'])
def test_bind_requires_exact_current_scope_and_owned_channel(source, change):
    database, actors = source
    first = account(source)
    view, binding = channel(source, actor='reviewer' if change == 'other_owner' else 'lawyer')
    if change == 'scope':
        view = view.model_copy(update={'scope':view.scope.model_copy(update={'input_revision':1})})
    task_id = uuid4() if change == 'wrong_binding' else binding.id
    expected = 'VERSION_CONFLICT' if change == 'scope' else 'CROSS_MATTER_DENIED'
    denied(expected, api().bind_synthetic_peer, actors['lawyer'], first.id,
           d.WeixinPeerBindInput(sender_peer_id='synthetic-peer', task_binding_id=task_id,
                                expected_scope=view.scope), database=database)
    assert counts(database) == (1, 0, 0)


def test_revocations_preserve_first_actor_time_reason_and_allow_historical_reads(source):
    database, actors = source
    service = api()
    first, bound, view, binding = mapping(source)
    reason = d.WeixinRevokeInput(reason='independent fictional revocation')
    revoked = service.revoke_synthetic_peer(actors['lawyer'], bound.id, reason, database=database)
    assert revoked.revoked_by == actors['lawyer'].user_id and revoked.revoked_at >= bound.created_at
    assert service.revoke_synthetic_peer(actors['lawyer'], bound.id, reason, database=database) == revoked
    assert service.read_synthetic_peer(actors['lawyer'], bound.id, database=database) == revoked
    denied('VERSION_CONFLICT', service.revoke_synthetic_peer, actors['lawyer'], bound.id,
           d.WeixinRevokeInput(reason='changed reason'), database=database)
    denied('STATE_CONFLICT', service.bind_synthetic_peer, actors['lawyer'], first.id,
           d.WeixinPeerBindInput(sender_peer_id=bound.sender_peer_id, task_binding_id=binding.id,
                                expected_scope=view.scope), database=database)
    gone = service.revoke_synthetic_account(actors['lawyer'], first.id, reason, database=database)
    assert service.revoke_synthetic_account(actors['lawyer'], first.id, reason, database=database) == gone
    assert service.read_synthetic_account(actors['lawyer'], first.id, database=database) == gone
    denied('VERSION_CONFLICT', service.revoke_synthetic_account, actors['lawyer'], first.id,
           d.WeixinRevokeInput(reason='different reason'), database=database)
    denied('STATE_CONFLICT', service.create_synthetic_account, actors['lawyer'],
           d.WeixinAccountCreateInput(bot_account_id='synthetic-bot'), database=database)


def test_restore_fence_allows_history_but_blocks_all_account_writes(source):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors = source
    service = api()
    first, bound, view, binding = mapping(source)
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='1'*64, manifest_sha256='2'*64, payload='{}'))
    assert service.read_synthetic_account(actors['lawyer'], first.id, database=database) == first
    assert service.read_synthetic_peer(actors['lawyer'], bound.id, database=database) == bound
    denied('BLOCKED_LIVE', service.create_synthetic_account, actors['lawyer'],
           d.WeixinAccountCreateInput(bot_account_id='new-bot'), database=database)
    denied('BLOCKED_LIVE', service.bind_synthetic_peer, actors['lawyer'], first.id,
           d.WeixinPeerBindInput(sender_peer_id=bound.sender_peer_id, task_binding_id=binding.id,
                                expected_scope=view.scope), database=database)
    for function, identifier in ((service.revoke_synthetic_account, first.id), (service.revoke_synthetic_peer, bound.id)):
        denied('BLOCKED_LIVE', function, actors['lawyer'], identifier,
               d.WeixinRevokeInput(reason='fenced fictional write'), database=database)
    assert counts(database) == (1, 1, 0)


@pytest.mark.parametrize('change', ['binding_revision', 'input_revision', 'materials_revision', 'archived', 'owner', 'workspace', 'session'])
def test_mapping_guard_is_pure_and_detects_current_scope_and_ownership(source, change):
    database, actors = source
    service = api()
    first, bound, view, _ = mapping(source)
    with database.session() as db:
        assert service._mapping_reason(actors['lawyer'], first, bound, db) is None
        if change.endswith('_revision'):
            db.execute(text('UPDATE assistant_conversations SET '+change+'='+change+'+1 WHERE id=:id'),
                       {'id':str(view.scope.conversation_id)})
        elif change == 'session':
            db.get(SessionRow, str(actors['lawyer'].session_id)).revoked = True
        else:
            key, value = {'archived':('archived_at', datetime.now(timezone.utc).isoformat()),
                          'owner':('owner_id', str(actors['reviewer'].user_id)),
                          'workspace':('workspace_id', str(uuid4()))}[change]
            db.execute(text('UPDATE assistant_conversations SET '+key+'=:value WHERE id=:id'),
                       {'id':str(view.scope.conversation_id), 'value':value})
        db.flush()
        # A pure guard cannot discard or commit an earlier unrelated write in the same poll.
        db.execute(text("UPDATE assistant_conversations SET draft_input='fictional pending write' WHERE id=:id"),
                   {'id':str(view.scope.conversation_id)})
        with event_guard(db):
            result = service._mapping_reason(actors['lawyer'], first, bound, db)
        assert result == ('scope_stale' if change.endswith('_revision') or change == 'archived' else 'scope_denied')
        assert db.scalar(text('SELECT draft_input FROM assistant_conversations WHERE id=:id'),
                         {'id':str(view.scope.conversation_id)}) == 'fictional pending write'
        assert db.scalar(text('SELECT count(*) FROM audit_events')) == 0


class event_guard:
    def __init__(self, db): self.db = db
    def __enter__(self):
        event.listen(self.db, 'after_commit', self.fail)
        event.listen(self.db, 'after_rollback', self.fail)
    def fail(self, *args): raise AssertionError('mapping classification must not commit or rollback')
    def __exit__(self, *args):
        event.remove(self.db, 'after_commit', self.fail)
        event.remove(self.db, 'after_rollback', self.fail)


@pytest.mark.parametrize('kind', ['matter', 'intake', 'projection'])
def test_mapping_guard_rechecks_membership_and_converted_or_projected_intake_owner(source, kind):
    from cn_contract.matters import create_matter
    database, actors = source
    service = api()
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立虚构权限案', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('仅权限测试',)), actors['lawyer'], db)
        intake_id = uuid4()
        db.execute(text('''INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES(:id,:owner,:request,:sha,1,:matter)'''),
            {'id':str(intake_id), 'owner':str(actors['lawyer'].user_id), 'request':str(uuid4()),
             'sha':'f'*64, 'matter':str(matter.id)})
    first, bound, view, _ = mapping(source, scope_kind='intake' if kind == 'intake' else 'matter',
                                  scope_ref=intake_id if kind == 'intake' else matter.id)
    with database.session() as db:
        before_audits = db.scalar(text('SELECT count(*) FROM audit_events'))
        if kind == 'projection':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                       {'intake':str(intake_id), 'id':str(view.scope.conversation_id)})
            db.execute(text('UPDATE intake_cases SET owner_id=:owner WHERE id=:id'),
                       {'owner':str(actors['reviewer'].user_id), 'id':str(intake_id)})
        else:
            db.delete(db.get(MembershipRow, (str(matter.id), str(actors['lawyer'].user_id))))
        db.flush()
        with event_guard(db):
            assert service._mapping_reason(actors['lawyer'], first, bound, db) == 'scope_denied'
        assert db.scalar(text('SELECT count(*) FROM audit_events')) == before_audits


def test_service_revalidates_model_copy_inputs_before_any_persistence(source):
    database, actors = source
    service = api()
    first = account(source)
    view, binding = channel(source)
    for request, function, args in (
        (d.WeixinAccountCreateInput(bot_account_id='safe').model_copy(update={'bot_account_id':False}),
         service.create_synthetic_account, (actors['lawyer'],)),
        (d.WeixinPeerBindInput(sender_peer_id='safe', task_binding_id=binding.id, expected_scope=view.scope)
         .model_copy(update={'sender_peer_id':' unsafe '}), service.bind_synthetic_peer, (actors['lawyer'], first.id)),
        (d.WeixinRevokeInput(reason='safe').model_copy(update={'reason':'   '}),
         service.revoke_synthetic_account, (actors['lawyer'], first.id))):
        with pytest.raises(ValidationError):
            function(*args, request, database=database)
    assert counts(database) == (1, 0, 0)


def test_database_constraint_failure_is_sanitized_and_rolls_back(source, monkeypatch):
    database, actors = source
    service = api()
    first = account(source)
    monkeypatch.setattr(service, 'uuid4', lambda:first.id)
    denied('VERSION_CONFLICT', service.create_synthetic_account, actors['lawyer'],
           d.WeixinAccountCreateInput(bot_account_id='different-fictional-bot'), database=database)
    assert counts(database) == (1, 0, 0)


def test_commit_failure_does_not_return_or_leave_an_account(source, monkeypatch):
    database, actors = source
    service = api()
    def fail_commit(db):
        raise RuntimeError('independent fictional commit fault')
    with monkeypatch.context() as patch:
        patch.setattr(database.session_factory.class_, 'commit', fail_commit)
        with pytest.raises(RuntimeError, match='independent fictional commit fault'):
            service.create_synthetic_account(actors['lawyer'],
                d.WeixinAccountCreateInput(bot_account_id='failed-fictional-bot'), database=database)
    assert counts(database) == (0, 0, 0)


def test_peer_read_checks_current_principal_before_mapping_lookup(source, monkeypatch):
    database, actors = source
    service = api()
    forged = actors['assistant'].model_copy(update={'roles':frozenset({d.Role.HANDLING_LAWYER})})
    def never(*args):
        raise AssertionError('untrusted roles must be rejected before mapping lookup')
    monkeypatch.setattr(service, '_mapping_row', never)
    denied('CROSS_MATTER_DENIED', service.read_synthetic_peer, forged, uuid4(), database=database)
    denied('CROSS_MATTER_DENIED', service.revoke_synthetic_peer, forged, uuid4(),
           d.WeixinRevokeInput(reason='fictional revoke'), database=database)


@pytest.mark.parametrize('kind', ['matter', 'intake', 'projection'])
def test_archived_matter_blocks_new_ingress_for_direct_converted_and_projected_scopes(source, kind):
    from cn_contract.matters import create_matter
    database, actors = source
    service = api()
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立虚构归档权限案', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('仅合成归档权限测试',)), actors['lawyer'], db)
        intake_id = uuid4()
        db.execute(text('''INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES(:id,:owner,:request,:sha,1,:matter)'''),
            {'id':str(intake_id), 'owner':str(actors['lawyer'].user_id), 'request':str(uuid4()),
             'sha':'e'*64, 'matter':str(matter.id)})
    options = {'scope_kind':kind, 'scope_ref':matter.id if kind == 'matter' else intake_id} if kind != 'projection' else {}
    first, bound, view, _ = mapping(source, **options)
    with database.session() as db:
        if kind == 'projection':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                       {'intake':str(intake_id), 'id':str(view.scope.conversation_id)})
        before_audits = db.scalar(text('SELECT count(*) FROM audit_events'))
        with event_guard(db):
            assert service._mapping_reason(actors['lawyer'], first, bound, db) is None
        assert db.get(MembershipRow, (str(matter.id), str(actors['lawyer'].user_id))) is not None
        db.get(MatterRow, str(matter.id)).status = 'archived'
        db.flush()
        with event_guard(db):
            assert service._mapping_reason(actors['lawyer'], first, bound, db) == 'scope_denied'
        assert db.scalar(text('SELECT count(*) FROM audit_events')) == before_audits
