"""Reversible list removal over independent fictional conversation storage."""
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.persistence import SessionRow
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox.personal_runtime import PersonalWeixinRuntime
from tests.integration.test_assistant_storage import (
    workspace, conversation, message, counts, assert_denied, add_matter, add_intake,
)
from tests.integration.test_assistant_routes import chat, native, sign_in, create
from tests.integration.test_assistant_attachments import material_workspace
from tests.integration.test_task_drafts import task_workspace, ready_media, receive


def request(view, **changes):
    return d.AssistantArchiveInput(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, **changes)


def test_archive_preserves_history_and_exact_replays_but_blocks_new_writes(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace);actor = actors['lawyer'];cid = first.scope.conversation_id
    sent = message(first)
    with database.session() as db:
        run = service.save_message(actor, cid, sent, db)
        service.cancel_run(actor, run.id, d.AssistantCancelInput(request_id=uuid4()), db)
        view = service.read_conversation(actor, cid, db)
    before = counts(database)
    with database.session() as db:
        archived = service.archive_conversation(actor, cid, request(view), db)
        assert archived.archived_at and archived.messages == view.messages
        assert service.list_conversations(actor, db).items == ()
        assert service.archive_conversation(actor, cid, request(view), db) == archived
        assert service.save_message(actor, cid, sent, db).id == run.id
        assert service.read_conversation(actor, cid, db) == archived
        assert_denied('VERSION_CONFLICT', service.save_message, actor, cid, message(archived), db)
        assert_denied('VERSION_CONFLICT', service.save_draft, actor, cid,
            d.AssistantDraftInput(expected_scope=archived.scope,
                expected_composer_revision=archived.composer_revision, content='新输入'), db)
    assert counts(database) == before


@pytest.mark.parametrize('change', ['scope', 'composer', 'owner', 'revoked', 'workspace', 'readonly', 'active'])
def test_archive_rejects_stale_or_unauthorized_before_runtime(workspace, change):
    database, actors, _, service = workspace
    first = conversation(workspace);actor = actors['lawyer'];cid = first.scope.conversation_id
    value = request(first)
    expected = 'VERSION_CONFLICT'
    with database.session() as db:
        if change == 'scope':
            value = value.model_copy(update={'expected_scope':first.scope.model_copy(update={'materials_revision':1})})
        elif change == 'composer':
            value = value.model_copy(update={'expected_composer_revision':1})
        elif change == 'owner':actor = actors['reviewer'];expected = 'CROSS_MATTER_DENIED'
        elif change == 'revoked':db.get(SessionRow, str(actor.session_id)).revoked = True;expected = 'AUTHORIZATION_REQUIRED'
        elif change == 'workspace':
            db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())});expected = 'CROSS_MATTER_DENIED'
        elif change == 'readonly':
            db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64,payload='{}'))
            db.flush();expected = 'BLOCKED_LIVE'
        elif change == 'active':
            service.save_message(actor, cid, message(first), db)
            first = service.read_conversation(actor, cid, db);value = request(first);expected = 'ASSISTANT_BUSY'
        def no_runtime(_):raise AssertionError('invalid archive must not touch runtime')
        with pytest.raises(ServiceError) as error:
            service.archive_conversation(actor, cid, value, db, require_disconnected=no_runtime)
        assert error.value.code == expected
        assert db.scalar(text('SELECT archived_at FROM assistant_conversations WHERE id=:id'), {'id':str(cid)}) is None


@pytest.mark.parametrize('scope_kind', ['matter', 'intake', 'projection'])
def test_archive_rechecks_case_and_intake_membership(workspace, scope_kind):
    database, actors, _, service = workspace
    matter = add_matter(database, actors['lawyer'])
    intake = add_intake(database, actors['lawyer'], matter)
    first = conversation(workspace, **({} if scope_kind == 'projection' else
        {'scope_kind':scope_kind, 'scope_ref':matter if scope_kind == 'matter' else intake}))
    with database.session() as db:
        if scope_kind == 'projection':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:i WHERE id=:id'),
                {'i':str(intake),'id':str(first.scope.conversation_id)})
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter)})
        assert_denied('CROSS_MATTER_DENIED', service.archive_conversation, actors['lawyer'],
            first.scope.conversation_id, request(first), db)


def test_archived_cursor_and_sql_limit_do_not_skip_visible_rows(workspace):
    database, actors, _, service = workspace
    values = [conversation(workspace) for _ in range(5)]
    with database.session() as db:
        ordered = service.list_conversations(actors['lawyer'], db, limit=5).items
        service.archive_conversation(actors['lawyer'], ordered[1].scope.conversation_id, request(ordered[1]), db)
        first = service.list_conversations(actors['lawyer'], db, limit=2)
        assert [item.scope for item in first.items] == [ordered[0].scope, ordered[2].scope]
        after_removed = service.list_conversations(actors['lawyer'], db, cursor=ordered[1].scope.conversation_id, limit=2)
        assert [item.scope for item in after_removed.items] == [ordered[2].scope, ordered[3].scope]


def test_awaiting_input_can_archive_but_new_cancel_cannot_change_archived_run(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace);actor = actors['lawyer'];cid = first.scope.conversation_id
    with database.session() as db:
        run = service.save_message(actor, cid, message(first), db)
        db.execute(text("UPDATE assistant_runs SET state='awaiting_input' WHERE id=:id"), {'id':str(run.id)})
        view = service.read_conversation(actor, cid, db)
        assert service.archive_conversation(actor, cid, request(view), db).archived_at
        assert_denied('VERSION_CONFLICT', service.cancel_run, actor, run.id,
            d.AssistantCancelInput(request_id=uuid4()), db)
        assert service.get_run(actor, run.id, db).state == 'awaiting_input'


def test_archive_blocks_active_task_execution_and_preserves_originals_after_stop(task_workspace):
    from cn_contract.assistant import service, attachments
    env = task_workspace;database, actors, cid, _, tasks, upload, raw = env
    actor = actors['lawyer'];media = ready_media(env)
    draft = receive(env, {'event_id':'archive-fiction','text':'审查虚构合同','media':[media]}).drafts[0]
    with database.session() as db:
        draft = tasks.read_draft(actor, draft.id, db)
        execution = tasks.freeze_draft(actor,draft.id,d.TaskFreezeInput(
            expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        tasks.advance_execution(actor,execution.id,'creating_matter',db,expected_state='prepared')
        view = service.read_conversation(actor,cid,db)
        assert_denied('ASSISTANT_BUSY', service.archive_conversation, actor, cid, request(view), db)
        tasks.advance_execution(actor,execution.id,'blocked',db,expected_state='creating_matter')
        assert service.archive_conversation(actor,cid,request(view),db).archived_at
        assert tasks.read_execution(actor,execution.id,db).state == 'blocked'
    assert attachments.read_original(actor,cid,media['attachment_id'],database=database) == raw
    assert attachments.ingest_attachment(actor,cid,upload,BytesIO(raw),database=database).attachment.id == media['attachment_id']
    materials = attachments.read_materials(actor,cid,database=database)
    with pytest.raises(ServiceError) as error:
        attachments.select_materials(actor,cid,d.AssistantMaterialSelectionInput(
            request_id=uuid4(),expected_scope=materials.scope,items=()),database=database)
    assert error.value.code == 'VERSION_CONFLICT'
    with pytest.raises(ServiceError) as error:
        receive(env, {'event_id':'late-after-archive','text':'迟到消息'})
    assert error.value.code == 'STATE_CONFLICT'


def test_archive_racing_new_draft_either_preserves_new_work_or_blocks_it(workspace):
    database, actors, _, service = workspace
    view = conversation(workspace);actor = actors['lawyer'];cid = view.scope.conversation_id
    barrier = Barrier(2)
    def operation(archive):
        barrier.wait(timeout=5)
        try:
            with database.session() as db:
                if archive:service.archive_conversation(actor,cid,request(view),db)
                else:service.save_draft(actor,cid,d.AssistantDraftInput(expected_scope=view.scope,
                    expected_composer_revision=0,content='比赛窗口里的新草稿'),db)
            return 'archive' if archive else 'draft'
        except ServiceError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation,[True,False]))
    assert 'VERSION_CONFLICT' in results
    with database.session() as db:
        current = service.read_conversation(actor,cid,db)
        assert (current.archived_at is not None and current.draft_input == '') or (
            current.archived_at is None and current.draft_input == '比赛窗口里的新草稿')


@pytest.mark.parametrize('same_target', [True, False])
def test_runtime_archive_guard_uses_target_not_session_visibility(workspace, same_target):
    database, actors, _, service = workspace
    first = conversation(workspace);cid = first.scope.conversation_id
    runtime = object.__new__(PersonalWeixinRuntime)
    runtime._value = SimpleNamespace(expected_scope=SimpleNamespace(conversation_id=cid if same_target else uuid4()))
    runtime._status = d.PersonalWeixinStatus(state='paused', conversation_id=runtime._value.expected_scope.conversation_id)
    runtime._status_actor = (actors['lawyer'].user_id, uuid4())
    with database.session() as db:
        if same_target:
            with pytest.raises(ServiceError, match='request blocked') as error:
                service.archive_conversation(actors['lawyer'], cid, request(first), db,
                    require_disconnected=runtime.require_disconnected)
            assert error.value.code == 'PERSONAL_WEIXIN_CONNECTED'
        else:
            assert service.archive_conversation(actors['lawyer'], cid, request(first), db,
                require_disconnected=runtime.require_disconnected).archived_at
        assert runtime._status.state == 'paused'


def test_delete_route_auth_csrf_origin_and_repeated_exact_body(chat):
    client, database, _ = chat
    headers = sign_in(client);view = create(client, headers)
    url = '/api/assistant/conversations/' + view['scope']['conversation_id']
    body = {'expected_scope':view['scope'],'expected_composer_revision':view['composer_revision']}
    assert client.request('DELETE',url,json=body).status_code == 403
    assert client.request('DELETE',url,headers={**headers,'Origin':'https://fiction.invalid'},json=body).status_code == 403
    other = sign_in(client, '另一合成律师')
    assert client.request('DELETE',url,headers=other,content='not-json').status_code == 403
    headers = sign_in(client)
    removed = client.request('DELETE',url,headers=headers,json=body)
    assert removed.status_code == 200, removed.text
    assert removed.json()['archived_at']
    assert client.request('DELETE',url,headers=headers,json=body).json() == removed.json()
    assert client.get('/api/assistant/conversations').json()['items'] == []
    assert client.get(url).json()['archived_at']


def test_delete_route_blocks_matching_runtime_even_when_session_status_is_hidden(chat):
    client, _, _ = chat
    headers = sign_in(client);view = create(client,headers);cid = view['scope']['conversation_id']
    from uuid import UUID
    runtime = object.__new__(PersonalWeixinRuntime)
    runtime._value = SimpleNamespace(expected_scope=SimpleNamespace(conversation_id=UUID(cid)))
    runtime._status = d.PersonalWeixinStatus(state='connected',conversation_id=cid)
    runtime._status_actor = (uuid4(),uuid4())
    client.app.state.personal_weixin_runtime = runtime
    result = client.request('DELETE','/api/assistant/conversations/'+cid,headers=headers,
        json={'expected_scope':view['scope'],'expected_composer_revision':0})
    assert result.status_code == 409 and result.json()['code'] == 'PERSONAL_WEIXIN_CONNECTED'
    assert client.get('/api/assistant/conversations/'+cid).json()['archived_at'] is None
