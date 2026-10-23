"""Independent synthetic seam probes, excluding the main six-file regression."""
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachment_schema, profile_schema, profile_store, service
from cn_contract.assistant import profile_preparation_service as trusted
from cn_contract.intake import service as intake
from cn_contract.persistence import MembershipRow
from cn_contract.record_codec import encode, sha
from cn_contract.security import ServiceError
from tests.integration.test_assistant_storage import workspace, add_matter


def config():
    return d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='1',
        output_usd_per_million='2', price_reference='independent synthetic review only')


@pytest.fixture
def source(workspace):
    database, actors, _, _ = workspace
    actor = actors['lawyer']
    attachment_schema.initialize_storage(database)
    profile_schema.initialize_storage(database)
    with database.session() as db:
        value = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        value = service.save_draft(actor, value.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=value.scope, expected_composer_revision=0, content='独立合成：甲称有未付货款。'), db)
    return database, actors, value


def submission(value):
    return d.AssistantMessageInput(request_id=uuid4(), expected_scope=value.scope,
        expected_composer_revision=value.composer_revision, content=value.draft_input)


def save(database, actor, value):
    message = submission(value)
    with database.session() as db:
        basis = trusted.build_profile_basis(actor, value.scope.conversation_id, message, db, config=config())
        run = service.save_message(actor, value.scope.conversation_id, message, db)
    return message, basis, run


def denied(code, function, *args, **kwargs):
    with pytest.raises(ServiceError) as error:
        function(*args, **kwargs)
    assert error.value.code == code


@pytest.mark.parametrize('stage', ['basis','prepared'])
def test_denial_keeps_existing_audit_transaction_and_rolls_back_pending_changes(source, stage):
    database, actors, value = source
    actor = actors['lawyer']
    matter = add_matter(database, actor)
    cid = value.scope.conversation_id
    with database.session() as db:
        db.execute(text("UPDATE assistant_conversations SET scope_kind='matter',scope_ref=:m,binding_revision=2 WHERE id=:id"),
                   {'m':str(matter), 'id':str(cid)})
        value = service.read_conversation(actor, cid, db)
    message, basis, run = save(database, actor, value) if stage == 'prepared' else (submission(value),None,None)
    with database.session() as db:
        before = db.scalar(text('SELECT count(*) FROM audit_events'))
        draft = db.scalar(text('SELECT draft_input FROM assistant_conversations WHERE id=:id'), {'id':str(cid)})
        db.execute(text('UPDATE assistant_conversations SET draft_input=:value WHERE id=:id'),
                   {'value':'pending caller business change must roll back', 'id':str(cid)})
        # Pending ORM permission change must be flushed, observed, then rolled
        # back by the preexisting denial audit contract, not committed with it.
        db.delete(db.get(MembershipRow, (str(matter),str(actor.user_id))))
        if stage == 'basis':
            denied('CROSS_MATTER_DENIED', trusted.build_profile_basis, actor, cid, message, db, config=config())
        else:
            denied('CROSS_MATTER_DENIED', trusted.prepare_profile, actor, run.id, basis, db, config=config())
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM audit_events')) == before+1
        assert db.get(MembershipRow, (str(matter),str(actor.user_id))) is not None
        assert db.scalar(text('SELECT draft_input FROM assistant_conversations WHERE id=:id'), {'id':str(cid)}) == draft
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 0


def test_stored_run_actor_is_revalidated_beyond_conversation_ownership(source):
    database, actors, value = source
    actor = actors['lawyer']
    _, basis, run = save(database, actor, value)
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_run_input'))
        db.execute(text('UPDATE assistant_runs SET actor_id=:id WHERE id=:run'),
                   {'id':str(actors['reviewer'].user_id),'run':str(run.id)})
    with database.session() as db:
        denied('CROSS_MATTER_DENIED', trusted.prepare_profile, actor, run.id, basis, db, config=config())


def test_same_revision_intake_replacement_cannot_retarget_prepared_save(source):
    database, actors, value = source
    actor = actors['lawyer']
    with database.session() as db:
        targets = [intake.create(d.IntakeCreateInput(request_id=uuid4(),draft=d.IntakeDraft(title='同名同版本合成接待')),
                    actor, db) for _ in range(2)]
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:target WHERE id=:id'),
                   {'target':str(targets[0].id), 'id':str(value.scope.conversation_id)})
    _, basis, run = save(database, actor, value)
    assert basis.expected_intake_id == targets[0].id
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:target WHERE id=:id'),
                   {'target':str(targets[1].id), 'id':str(value.scope.conversation_id)})
        denied('VERSION_CONFLICT', trusted.prepare_profile, actor, run.id, basis, db, config=config())


def test_valid_digest_same_revision_profile_with_different_scope_is_rejected(source):
    database, actors, value = source
    actor = actors['lawyer']
    with database.session() as db:
        profile_store._commit(actor, d.ProfileCommitInput(request_id=uuid4(),
            patch=d.ProfilePatch(scope=value.scope,base_profile_revision=0),
            manual_edits=(d.ProfileEdit(field='title',value={'kind':'text','value':'合成标题'}),)),
            d.ProfileSourceSnapshot(scope=value.scope), db)
    _, basis, run = save(database, actor, value)
    with database.session() as db:
        previous = profile_store._profile(value.scope.conversation_id,db)
        changed = previous.model_copy(update={'scope':previous.scope.model_copy(update={
            'scope_kind':'matter', 'scope_ref':uuid4()})})
        db.execute(text('DROP TRIGGER immutable_assistant_profile_revisions_update'))
        db.execute(text('UPDATE assistant_profile_revisions SET profile_json=:raw,profile_sha256=:sha'),
                   {'raw':encode(changed.model_dump(mode='json')),'sha':sha(changed.model_dump(mode='json'))})
        # The existing low-level reader accepts the hash/cid/workspace; the new
        # seam must additionally reject fixed binding mismatch before preparing.
        assert profile_store._profile(value.scope.conversation_id,db) == changed
        denied('VERSION_CONFLICT', trusted.prepare_profile, actor, run.id, basis, db, config=config())


def test_cold_import_does_not_load_application_provider_or_parser_entrypoints():
    script = '''import json, sys
import cn_contract.assistant.profile_preparation_service
prefixes = ('cn_contract.web','cn_contract.desktop','cn_contract.assistant.providers.main',
            'cn_contract.assistant.registry','httpx','fastapi','fitz','pypdf')
bad = [name for name in sys.modules if any(name == p or name.startswith(p+'.') for p in prefixes)]
print(json.dumps({'loaded_forbidden_modules':bad}, sort_keys=True))
assert not bad
'''
    result = subprocess.run([sys.executable,'-X','utf8','-c',script], cwd=Path(__file__).resolve().parents[3],
                            capture_output=True,text=True,timeout=45)
    assert result.returncode == 0, result.stderr+result.stdout
    assert json.loads(result.stdout) == {'loaded_forbidden_modules':[]}
