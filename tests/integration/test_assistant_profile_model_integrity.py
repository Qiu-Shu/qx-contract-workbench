"""New archive structure must keep old validation and refuse inactive records."""
from contextlib import closing
import sqlite3

import pytest
from sqlalchemy import text

from cn_contract import storage_schema
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.config import load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt, source
from tests.integration.test_assistant_model_backup import reserved
from tests.integration.test_assistant_generation import world


def validate(database, allowed=True):
    with database.session() as db:
        validate_model_records(db, allowed=allowed)


@pytest.mark.parametrize('native', [False, True])
def test_empty_successor_runs_all_archive_validators(tmp_path, native):
    database = Database('sqlite:///'+str(tmp_path/'empty.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        if native:
            with database.session() as db:
                db.execute(text('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'))
        with database.session() as db:
            rows = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
            assert storage_schema.identify_schema(rows, native=native) == 'assistant-profile-model-v1'
            assert backup._file_references(db) == []
            assert backup._file_references(db, allow_assistant=False) == []
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('allowed', [False, True])
def test_profile_attempt_is_not_accepted_as_plain_history(world, allowed):
    database, *_ = world
    reserved(world)
    corrupt(database, 'assistant_model_attempts',
            "UPDATE assistant_model_attempts SET input_format='profile-text-v1'")
    with pytest.raises(ValueError, match='^ASSISTANT_PROFILE_MODEL_NOT_ENABLED$'):
        validate(database, allowed=allowed)


@pytest.mark.parametrize('allowed', [False, True])
def test_handler_alone_cannot_escape_empty_ledger_guard(source, allowed):
    _, database, *_ = source
    # Deliberately hostile archive rows: SQLite files can arrive with FK checks
    # disabled. No attempt/output is present, so the empty-ledger fast path is tested.
    with closing(sqlite3.connect(database.engine.url.database)) as db:
        db.execute('''INSERT INTO assistant_profile_handlers
            (run_id,event_seq,handler_id,handler_version,attempt_id,output_id,
             conversation_id,outcome,reason_code,basis_sha256,created_at)
            VALUES ('missing-run',1,'profile.save','1','missing-attempt','missing-output',
                    'missing-conversation','blocked','save_failed',?,?)''',
            ('0'*64, '2026-01-01T00:00:00+00:00'))
        db.commit()
    with pytest.raises(ValueError, match='^ASSISTANT_PROFILE_MODEL_NOT_ENABLED$'):
        validate(database, allowed=allowed)


def test_profile_format_rejects_backup_and_authenticated_restore(world, tmp_path, monkeypatch):
    database, *_ = world
    reserved(world)
    corrupt(database, 'assistant_model_attempts',
            "UPDATE assistant_model_attempts SET input_format='profile-text-v1'")
    from pathlib import Path
    root = Path(database.engine.url.database).parent
    rejected = tmp_path/'must-not-publish.qxbak'
    with pytest.raises(ValueError, match='^ASSISTANT_PROFILE_MODEL_NOT_ENABLED$'):
        workspace_backup.create_workspace_backup(root, rejected, PASSPHRASE, data_parent=tmp_path)
    assert not rejected.exists()
    hostile = tmp_path/'synthetic-inactive-format.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, hostile, PASSPHRASE, data_parent=tmp_path)
    before = (root/'workbench.db').read_bytes()
    destination = tmp_path/'must-not-restore'
    with pytest.raises(ValueError, match='^ASSISTANT_PROFILE_MODEL_NOT_ENABLED$'):
        workspace_backup.restore_workspace_backup(hostile, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes() == before
