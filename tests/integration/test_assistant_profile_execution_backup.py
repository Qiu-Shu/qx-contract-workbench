"""Authenticated synthetic profile archives preserve receipts but cannot resend."""
import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from cn_contract.assistant import profile_store
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.policy import sha
from cn_contract.config import canonical_json as encoded
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import profile_world
from tests.integration.test_assistant_profile_model_integrity import profile_history


def records(db):
    return {table:[dict(row) for row in db.execute(text('SELECT * FROM '+table)).mappings()]
            for table in ('assistant_profile_handlers', 'assistant_profile_receipts',
                          'assistant_profile_revisions', 'assistant_model_outputs')}


@pytest.mark.parametrize('state', ['received', 'unchanged', 'blocked', 'reserved', 'sending',
                                  'sent_unknown', 'failed_before_send'])
def test_profile_qxbak_recovery_preserves_atomic_history_and_never_resends(profile_world, tmp_path, monkeypatch, state):
    database, _, _, _ = profile_world
    if state == 'blocked':
        def failure(*args):
            raise ValueError('synthetic save failure')
        monkeypatch.setattr(profile_store, '_commit', failure)
    view, _, runtime = profile_history(profile_world,
        state='received' if state in ('unchanged', 'blocked') else state, empty=state == 'unchanged')
    with database.session() as db:
        before = records(db)
    root = Path(database.engine.url.database).parent
    original = (root/'workbench.db').read_bytes()
    archive = tmp_path/'合成档案.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    target = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected', database.settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            actual = attempts.read_attempt(actor, view.id, db)
            expected = {'reserved':'failed_before_send', 'sending':'sent_unknown',
                        'unchanged':'received', 'blocked':'received'}.get(state, state)
            assert actual.state == expected and actual.output == view.output
            assert actual.input_format == 'profile-text-v1'
            assert records(db) == before
            assert attempts.recover_attempts(db) == 0
            assert backup._file_references(db) == []
        calls = []
        async def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError('restored profile must never send')
        monkeypatch.setattr(runtime.provider, 'generate_profile', forbidden)
        with pytest.raises(ServiceError) as denied:
            asyncio.run(execute_attempt(actor, view.id, restored, runtime))
        assert denied.value.code == 'BLOCKED_LIVE' and calls == []
        again = tmp_path/'second.qxbak'
        workspace_backup.create_workspace_backup(target, again, PASSPHRASE, data_parent=tmp_path)
        workspace_backup.restore_workspace_backup(again, tmp_path/'again', PASSPHRASE)
    finally:
        restored.engine.dispose()
    assert (root/'workbench.db').read_bytes() == original


@pytest.mark.parametrize('tamper', ['handler_missing', 'rehashed_profile'])
def test_hostile_authenticated_profile_archive_rejects_restore_without_publishing(profile_world, tmp_path, monkeypatch, tamper):
    database, *_ = profile_world
    profile_history(profile_world)
    if tamper == 'handler_missing':
        corrupt(database, 'assistant_profile_handlers', 'DELETE FROM assistant_profile_handlers')
    else:
        with database.session() as db:
            value = json.loads(db.scalar(text('SELECT profile_json FROM assistant_profile_revisions')))
        value['fields'][0]['candidates'][0]['value']['value'] = '99000'
        raw = encoded(value)
        corrupt(database, 'assistant_profile_revisions',
                'UPDATE assistant_profile_revisions SET profile_json=?,profile_sha256=?', (raw,sha(raw)))
    root = Path(database.engine.url.database).parent
    rejected = tmp_path/'must-not-publish.qxbak'
    with pytest.raises(ValueError, match='ASSISTANT_MODEL_INTEGRITY'):
        workspace_backup.create_workspace_backup(root, rejected, PASSPHRASE, data_parent=tmp_path)
    assert not rejected.exists()
    hostile = tmp_path/'authenticated-hostile.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(root, hostile, PASSPHRASE, data_parent=tmp_path)
    original = (root/'workbench.db').read_bytes()
    destination = tmp_path/'must-not-restore'
    with pytest.raises(ValueError, match='ASSISTANT_MODEL_INTEGRITY'):
        workspace_backup.restore_workspace_backup(hostile, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert (root/'workbench.db').read_bytes() == original
