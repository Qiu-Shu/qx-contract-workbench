"""Independent synthetic probes for the trusted profile preparation contract."""
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests' / 'integration'))

from cn_contract import domain as d
from cn_contract.assistant import attachment_records, profile_preparation_service as trusted, service
from cn_contract.security import ServiceError
from test_assistant_storage import workspace
from test_assistant_profile_trusted_preparation import source, config, saved, prepare
from test_assistant_profile_sources import state


@pytest.mark.parametrize('stage', ['basis', 'prepared'])
@pytest.mark.parametrize('raw', ['{}', '""'])
def test_non_array_material_snapshot_must_not_become_empty_selection(source, stage, raw):
    database, actor, value, submission = source
    with database.session() as db:
        row = service._owned(actor, value.scope.conversation_id, db)
        attachment_records.snapshot(row, (), 'selection', uuid4(), '0' * 64, actor, db)
        current = service.read_conversation(actor, value.scope.conversation_id, db)
    submission = submission.model_copy(update={'expected_scope': current.scope})
    source = database, actor, current, submission
    basis, run = saved(source) if stage == 'prepared' else (None, None)
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_material_snapshots_update'))
        db.execute(text('UPDATE assistant_material_snapshots SET items_json=:raw'), {'raw': raw})
    before = state(database)
    with database.session() as db, pytest.raises(ServiceError) as error:
        if stage == 'basis':
            trusted.build_profile_basis(actor, current.scope.conversation_id, submission, db, config=config())
        else:
            trusted.prepare_profile(actor, run.id, basis, db, config=config())
    assert error.value.code == 'VERSION_CONFLICT'
    assert state(database) == before


def test_saved_source_and_preparation_share_callers_transaction_and_rollback(source):
    database, actor, value, submission = source
    before = state(database)
    with pytest.raises(RuntimeError, match='synthetic caller rollback'):
        with database.session() as db:
            basis = trusted.build_profile_basis(actor, value.scope.conversation_id, submission, db, config=config())
            run = service.save_message(actor, value.scope.conversation_id, submission, db)
            result = trusted.prepare_profile(actor, run.id, basis, db, config=config())
            assert result.request.message_id == run.message_id
            assert result.request.content == submission.content
            raise RuntimeError('synthetic caller rollback')
    assert state(database) == before


def test_existing_generation_metadata_does_not_become_a_new_execution_gate(source):
    database, actor, _, _ = source
    basis, run = saved(source)
    first = prepare(source, run, basis)
    with database.session() as db:
        db.execute(text("UPDATE assistant_runs SET state='generating',selected_provider='deepseek',"
                        "selected_model='deepseek-chat' WHERE id=:id"), {'id': str(run.id)})
    before = state(database)
    assert prepare(source, run, basis) == first
    assert state(database) == before


def test_actor_identity_column_is_explicitly_bound_even_if_request_digest_is_unchanged(source, workspace):
    database, _, _, _ = source
    basis, run = saved(source)
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_run_input'))
        db.execute(text('UPDATE assistant_runs SET actor_id=:actor WHERE id=:id'),
                   {'actor': str(workspace[1]['reviewer'].user_id), 'id': str(run.id)})
    with pytest.raises(ServiceError) as error:
        prepare(source, run, basis)
    assert error.value.code == 'CROSS_MATTER_DENIED'


def test_preparation_has_no_runtime_callers_and_guard_is_preserved():
    files = list((ROOT / 'src').rglob('*.py')) + list((ROOT / 'desktop').rglob('*.cjs'))
    files = [path for path in files if 'node_modules' not in path.parts]
    needle = 'profile_preparation_service'
    references = [str(path.relative_to(ROOT)) for path in files if needle in path.read_text(encoding='utf-8')]
    assert references == []
    guard = (ROOT / 'src/cn_contract/assistant/model_integrity.py').read_text(encoding='utf-8')
    assert "raise ValueError('ASSISTANT_PROFILE_MODEL_NOT_ENABLED')" in guard
