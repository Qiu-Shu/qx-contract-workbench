"""Independent publication-stage probes: synthetic local SQLite only."""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

# Existing integration helpers use sibling imports when collected in their folder.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tests'/'integration'))

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import model_integrity, profile_integrity, profile_store
from cn_contract.config import load_settings
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_model_backup import reserved


@pytest.fixture
def empty_database(tmp_path):
    database = Database('sqlite:///' + str(tmp_path/'独立空账本.db'), tmp_path/'原件', load_settings())
    initialize_storage(database)
    yield database
    database.engine.dispose()


@pytest.mark.parametrize('allowed', [True, False])
def test_orphan_handler_precedes_empty_model_return(empty_database, allowed):
    database = empty_database
    with closing(sqlite3.connect(database.engine.url.database)) as raw:
        raw.execute('''INSERT INTO assistant_profile_handlers
            (run_id,event_seq,handler_id,handler_version,attempt_id,output_id,conversation_id,
             outcome,reason_code,basis_sha256,created_at)
            VALUES ('absent-run',1,'profile.save','1','absent-attempt','absent-output','absent-conversation',
                    'blocked','version_conflict',?,'2026-10-23T00:00:00+00:00')''', ('b'*64,))
        raw.commit()
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        with pytest.raises(ValueError, match='^ASSISTANT_PROFILE_MODEL_NOT_ENABLED$'):
            model_integrity.validate_model_records(db, allowed=allowed)


def test_new_attempt_refused_before_any_legacy_shape_or_identity(empty_database):
    database = empty_database
    with closing(sqlite3.connect(database.engine.url.database)) as raw:
        raw.execute('''INSERT INTO assistant_model_attempts
            (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
             input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format,round_no)
            VALUES ('a','r','c','p',?,?,?,'{}','{}','{}','0','2026-10-23T00:00:00+00:00',
                    'reserved','2026-10-23T00:00:00+00:00','profile-text-v1',1)''', ('0'*64,)*3)
        raw.commit()
    with database.session() as db, pytest.raises(ValueError, match='^ASSISTANT_PROFILE_MODEL_NOT_ENABLED$'):
        backup._file_references(db)


def test_real_legacy_profile_replayed_and_tamper_refused_on_successor(world):
    database, actor, conversation, *_ = world
    request = d.ProfileCommitInput(request_id=uuid4(),
        patch=d.ProfilePatch(scope=conversation.scope, base_profile_revision=0, changes=()),
        manual_edits=(d.ProfileEdit(field='title', value={'kind':'text','value':'独立合成档案'}),))
    receipt = profile_store.save_profile(actor, request, database=database)
    assert receipt.profile_changed and receipt.profile_revision == 1
    with database.session() as db:
        profile_integrity.validate_profile_records(db)
        assert backup._file_references(db) == []
    corrupt(database, 'assistant_profile_revisions',
            'UPDATE assistant_profile_revisions SET profile_sha256=?', ('0'*64,))
    with database.session() as db, pytest.raises(ValueError, match='^ASSISTANT_PROFILE_INTEGRITY$'):
        backup._file_references(db)


def test_nonempty_legacy_model_retains_context_and_v2_rounds_validation(world, monkeypatch):
    database, *_ = world
    reserved(world)
    calls = []
    original = model_integrity._validate
    def observe(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)
    monkeypatch.setattr(model_integrity, '_validate', observe)
    with database.session() as db:
        model_integrity.validate_model_records(db)
    assert calls == [{'context_schema':True, 'rounds':'v2'}]


def test_new_empty_family_still_rejects_legacy_model_digest_tamper(world):
    database, *_ = world
    reserved(world)
    corrupt(database, 'assistant_model_attempts',
            'UPDATE assistant_model_attempts SET request_sha256=?', ('0'*64,))
    with database.session() as db, pytest.raises(ValueError, match='^ASSISTANT_MODEL_INTEGRITY$'):
        backup._file_references(db)
