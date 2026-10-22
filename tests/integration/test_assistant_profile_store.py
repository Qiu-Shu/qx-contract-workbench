"""Atomic local drafts, only independently synthetic conversations."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.assistant import service, profile_schema
from cn_contract.intake import service as intake
from cn_contract.persistence import SessionRow
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, add_matter
from test_assistant_profile_sources import sent, patch, msg_ref


def save(actor, request, database):
    from cn_contract.assistant.profile_store import save_profile
    return save_profile(actor, request, database=database)


def next_request(request, result, **changes):
    return request.model_copy(update={'request_id':uuid4(),
        'patch':request.patch.model_copy(update={'base_profile_revision':result.profile_revision}),
        'expected_intake_id':result.intake_id, 'expected_intake_revision':result.intake_revision, **changes})


def count(database):
    with database.session() as db:
        return tuple(db.scalar(text('SELECT count(*) FROM '+table)) for table in (
            'assistant_profile_revisions','assistant_profile_receipts','intake_cases','intake_revisions'))


def setup(workspace):
    database, actors, _, _ = workspace
    profile_schema.initialize_storage(database)
    value = sent(workspace)
    request = d.ProfileCommitInput(request_id=uuid4(), patch=patch(value.scope, (msg_ref(value),)), project_intake=True)
    return database, actors['lawyer'], value, request


def test_projection_retry_and_recoverable_receipt(workspace):
    from cn_contract.assistant.profile_store import save_profile, read_profile, find_receipt
    database, actor, value, request = setup(workspace)
    result = save_profile(actor, request, database=database)
    assert result.profile_changed and result.projection_changed
    assert result.profile_revision == 1 and result.intake_revision == 1
    assert result.consultation_origin == 'profile_summary' and result.audience == 'internal'
    assert save_profile(actor, request, database=database) == result
    assert find_receipt(actor, value.scope.conversation_id, request.request_id, database=database) == result
    assert read_profile(actor, value.scope.conversation_id, database=database).revision == 1
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM intake_cases')) == 1
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 1
        assert db.scalar(text('SELECT count(*) FROM matters')) == 0


def test_noop_request_has_one_receipt_without_new_revisions(workspace):
    database, actor, _, request = setup(workspace)
    first = save(actor, request, database)
    second_request = next_request(request, first)
    second = save(actor, second_request, database)
    assert not second.profile_changed and not second.projection_changed
    assert second.event_type == 'profile.unchanged' and second.sequence == 2
    assert second.consultation_origin == 'profile_summary'
    assert save(actor, second_request, database) == second
    assert count(database) == (1, 2, 1, 1)


def test_empty_draft_does_not_create_intake_or_profile_revision(workspace):
    database, actor, _, request = setup(workspace)
    empty = request.model_copy(update={'patch':request.patch.model_copy(update={'changes':()})})
    result = save(actor, empty, database)
    assert result.profile_revision == 0 and result.intake_id is None
    assert result.event_type == 'profile.unchanged' and count(database) == (0, 1, 0, 0)


def test_profile_only_then_project_with_same_state(workspace):
    database, actor, _, request = setup(workspace)
    first = save(actor, request.model_copy(update={'project_intake':False}), database)
    assert first.intake_id is None and count(database) == (1, 1, 0, 0)
    second = save(actor, next_request(request, first), database)
    assert not second.profile_changed and second.projection_changed and second.profile_revision == 1
    assert count(database) == (1, 2, 1, 1)


@pytest.mark.parametrize('table,operation', [
    ('intake_cases','INSERT'), ('intake_revisions','INSERT'), ('assistant_conversations','UPDATE'),
    ('assistant_profile_revisions','INSERT'), ('assistant_profile_receipts','INSERT')])
def test_each_write_failure_rolls_back_even_if_caller_commits(workspace, table, operation):
    from cn_contract.assistant.profile_store import _commit
    from cn_contract.assistant.profile_sources import read_profile_sources
    database, actor, value, request = setup(workspace)
    sources = read_profile_sources(actor, request.patch, database=database)
    with database.session() as db:
        db.execute(text(f'''CREATE TRIGGER fail_profile BEFORE {operation} ON {table}
            BEGIN SELECT RAISE(ABORT,'synthetic failure'); END'''))
    with database.session() as db:
        with pytest.raises(IntegrityError):
            _commit(actor, request, sources, db)
        db.execute(text('DROP TRIGGER fail_profile'))
    assert count(database) == (0, 0, 0, 0)
    with database.session() as db:
        assert db.scalar(text('SELECT projection_intake_id FROM assistant_conversations WHERE id=:cid'),
            {'cid':str(value.scope.conversation_id)}) is None
    assert save(actor, request, database).sequence == 1


@pytest.mark.parametrize('fault', ['request_key','profile_revision','intake_revision','intake_id','source_quote'])
def test_stale_or_forged_commands_do_not_write(workspace, fault):
    database, actor, _, request = setup(workspace)
    first = save(actor, request, database)
    current = next_request(request, first)
    if fault == 'request_key':
        current = current.model_copy(update={'request_id':request.request_id})
    elif fault == 'profile_revision':
        current = current.model_copy(update={'patch':request.patch})
    elif fault == 'intake_revision':
        current = current.model_copy(update={'expected_intake_revision':2})
    elif fault == 'intake_id':
        current = current.model_copy(update={'expected_intake_id':uuid4()})
    else:
        original = request.patch.changes[0]
        import hashlib
        ref = original.source_refs[0].model_copy(update={'quote':'伪造内容','start':0,'end':4,
            'quote_sha256':hashlib.sha256('伪造内容'.encode()).hexdigest()})
        current = current.model_copy(update={'patch':current.patch.model_copy(update={
            'changes':(original.model_copy(update={'source_refs':(ref,)}),)})})
    before = count(database)
    with pytest.raises(ServiceError) as error:
        save(actor, current, database)
    assert error.value.code == 'VERSION_CONFLICT' and count(database) == before
    assert save(actor, request, database) == first


def test_typing_does_not_conflict_or_enter_profile(workspace):
    from cn_contract.assistant.profile_store import read_profile
    database, actor, value, request = setup(workspace)
    with database.session() as db:
        service.save_draft(actor, value.scope.conversation_id, d.AssistantDraftInput(expected_scope=value.scope,
            expected_composer_revision=value.composer_revision, content='未发送私密草稿'), db)
    save(actor, request, database)
    assert '未发送私密草稿' not in read_profile(actor, value.scope.conversation_id, database=database).model_dump_json()


@pytest.mark.parametrize('mutation', ['session','scope','archive','restore'])
def test_recheck_after_source_io_blocks_revocation_or_scope_change(workspace, monkeypatch, mutation):
    from cn_contract.assistant import profile_store
    database, actor, value, request = setup(workspace)
    original = profile_store.read_profile_sources
    def changed(*args, **kwargs):
        snapshot = original(*args, **kwargs)
        with database.session() as db:
            if mutation == 'session':
                db.get(SessionRow, str(actor.session_id)).revoked = True
            elif mutation == 'scope':
                db.execute(text('UPDATE assistant_conversations SET input_revision=input_revision+1'))
            elif mutation == 'archive':
                db.execute(text("UPDATE assistant_conversations SET archived_at='2026-01-01T00:00:00+00:00'"))
            else:
                db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
        return snapshot
    monkeypatch.setattr(profile_store, 'read_profile_sources', changed)
    with pytest.raises(ServiceError):
        save(actor, request, database)
    assert count(database) == (0, 0, 0, 0)


@pytest.mark.parametrize('same_key', [True, False])
def test_concurrent_commands_have_one_atomic_winner(workspace, same_key):
    database, actor, _, request = setup(workspace)
    barrier = Barrier(2)
    def submit(index):
        barrier.wait(timeout=10)
        try:
            return save(actor, request if same_key or index == 0 else request.model_copy(update={'request_id':uuid4()}), database)
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    if same_key:
        assert results[0] == results[1]
    else:
        assert len([r for r in results if r == 'VERSION_CONFLICT']) == 1
    assert count(database) == (1, 1, 1, 1)


def test_manual_clear_and_legacy_page_edit_stay_protected(workspace):
    from cn_contract.assistant.profile_store import read_profile
    database, actor, value, request = setup(workspace)
    first = save(actor, request, database)
    with database.session() as db:
        record = intake.read(first.intake_id, actor, db)
        draft = d.IntakeDraft.model_validate(record.model_dump(include=set(d.IntakeDraft.model_fields)))
        record = intake.save(record.id, d.IntakeUpdateInput(expected_revision=record.revision,
            draft=draft.model_copy(update={'consultation':'律师在旧接待页面修正的合成表述'})), actor, db)
    second = save(actor, next_request(request, first, expected_intake_revision=record.revision), database)
    assert second.profile_changed and not second.projection_changed and second.consultation_origin == 'user'
    third = save(actor, next_request(request, second, manual_edits=(d.ProfileEdit(
        field='consultation', value={'kind':'null','value':None}),)), database)
    assert third.projection_changed and third.consultation_origin == 'user'
    state = read_profile(actor, value.scope.conversation_id, database=database)
    assert next(f for f in state.fields if f.field == 'consultation').protected_value.kind == 'null'
    with database.session() as db:
        assert intake.read(first.intake_id, actor, db).consultation == ''
        assert intake.read(first.intake_id, actor, db, revision=1).consultation == '合成客户自述，尚待核实。'


def test_nonowner_cannot_read_history_receipt_or_submit(workspace):
    from cn_contract.assistant.profile_store import read_profile, find_receipt
    database, actor, value, request = setup(workspace)
    save(actor, request, database)
    stranger = workspace[1]['reviewer']
    for operation in (lambda:read_profile(stranger, value.scope.conversation_id, database=database),
            lambda:find_receipt(stranger, value.scope.conversation_id, request.request_id, database=database),
            lambda:save(stranger, request, database)):
        with pytest.raises(ServiceError) as error:
            operation()
        assert error.value.code == 'CROSS_MATTER_DENIED'


def test_converted_target_blocks_new_save_but_preserves_receipt(workspace):
    from cn_contract.assistant.profile_store import find_receipt
    database, actor, value, request = setup(workspace)
    first = save(actor, request, database)
    matter_id = add_matter(database, actor)
    with database.session() as db:
        db.execute(text('UPDATE intake_cases SET matter_id=:mid WHERE id=:iid'),
            {'mid':str(matter_id),'iid':str(first.intake_id)})
    before = count(database)
    with pytest.raises(ServiceError):
        save(actor, next_request(request, first), database)
    assert count(database) == before
    assert find_receipt(actor, value.scope.conversation_id, request.request_id, database=database) == first


def test_existing_intake_fields_are_protected_on_first_link(workspace):
    database, actors, _, _ = workspace
    actor = actors['lawyer']
    profile_schema.initialize_storage(database)
    with database.session() as db:
        original = intake.create(d.IntakeCreateInput(request_id=uuid4(),
            draft=d.IntakeDraft(title='已登记的合成咨询',consultation='')), actor, db)
    value = sent(workspace, scope_kind='intake', scope_ref=original.id)
    request = d.ProfileCommitInput(request_id=uuid4(), patch=patch(value.scope,(msg_ref(value),)),
        expected_intake_id=original.id, expected_intake_revision=1, project_intake=True)
    result = save(actor, request, database)
    assert result.profile_changed and not result.projection_changed
    with database.session() as db:
        assert intake.read(original.id, actor, db).consultation == ''
    assert count(database) == (1,1,1,1)


def test_same_subject_in_distinct_conversations_never_merges_clients(workspace):
    database, actor, _, first_request = setup(workspace)
    second_value = sent(workspace)
    second_request = d.ProfileCommitInput(request_id=first_request.request_id,
        patch=patch(second_value.scope,(msg_ref(second_value),)), project_intake=True)
    first = save(actor, first_request, database)
    second = save(actor, second_request, database)
    assert first.intake_id != second.intake_id and count(database) == (2,2,2,2)


@pytest.mark.parametrize('edited', [False, True])
def test_predictable_creation_key_cannot_link_a_preexisting_intake(workspace, edited):
    from uuid import uuid5, NAMESPACE_URL
    from cn_contract.assistant.profile_sources import read_profile_sources
    from cn_contract.assistant.profiles import merge_profile
    database, actor, value, request = setup(workspace)
    projection = merge_profile(None, request.patch, read_profile_sources(actor, request.patch, database=database),
        project_intake=True).projection
    with database.session() as db:
        original = intake.create(d.IntakeCreateInput(request_id=uuid5(NAMESPACE_URL,
            f'qx-profile:{value.scope.conversation_id}:{request.request_id}'), draft=projection), actor, db)
        if edited:
            intake.save(original.id,d.IntakeUpdateInput(expected_revision=1,
                draft=projection.model_copy(update={'consultation':'手工修改后的既有接待'})),actor,db)
    before = count(database)
    with pytest.raises(ServiceError) as error:
        save(actor, request, database)
    assert error.value.code == 'VERSION_CONFLICT' and count(database) == before


@pytest.mark.parametrize('fault', ['half_target','duplicate_manual','forged_nested','owner'])
def test_command_dto_rejects_invalid_or_unauthorized_claims(workspace, fault):
    database, actor, _, request = setup(workspace)
    data = request.model_dump(mode='python')
    if fault == 'half_target': data['expected_intake_id'] = uuid4()
    elif fault == 'duplicate_manual':
        edit = d.ProfileEdit(field='title', value={'kind':'text','value':'合成标题'})
        data['manual_edits'] = (edit, edit)
    elif fault == 'owner': data['owner_id'] = uuid4()
    else:
        invalid = request.patch.changes[0].model_copy(update={'verification':'confirmed'})
        data['patch'] = request.patch.model_copy(update={'changes':(invalid,)})
        request = request.model_copy(update=data)
        with pytest.raises(ValidationError):
            save(actor, request, database)
        return
    with pytest.raises(ValidationError):
        d.ProfileCommitInput(**data)
