"""Context archives preserve the fixed format and ordered sources across restore.

The restore entry point rejects a published archive whose link count is stale
(FILE_LIMIT_OR_LINK). Some Windows hosts never report the count dropping after
the staging link is removed, so roundtrips here restore from a byte-identical
copy of the archive — the same trust boundary, a fresh directory entry.
"""
import asyncio
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.runner import execute_attempt
from cn_contract.config import canonical_json
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login, ServiceError
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_context_send import context_world, enqueue
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_model_backup import PASSPHRASE


def restore_copy(archive, destination, tmp_path):
    copied = tmp_path/(archive.stem + '-copy.qxbak')
    shutil.copyfile(archive, copied)
    return workspace_backup.restore_workspace_backup(copied, destination, PASSPHRASE)


def open_restored(result, settings):
    target = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected',
                        settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    return restored


@pytest.mark.parametrize('state', ['reserved', 'sending', 'received', 'sent_unknown', 'failed_before_send'])
def test_context_archive_roundtrip_preserves_format_sources_and_blocks_resend(context_world, tmp_path, state):
    database, actor, view, submission, basis, runtime = context_world
    first = enqueue(context_world)
    if state == 'received':
        first = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    elif state == 'sent_unknown':
        with database.session() as db:
            token, _, _ = attempts.claim(actor, first.id, db, runtime)
            attempts.settle(actor, first.id, token,
                d.MainContextReply(state='sent_unknown', error_code='PROVIDER_ERROR'), db, runtime)
    elif state == 'sending':
        with database.session() as db:
            attempts.claim(actor, first.id, db, runtime)
    elif state == 'failed_before_send':
        with database.session() as db:
            service.cancel_run(actor, first.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
        asyncio.run(execute_attempt(actor, first.id, database, runtime))
    with database.session() as db:
        before = dict(db.execute(text('SELECT * FROM assistant_model_attempts')).mappings().one())
        relations_before = [dict(row) for row in db.execute(text(
            'SELECT * FROM assistant_model_input_citations ORDER BY ordinal')).mappings()]
    root = Path(database.engine.url.database).parent
    original = (root/'workbench.db').read_bytes()
    archive = tmp_path/'synthetic-context.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = restore_copy(archive, tmp_path/'restored', tmp_path)
    restored = open_restored(result, database.settings)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            current = authenticate(token, db)
            view_after = attempts.read_attempt(current, first.id, db)
            expected = {'reserved': 'failed_before_send', 'sending': 'sent_unknown'}.get(state, state)
            assert type(view_after) is d.MainContextAttemptView
            assert view_after.input_format == 'library-context-v1' and view_after.state == expected
            after = dict(db.execute(text('SELECT * FROM assistant_model_attempts')).mappings().one())
            for key in before.keys()-{'state', 'updated_at'}:
                assert before[key] == after[key], key
            assert [dict(row) for row in db.execute(text(
                'SELECT * FROM assistant_model_input_citations ORDER BY ordinal')).mappings()] == relations_before
            if state == 'received':
                assert view_after.output == first.output
            else:
                assert view_after.output is None
            assert backup._file_references(db) == []
        calls = len(runtime.provider.context_calls)
        with pytest.raises(ServiceError) as blocked:
            asyncio.run(execute_attempt(current, first.id, restored, runtime))
        assert blocked.value.code == 'BLOCKED_LIVE'
        assert len(runtime.provider.context_calls) == calls
    finally:
        restored.engine.dispose()
    assert (root/'workbench.db').read_bytes() == original


@pytest.mark.parametrize('fault', [
    'relation_missing', 'relation_order', 'relation_unknown_attempt',
    'format_plain_flip', 'question_tamper', 'basis_tamper',
    'wire_tamper', 'output_forged_citation', 'plain_row_with_relation',
    'second_round',
])
def test_context_archive_rejects_selection_and_format_corruption(context_world, tmp_path, fault):
    database, actor, view, submission, basis, runtime = context_world
    first = asyncio.run(execute_attempt(actor, enqueue(context_world).id, database, runtime))
    identifier = str(first.id)
    if fault == 'relation_missing':
        corrupt(database, 'assistant_model_input_citations',
                'DELETE FROM assistant_model_input_citations')
    elif fault == 'relation_order':
        corrupt(database, 'assistant_model_input_citations',
                'UPDATE assistant_model_input_citations SET ordinal=7')
    elif fault == 'relation_unknown_attempt':
        corrupt(database, 'assistant_model_input_citations',
                'UPDATE assistant_model_input_citations SET attempt_id=?', (str(uuid4()),))
    elif fault == 'format_plain_flip':
        corrupt(database, 'assistant_model_attempts',
                "UPDATE assistant_model_attempts SET input_format='plain-text-v1'")
    elif fault in ('question_tamper', 'basis_tamper', 'wire_tamper'):
        with database.session() as db:
            attempt = dict(db.execute(text('SELECT input_json FROM assistant_model_attempts')).mappings().one())
        prepared = json.loads(attempt['input_json'])
        if fault == 'question_tamper':
            prepared['request']['manifest']['question'] = '篡改后的合成问题'
        elif fault == 'basis_tamper':
            prepared['request']['basis']['manifest_sha256'] = '0'*64
        else:
            wire = json.loads(prepared['wire_payload_json'])
            wire['messages'][0]['content'] = 'Fictional replaced system instructions'
            prepared['wire_payload_json'] = canonical_json(wire)
        corrupt(database, 'assistant_model_attempts',
                'UPDATE assistant_model_attempts SET input_json=?', (canonical_json(prepared),))
    elif fault == 'output_forged_citation':
        with database.session() as db:
            output = dict(db.execute(text('SELECT output_json FROM assistant_model_outputs')).mappings().one())
        forged = json.loads(output['output_json'])
        forged['candidate']['citations'][0]['saved_citation_id'] = str(uuid4())
        corrupt(database, 'assistant_model_outputs',
                'UPDATE assistant_model_outputs SET output_json=?', (canonical_json(forged),))
    elif fault == 'second_round':
        # A hand-inserted second round stays structurally occupiable but is
        # rejected: a v1-format run can never become multi-round, and v2
        # rounds require their persisted plan/tool chain (B2c2 semantics).
        with database.session() as db:
            row = dict(db.execute(text('SELECT * FROM assistant_model_attempts')).mappings().one())
        values = tuple(str(uuid4()) if key == 'id' else 2 if key == 'round_no' else value
                       for key, value in row.items())
        corrupt(database, 'assistant_model_attempts',
                'INSERT INTO assistant_model_attempts (' + ','.join(row) + ') VALUES ('
                + ','.join('?' for _ in row) + ')', values)
    else:
        # A plain-format sibling must never carry context relations.
        with database.session() as db:
            current = service.read_conversation(actor, view.scope.conversation_id, db)
            runtime.policy = d.MainModelPolicy.model_validate(
                {**runtime.policy.model_dump(mode='json'), 'policy_id': str(uuid4()),
                 'allowed_content_sha256s': [basis.manifest_sha256,
                                             attempts.sha('第二轮独立合成普通文字')]})
            plain = attempts.enqueue_generation(actor, view.scope.conversation_id,
                d.AssistantMessageInput(request_id=uuid4(), expected_scope=current.scope,
                    expected_composer_revision=current.composer_revision,
                    content='第二轮独立合成普通文字'), db, runtime)
        corrupt(database, 'assistant_model_input_citations',
                'INSERT INTO assistant_model_input_citations VALUES(?,?,?)',
                (str(plain.id), 0, str(submission.citation_ids[0])))
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        backup._file_references(db)
    archive = tmp_path/'invalid-context.qxbak'
    # An orphaned relation also violates the workspace gate's own FK check,
    # which fires before the archive's model validation either way.
    expected = 'WORKSPACE_DATABASE_MISMATCH' if fault == 'relation_unknown_attempt' else 'ASSISTANT_MODEL'
    with pytest.raises(ValueError, match=expected):
        workspace_backup.create_workspace_backup(Path(database.engine.url.database).parent,
            archive, PASSPHRASE, data_parent=tmp_path)
    assert not archive.exists()
    assert len(runtime.provider.context_calls) == 1


def test_context_history_survives_current_session_revocation(context_world):
    database, actor, _, _, _, runtime = context_world
    asyncio.run(execute_attempt(actor, enqueue(context_world).id, database, runtime))
    with database.session() as db:
        db.execute(text('UPDATE sessions SET revoked=1'))
        db.execute(text('UPDATE users SET disabled=1'))
        assert backup._file_references(db) == []


def test_restore_rejects_authenticated_but_inconsistent_context_archive(context_world, tmp_path, monkeypatch):
    database, actor, view, submission, basis, runtime = context_world
    first = asyncio.run(execute_attempt(actor, enqueue(context_world).id, database, runtime))
    source = Path(database.engine.url.database)
    corrupt(database, 'assistant_model_input_citations',
            'DELETE FROM assistant_model_input_citations')
    before = source.read_bytes()
    hostile = tmp_path/'hostile-context.qxbak'
    # Construct an authenticated hostile fixture while bypassing validation
    # only during fixture assembly; restoration uses the real trust boundary.
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db: [])
        workspace_backup.create_workspace_backup(source.parent, hostile, PASSPHRASE, data_parent=tmp_path)
    archive_before = hostile.read_bytes()
    destination = tmp_path/'must-not-publish'
    with pytest.raises(ValueError, match='ASSISTANT_MODEL'):
        restore_copy(hostile, destination, tmp_path)
    assert not destination.exists() or not list(destination.iterdir())
    assert hostile.read_bytes() == archive_before and source.read_bytes() == before
