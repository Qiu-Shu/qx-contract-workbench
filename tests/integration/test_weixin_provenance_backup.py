"""Authenticated synthetic provenance archives preserve originals and stay paused."""
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.documents import ingest
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database, provision_matter, read_original
from cn_contract.review.synthetic import select_fixture
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.weixin_inbox import accounts, conversation, dispatch, generations
from cn_contract.weixin_inbox.provenance_integrity import validate_descriptor_generations
from tests.helpers.legacy_assistant_backup import USERNAME, PASSWORD, PASSPHRASE, write_old_cnbak
from tests.helpers.synthetic_operations import keys
from tests.helpers.synthetic_weixin_provenance import chain, snapshot
from tests.integration.test_weixin_dispatch import message, poll
from tests.integration.test_weixin_generation_backup import files
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_provenance import rewrite


def original_material(history):
    actor, database = history['actor'], history['database']
    matter = d.Matter(id=uuid4(), client_ref='SYNTHETIC', title='独立虚构来源备份原件',
        jurisdiction='CN-mainland', contract_type='sales', review_mode='pre_sign', position='buyer',
        objectives=(), member_ids={actor.user_id}, status='intake', active_fact_version=None,
        active_policy_version=None, gate_issues=())
    _, _, name, raw = select_fixture('sales')
    with database.session() as db:
        provision_matter(matter, db)
        version = ingest(BytesIO(raw), d.UploadMeta(matter_id=matter.id, original_name=name.name,
            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            baseline_view='original', supersedes_id=None), actor, db=db)
    return matter, version, raw


def test_two_real_qxbak_roundtrips_preserve_provenance_originals_and_all_pause_fences(world, tmp_path):
    history = chain(world)
    root, database = history['root'], history['database']
    matter, version, raw = original_material(history)
    before = snapshot(database)
    with database.session() as db:
        assert validate_descriptor_generations(db, allow_provenance=True) == []
        backup._file_references(db)
    source_files = files(root)
    archive = tmp_path/'独立合成消息来源.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    for number in (1, 2):
        archive_bytes = archive.read_bytes()
        report = workspace_backup.restore_workspace_backup(archive, tmp_path/('来源恢复'+str(number)), PASSPHRASE)
        target = Path(report['restored_root'])
        assert target != root and report['quarantined'] is True
        restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected', database.settings,
            initialize_schema=False)
        backup._mark_storage_flags(restored)
        try:
            with restored.session() as db:
                token, _ = login(USERNAME, PASSWORD, db)
                actor = authenticate(token, db)
                assert validate_descriptor_generations(db, allow_provenance=True) == []
                backup._file_references(db)
                assert read_original(matter.id, version.id, actor, db) == raw
                fence = json.loads(db.scalar(text('SELECT payload FROM ops_restore_fences ORDER BY rowid DESC LIMIT 1')))
                assert fence['old_sessions_revoked'] is True
                for name in ('task_inbox_enabled', 'weixin_inbox_enabled', 'weixin_dispatch_enabled',
                             'weixin_reauthorization_enabled', 'weixin_generation_enabled', 'live_egress',
                             'current_approvals_valid'):
                    assert fence[name] is False
                for name in ('assistant_runs', 'review_runs', 'task_executions'):
                    assert db.scalar(text('SELECT count(*) FROM '+name)) == 0
            assert snapshot(restored) == before
            assert conversation.read_authorization(actor, history['view'].scope.conversation_id,
                database=restored).state == 'restored_blocked'
            for generation in (history['first'], history['second']):
                assert generations.find_peer_generation(actor, history['mapping'].id, generation.request_id,
                    database=restored) == generation
            restored_world = (target, restored, actor, history['view'], history['binding'])
            # Reuse the exact saved request: replay still cannot bypass recovery quarantine.
            generation_request = d.WeixinPeerGenerationInput(request_id=history['second'].request_id,
                expected_generation=1, expected_previous_generation_sha256=history['first'].generation_sha256,
                expected_previous_scope_sha256=history['first'].scope_sha256,
                expected_checkpoint_revision=history['second'].checkpoint_revision,
                task_binding_id=history['second'].task_binding_id, expected_scope=history['second'].scope,
                reason=history['second'].reason)
            actions = (
                lambda:poll(restored_world, history['account'], [message(100)]),
                lambda:dispatch.dispatch_synthetic_descriptor(actor, history['two'][1].id, database=restored),
                lambda:accounts.refresh_synthetic_peer(actor, history['mapping'].id, history['grant_request'],
                    database=restored),
                lambda:generations.append_synthetic_generation(actor, history['mapping'].id, generation_request,
                    database=restored),
            )
            for action in actions:
                with pytest.raises(ServiceError) as failure:
                    action()
                assert failure.value.code == 'BLOCKED_LIVE'
                assert snapshot(restored) == before
            assert archive.read_bytes() == archive_bytes
            if number == 1:
                archive = tmp_path/'独立合成消息来源二代.qxbak'
                workspace_backup.create_workspace_backup(target, archive, PASSPHRASE, data_parent=tmp_path)
        finally:
            restored.engine.dispose()
    assert files(root) == source_files


def test_authenticated_ordinary_cnbak_cannot_publish_nonzero_provenance(world, tmp_path, monkeypatch):
    history = chain(world)
    database = history['database']
    with database.session() as db, pytest.raises(ServiceError) as refusal:
        validate_descriptor_generations(db)
    assert refusal.value.code == 'DATA_POLICY_UNAPPROVED'
    candidate = tmp_path/'ordinary-provenance.db'
    with closing(sqlite3.connect(database.engine.url.database)) as source, closing(sqlite3.connect(candidate)) as copy:
        source.backup(copy)
        copy.execute('DROP TABLE local_workspace_identity')
        copy.commit()
    ordinary = Database('sqlite:///'+str(candidate), tmp_path/'ordinary-protected', database.settings,
        initialize_schema=False)
    backup._mark_storage_flags(ordinary)
    archive = tmp_path/'认证非原生来源.cnbak'
    try:
        with ordinary.session() as db, pytest.raises(ValueError, match='WEIXIN_PROVENANCE_INTEGRITY'):
            validate_descriptor_generations(db, allow_provenance=True)
        # Only hostile fixture construction bypasses export checks; restoration does not.
        with monkeypatch.context() as patch:
            patch.setattr(backup, '_collect_files', lambda db:({}, []))
            write_old_cnbak(ordinary, archive)
    finally:
        ordinary.engine.dispose()
    archive_bytes = archive.read_bytes()
    destination = tmp_path/'不得发布普通来源'
    with pytest.raises((ValueError, ServiceError)):
        backup.restore_backup(archive, key_resolver=keys(), restore_parent=destination, settings=database.settings)
    assert not destination.exists() or not list(destination.iterdir())
    assert archive.read_bytes() == archive_bytes


@pytest.mark.parametrize('replacement', ['past', 'future'])
def test_authenticated_rehashed_wrong_target_archive_never_publishes(world, tmp_path, monkeypatch, replacement):
    history = chain(world)
    database, root = history['database'], history['root']
    if replacement == 'past':
        descriptor, generation = history['two'][1], history['first']
    else:
        descriptor, generation = history['one'][1], history['second']
    with database.session() as db:
        rewrite(db, descriptor.id, generation_id=str(generation.id), generation_sha256=generation.generation_sha256,
            task_binding_id=str(generation.task_binding_id), scope_sha256=generation.scope_sha256)
    with database.session() as db, pytest.raises(ValueError, match='WEIXIN_PROVENANCE_INTEGRITY'):
        validate_descriptor_generations(db, allow_provenance=True)
    refused = tmp_path/'不得创建错误来源.qxbak'
    with pytest.raises(ValueError, match='WEIXIN_INBOX_INTEGRITY'):
        workspace_backup.create_workspace_backup(root, refused, PASSPHRASE, data_parent=tmp_path)
    assert not refused.exists()
    hostile = tmp_path/'认证重算摘要错误来源.qxbak'
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup, '_file_references', lambda db:[])
        workspace_backup.create_workspace_backup(root, hostile, PASSPHRASE, data_parent=tmp_path)
    archive_bytes, source_files = hostile.read_bytes(), files(root)
    destination = tmp_path/'不得发布错误来源'
    with pytest.raises(ValueError, match='WEIXIN_INBOX_INTEGRITY'):
        workspace_backup.restore_workspace_backup(hostile, destination, PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())
    assert hostile.read_bytes() == archive_bytes
    assert files(root) == source_files
