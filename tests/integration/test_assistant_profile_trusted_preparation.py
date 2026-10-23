"""Actual SQLite state, not caller-supplied saved views, binds profile preparation."""
import importlib
import json
import warnings
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachment_records, attachment_schema, profile_schema, profile_store, service
from cn_contract.intake import service as intake
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.persistence import MembershipRow, SessionRow, UserRow
from cn_contract.record_codec import encode, sha
from cn_contract.security import ServiceError, authenticate, login
from test_assistant_main_provider import config
from test_assistant_profile_sources import state
from test_assistant_storage import workspace, add_matter


def api():
    try:
        return importlib.import_module('cn_contract.assistant.profile_preparation_service')
    except ModuleNotFoundError:
        pytest.fail('trusted database profile preparation is not implemented')


@pytest.fixture
def source(workspace):
    database, actors, _, _ = workspace
    actor = actors['lawyer']
    attachment_schema.initialize_storage(database)
    profile_schema.initialize_storage(database)
    with database.session() as db:
        value = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        value = service.save_draft(actor, value.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=value.scope, expected_composer_revision=value.composer_revision,
            content='完全合成：甲称已经付款35000元。'), db)
    submission = d.AssistantMessageInput(request_id=uuid4(), expected_scope=value.scope,
        expected_composer_revision=value.composer_revision, content=value.draft_input)
    return database, actor, value, submission


def basis_for(source, **options):
    database, actor, value, submission = source
    with database.session() as db:
        return api().build_profile_basis(actor, value.scope.conversation_id, submission, db,
                                         config=config(), **options)


def saved(source):
    database, actor, value, submission = source
    basis = basis_for(source)
    with database.session() as db:
        run = service.save_message(actor, value.scope.conversation_id, submission, db)
    return basis, run


def prepare(source, run, basis, **options):
    database, actor, _, _ = source
    with database.session() as db:
        return api().prepare_profile(actor, run.id, basis, db, config=options.get('config', config()))


def test_database_preparation_reads_exact_saved_text_without_side_effects(source):
    database, actor, value, submission = source
    before = state(database)
    basis = basis_for(source, project_intake=True)
    assert (basis.base_profile_revision, basis.expected_intake_id, basis.expected_intake_revision) == (0, None, None)
    assert basis.project_intake is True
    assert state(database) == before
    with database.session() as db:
        run = service.save_message(actor, value.scope.conversation_id, submission, db)
    before = state(database)
    prepared = prepare(source, run, basis)
    assert prepared.request.content == submission.content
    assert prepared.request.run_id == run.id and prepared.request.message_id == run.message_id
    assert prepared.request.source_revision == value.scope.input_revision + 1
    assert prepared.composer_revision == value.composer_revision + 1
    assert prepared.basis == basis
    assert state(database) == before
    with database.session() as db:
        assert service.get_run(actor, run.id, db).state == 'queued'
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 0


def denied(function, *args, code='VERSION_CONFLICT', **options):
    with pytest.raises(ServiceError) as error:
        function(*args, **options)
    assert error.value.code == code
    return error.value


@pytest.mark.parametrize('change', ['scope', 'composer', 'draft', 'skill', 'attachment'])
def test_basis_checks_current_draft_and_submission_bounds(source, change):
    database, actor, value, submission = source
    replacement = {'scope':{'expected_scope':value.scope.model_copy(update={'input_revision':1})},
        'composer':{'expected_composer_revision':value.composer_revision+1},
        'draft':{'content':submission.content+'新增一句'}, 'skill':{'requested_skill':'client_reply'},
        'attachment':{'attachment_ids':(uuid4(),)}}[change]
    before = state(database)
    with database.session() as db:
        denied(api().build_profile_basis, actor, value.scope.conversation_id,
            submission.model_copy(update=replacement), db, config=config(),
            code='NOT_SUPPORTED' if change in ('skill', 'attachment') else 'VERSION_CONFLICT')
    assert state(database) == before


def test_typing_does_not_rewrite_saved_source_or_original_request_revision(source):
    database, actor, value, _ = source
    basis, run = saved(source)
    first = prepare(source, run, basis)
    with database.session() as db:
        current = service.read_conversation(actor, value.scope.conversation_id, db)
        service.save_draft(actor, value.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=current.scope, expected_composer_revision=current.composer_revision,
            content='新草稿不能进入之前的模型请求'), db)
        db.execute(text("UPDATE assistant_runs SET state='generating' WHERE id=:id"), {'id':str(run.id)})
    before = state(database)
    assert prepare(source, run, basis) == first
    assert state(database) == before


@pytest.mark.parametrize('change', ['input_revision', 'binding_revision', 'materials_revision', 'composer_revision'])
def test_preparation_requires_current_post_save_scope_and_nonregressing_composer(source, change):
    database, _, value, _ = source
    basis, run = saved(source)
    with database.session() as db:
        operation = 'composer_revision=0' if change == 'composer_revision' else change+'='+change+'+1'
        db.execute(text('UPDATE assistant_conversations SET '+operation+' WHERE id=:id'), {'id':str(value.scope.conversation_id)})
    before = state(database)
    denied(prepare, source, run, basis)
    assert state(database) == before


@pytest.mark.parametrize('change,code', [('owner','CROSS_MATTER_DENIED'), ('session','AUTHORIZATION_REQUIRED'),
    ('role','CROSS_MATTER_DENIED'), ('workspace','CROSS_MATTER_DENIED'),
    ('archived','VERSION_CONFLICT'), ('restore','BLOCKED_LIVE')])
@pytest.mark.parametrize('stage', ['basis', 'prepared'])
def test_current_permissions_and_restore_apply_at_both_stages(source, workspace, change, code, stage):
    database, actor, value, submission = source
    basis, run = saved(source) if stage == 'prepared' else (None, None)
    with database.session() as db:
        if change == 'owner':
            actor = workspace[1]['reviewer']
        elif change == 'session':
            db.get(SessionRow, str(actor.session_id)).revoked = True
        elif change == 'role':
            db.get(UserRow, str(actor.user_id)).roles = json.dumps(['admin'])
        elif change == 'workspace':
            db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
        elif change == 'archived':
            db.execute(text('UPDATE assistant_conversations SET archived_at=:at'), {'at':service._at()})
        else:
            db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    before = state(database)
    with database.session() as db:
        if stage == 'basis':
            denied(api().build_profile_basis, actor, value.scope.conversation_id, submission, db, config=config(), code=code)
        else:
            denied(api().prepare_profile, actor, run.id, basis, db, config=config(), code=code)
    assert state(database) == before


def test_another_live_session_of_same_owner_cannot_prepare_saved_run(source):
    database, _, _, _ = source
    basis, run = saved(source)
    with database.session() as db:
        token, _ = login('lawyer', 'only-fictional-password', db)
        other = authenticate(token, db)
    with database.session() as db:
        denied(api().prepare_profile, other, run.id, basis, db, config=config(), code='CROSS_MATTER_DENIED')


@pytest.mark.parametrize('change', ['cancel', 'completed', 'request_digest', 'request_id', 'run_scope',
                                     'other_message', 'message_text', 'message_revision', 'message_role'])
def test_actual_run_and_message_cannot_be_substituted(source, change):
    database, actor, value, _ = source
    basis, run = saved(source)
    with database.session() as db:
        if change.startswith('message_') or change == 'other_message':
            db.execute(text('DROP TRIGGER immutable_assistant_messages_update'))
            if change == 'other_message':
                other = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
                updates = {'conversation_id':str(other.scope.conversation_id)}
            else:
                updates = {'message_text':{'content':'不同的合成原话'}, 'message_revision':{'source_revision':2},
                           'message_role':{'role':'assistant'}}[change]
            table, identifier = 'assistant_messages', run.message_id
        else:
            db.execute(text('DROP TRIGGER immutable_assistant_run_input'))
            updates = {'cancel':{'cancel_requested':1}, 'completed':{'state':'completed'},
                'request_digest':{'request_sha256':'0'*64}, 'request_id':{'request_id':str(uuid4())},
                'run_scope':{'scope_snapshot':value.scope.model_dump_json()}}[change]
            table, identifier = 'assistant_runs', run.id
        db.execute(text('UPDATE '+table+' SET '+','.join(key+'=:'+key for key in updates)+' WHERE id=:id'),
                   updates | {'id':str(identifier)})
    before = state(database)
    denied(prepare, source, run, basis, code='STATE_CONFLICT' if change in ('cancel', 'completed') else 'VERSION_CONFLICT')
    assert state(database) == before


def test_selected_materials_are_read_from_database_even_when_submission_is_empty(source):
    database, actor, value, submission = source
    with database.session() as db:
        row = service._owned(actor, value.scope.conversation_id, db)
        attachment_records.snapshot(row, (d.AssistantMaterialRef(attachment_id=uuid4(), parse_revision=None),),
                                    'selection', uuid4(), '0'*64, actor, db)
        current = service.read_conversation(actor, value.scope.conversation_id, db)
    submission = submission.model_copy(update={'expected_scope':current.scope})
    with database.session() as db:
        denied(api().build_profile_basis, actor, value.scope.conversation_id, submission, db,
               config=config(), code='NOT_SUPPORTED')


def intake_target(source, *, bound=False):
    database, actor, value, submission = source
    with database.session() as db:
        target = intake.create(d.IntakeCreateInput(request_id=uuid4(), draft=d.IntakeDraft(title='合成接待')), actor, db)
        if bound:
            db.execute(text("UPDATE assistant_conversations SET scope_kind='intake',scope_ref=:target,binding_revision=2 WHERE id=:id"),
                       {'id':str(value.scope.conversation_id), 'target':str(target.id)})
        else:
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:target WHERE id=:id'),
                       {'id':str(value.scope.conversation_id), 'target':str(target.id)})
        value = service.read_conversation(actor, value.scope.conversation_id, db)
    return (database, actor, value, submission.model_copy(update={'expected_scope':value.scope})), target


@pytest.mark.parametrize('bound', [False, True])
def test_basis_uses_actual_intake_target_and_does_not_refresh_its_saved_revision(source, bound):
    source, target = intake_target(source, bound=bound)
    database, actor, _, _ = source
    basis, run = saved(source)
    assert (basis.expected_intake_id, basis.expected_intake_revision) == (target.id, 1)
    prepare(source, run, basis)
    with database.session() as db:
        intake.save(target.id, d.IntakeUpdateInput(expected_revision=1, draft=d.IntakeDraft(title='人工修改接待')), actor, db)
    denied(prepare, source, run, basis)


@pytest.mark.parametrize('stage', ['basis', 'prepared'])
def test_converted_intake_is_not_a_save_target_even_if_still_authorized(source, stage):
    source, target = intake_target(source)
    database, actor, value, submission = source
    basis, run = saved(source) if stage == 'prepared' else (None, None)
    matter = add_matter(database, actor)
    with database.session() as db:
        db.execute(text('UPDATE intake_cases SET matter_id=:matter WHERE id=:id'), {'matter':str(matter), 'id':str(target.id)})
    with database.session() as db:
        if stage == 'basis':
            denied(api().build_profile_basis, actor, value.scope.conversation_id, submission, db, config=config())
        else:
            denied(api().prepare_profile, actor, run.id, basis, db, config=config())


def test_profile_revision_is_rebuilt_but_never_replaced_in_existing_basis(source):
    database, actor, value, _ = source
    with database.session() as db:
        receipt = profile_store._commit(actor, d.ProfileCommitInput(request_id=uuid4(),
            patch=d.ProfilePatch(scope=value.scope, base_profile_revision=0),
            manual_edits=(d.ProfileEdit(field='title', value={'kind':'text','value':'人工合成标题'}),)),
            d.ProfileSourceSnapshot(scope=value.scope), db)
    assert receipt.profile_revision == 1
    basis, run = saved(source)
    assert basis.base_profile_revision == 1
    prepare(source, run, basis)
    with database.session() as db:
        current = service.read_conversation(actor, value.scope.conversation_id, db)
        profile_store._commit(actor, d.ProfileCommitInput(request_id=uuid4(),
            patch=d.ProfilePatch(scope=current.scope, base_profile_revision=1),
            manual_edits=(d.ProfileEdit(field='title', value={'kind':'text','value':'更新后的合成标题'}),)),
            d.ProfileSourceSnapshot(scope=current.scope), db)
    denied(prepare, source, run, basis)


@pytest.mark.parametrize('change', ['binding_revision', 'input_revision', 'materials_revision'])
def test_profile_with_incompatible_or_future_source_scope_blocks_basis(source, change):
    database, _, value, _ = source
    profile = d.ProfileDraftState(scope=value.scope.model_copy(update={change:getattr(value.scope, change)+1}), revision=1)
    with database.session() as db:
        db.execute(text('''INSERT INTO assistant_profile_revisions VALUES (:cid,1,:profile,:sha,:at)'''),
            {'cid':str(value.scope.conversation_id), 'profile':encode(profile.model_dump(mode='json')),
             'sha':sha(profile.model_dump(mode='json')), 'at':service._at()})
    denied(basis_for, source)


def test_config_change_or_forged_saved_composer_cannot_reuse_basis(source):
    basis, run = saved(source)
    denied(prepare, source, run, basis, config=config(max_output_tokens=100))
    # Same text/wire but a different original composer must fail the persisted request digest.
    denied(prepare, source, run, basis.model_copy(update={'expected_composer_revision':0}))


@pytest.mark.parametrize('kind', ['message', 'basis', 'actor', 'config'])
def test_forged_dto_is_revalidated_without_echoing_payload(source, kind):
    database, actor, value, submission = source
    if kind == 'basis':
        basis, run = saved(source)
        error = denied(prepare, source, run, basis.model_copy(update={'purpose':'private malformed text'}))
    else:
        with warnings.catch_warnings(record=True) as warning_records, database.session() as db:
            warnings.simplefilter('always')
            error = denied(api().build_profile_basis,
                actor.model_copy(update={'session_id':'private malformed text'}) if kind == 'actor' else actor,
                value.scope.conversation_id,
                submission.model_copy(update={'attachment_ids':'private malformed text'}) if kind == 'message' else submission,
                db, config=config().model_copy(update={'max_output_tokens':'private malformed text'}) if kind == 'config' else config())
        assert not warning_records
    assert 'private malformed text' not in str(error)


@pytest.mark.parametrize('stage', ['basis', 'prepared'])
def test_revoked_matter_access_preserves_denial_audit_without_profile_writes(source, stage):
    database, actor, value, submission = source
    matter = add_matter(database, actor)
    with database.session() as db:
        db.execute(text("UPDATE assistant_conversations SET scope_kind='matter',scope_ref=:matter,binding_revision=2 WHERE id=:id"),
                   {'matter':str(matter), 'id':str(value.scope.conversation_id)})
        value = service.read_conversation(actor, value.scope.conversation_id, db)
    source = database, actor, value, submission.model_copy(update={'expected_scope':value.scope})
    basis, run = saved(source) if stage == 'prepared' else (None, None)
    with database.session() as db:
        db.delete(db.get(MembershipRow, (str(matter), str(actor.user_id))))
        previous = db.scalar(text('SELECT count(*) FROM audit_events'))
    with database.session() as db:
        if stage == 'basis':
            denied(api().build_profile_basis, actor, value.scope.conversation_id, source[3], db,
                   config=config(), code='CROSS_MATTER_DENIED')
        else:
            denied(api().prepare_profile, actor, run.id, basis, db, config=config(), code='CROSS_MATTER_DENIED')
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM audit_events')) == previous+1
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_revisions')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 0
