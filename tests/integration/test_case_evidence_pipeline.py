"""Synthetic chronology requests use the same material task, ledger and archive."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import case_evidence, evidence_worksheet, material_attempts, material_codec, material_preparation, service
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.review.model_adapter import MAX_RAW_BYTES
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login
from tests.helpers.case_evidence import add_document, draft_for, response
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_material_generation import material_world, grant
from tests.integration.test_assistant_material_routes import boot
from tests.integration.test_material_followup_history import followup
from tests.integration.test_assistant_main_provider import config, KEY, server


def chronology(w, task_id=None):
    return followup(w, task_id, '请按材料整理时间线，保留不同说法。', new_task=task_id is None)


def execute(w, selection, value=None):
    database, actor, _, _ = w
    basis = material_preparation.preview(actor, selection, database, config())
    with server(response(draft_for(basis.manifest) if value is None else value)) as (url, received, _):
        async def scenario():
            _, lease, approved = grant(w, selection,
                DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
            assert approved == basis
            with database.session() as db:
                queued = material_attempts.enqueue(actor, selection, approved, db, lease)
            result = await execute_attempt(actor, queued.id, database, lease)
            assert await execute_attempt(actor, queued.id, database, lease) == result
            with database.session() as db:
                assert attempts.read_attempt(actor, queued.id, db) == result
                validate_model_records(db)
            return result
        result = asyncio.run(scenario())
        assert len(received) == 1
        wire = json.loads(received[0]['body'])
        assert json.loads(wire['messages'][1]['content']) == basis.manifest.model_dump(mode='json')
    return result, basis


def test_explicit_chronology_selects_versioned_method_in_existing_case(material_world):
    w = material_world
    selection = chronology(w)
    basis = material_preparation.preview(w[1], selection, w[0], config())
    assert basis.manifest.case_method.method_id == 'case-evidence-v5'
    assert basis.manifest.workflow == 'case'
    assert basis.parent_business_run_id == selection.parent_business_run_id


def test_chronology_roundtrip_export_followup_and_archive_preserve_unreviewed_sources(material_world, tmp_path):
    w = material_world
    selection = chronology(w)
    initial = material_preparation.preview(w[1], selection, w[0], config())
    with w[0].session() as db:
        worksheet = evidence_worksheet.read(w[1], w[2], db)
    manual = d.EvidenceFact(id=uuid4(), category='agreement', content='律师既有登记：材料记载借款，尚不认定交付。',
        review_state='reviewed', source=next(source.reference for source in initial.manifest.sources
            if source.reference.kind == 'document'))
    evidence_worksheet.commit(w[1], w[2], d.EvidenceCommitInput(request_id=uuid4(),
        expected_scope=worksheet.scope, expected_profile_revision=worksheet.profile_revision,
        base_revision=worksheet.revision, rows=(manual,)), database=w[0])
    first, basis = execute(w, selection)
    assert first.state == 'received' and first.output is not None
    candidate = first.output.candidate
    assert first.output.review_status == 'unverified'
    assert candidate.case_evidence.model_dump(mode='json') == draft_for(basis.manifest)
    assert '2026年1月3日' in candidate.text and '30000元' in candidate.text
    assert '法律分析（依据及适用待核）' in candidate.text
    assert candidate.citations == (candidate.case_evidence.quotes[0].source_id,)
    second, second_basis = execute(w, chronology(w, basis.manifest.stable_task_id))
    assert second_basis.manifest.stable_task_id == basis.manifest.stable_task_id
    assert second_basis.parent_business_run_id != basis.parent_business_run_id
    assert [item.content for item in second_basis.manifest.conversation_history] == [
        basis.manifest.question, candidate.text]
    assert second.output.manifest.materials == first.output.manifest.materials
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 2
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_evidence_revisions')) == 1
        assert evidence_worksheet.read(w[1], w[2], db).rows == (manual,)
        saved = tuple(db.execute(text('SELECT * FROM assistant_model_outputs ORDER BY id')).all())
    with boot(w, tmp_path) as http:
        document = http.client.get(http.url + '/material-generations/' + str(second.id) + '/document')
        assert document.status_code == 200, document.text
        body = '\n'.join(p.text for p in Document(BytesIO(document.content)).paragraphs)
        assert second.output.candidate.text in body
        assert '独立虚构借款.docx' in body and '待律师核对' in body
        assert candidate.case_evidence.quotes[0].exact_quote in body
    with w[0].session() as db:
        assert tuple(db.execute(text('SELECT * FROM assistant_model_outputs ORDER BY id')).all()) == saved
    root = Path(w[0].engine.url.database).parent
    archive = tmp_path / 'case-evidence.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    info = workspace_backup.restore_workspace_backup(archive, tmp_path / 'case-restored', PASSPHRASE)
    target = Path(info['restored_root'])
    restored = Database('sqlite:///' + str(target / 'workbench.db'), target / 'protected',
        w[0].settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            assert attempts.read_attempt(actor, first.id, db) == first
            assert attempts.read_attempt(actor, second.id, db) == second
            assert evidence_worksheet.read(actor, w[2], db).rows == (manual,)
            validate_model_records(db)
        restored_w = (restored, actor, w[2], token)
        with boot(restored_w, tmp_path) as http:
            document = http.client.get(http.url + '/material-generations/' + str(second.id) + '/document')
            assert document.status_code == 200, document.text
            assert second.output.candidate.text in '\n'.join(
                p.text for p in Document(BytesIO(document.content)).paragraphs)
            blocked = http.client.post(http.url + '/material-generations', headers=http.headers,
                json=second_basis.model_dump(mode='json', include=set(d.MainMaterialSelection.model_fields)))
            assert blocked.status_code == 409, blocked.text
    finally:
        restored.engine.dispose()


@pytest.mark.parametrize('damage', ['derived_text', 'exact_quote', 'method_sha256'])
@pytest.mark.parametrize('method_id', ['case-evidence-v4', 'case-evidence-v5'])
def test_persisted_chronology_tampering_rejects_archive_export_and_followup(
        material_world, tmp_path, monkeypatch, damage, method_id):
    w = material_world
    with monkeypatch.context() as revision:
        revision.setattr(material_preparation, 'select_method',
            lambda *args: case_evidence.select_method(*args, method_id=method_id))
        result, basis = execute(w, chronology(w))
    assert basis.manifest.case_method.method_id == method_id
    with w[0].session() as db:
        value = json.loads(db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(result.id)}))
        if damage == 'derived_text':
            value['candidate']['text'] += '\n擅改已保存成果。'
        elif damage == 'exact_quote':
            value['candidate']['case_evidence']['quotes'][0]['exact_quote'] = '2026年1月3日甲向乙借款90000元'
        else:
            value['manifest']['case_method']['method_sha256'] = 'f' * 64
        # Keep canonical JSON and DTO shape valid: the source check must catch the tamper.
        changed = encoded(d.MainMaterialOutputView.model_validate(value))
        triggers = db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_model_outputs'")).all()
        for name, _ in triggers:
            db.execute(text('DROP TRIGGER "' + name.replace('"', '""') + '"'))
        db.execute(text('UPDATE assistant_model_outputs SET output_json=:value WHERE attempt_id=:id'),
            {'value': changed, 'id': str(result.id)})
        for _, sql in triggers:
            db.execute(text(sql))
    with w[0].session() as db:
        with pytest.raises(ValueError):
            attempts.read_attempt(w[1], result.id, db)
        with pytest.raises(ValueError):
            validate_model_records(db)
    with boot(w, tmp_path) as http:
        rejected = http.client.get(http.url + '/material-generations/' + str(result.id) + '/document')
        assert rejected.status_code == 409, rejected.text
    selection = chronology(w, basis.manifest.stable_task_id)
    with pytest.raises(ValueError):
        material_preparation.preview(w[1], selection, w[0], config())


@pytest.mark.parametrize('boundary', ['decode', 'settle'])
def test_new_protocol_rejects_legacy_text_but_preserves_usage_without_resend(material_world, monkeypatch, boundary):
    w = material_world
    selection = chronology(w)
    basis = material_preparation.preview(w[1], selection, w[0], config())
    legacy = {'text': '旧格式候选不得替代新版引用校验。', 'citations': [basis.manifest.sources[0].source_id]}
    if boundary == 'settle':
        decode = material_codec.decode
        def downgrade(*args, **kwargs):
            reply = decode(*args, **kwargs)
            assert reply.output is not None
            return reply.model_copy(update={'output': d.MainMaterialCandidate.model_validate(legacy)})
        monkeypatch.setattr(material_codec, 'decode', downgrade)
    result, _ = execute(w, selection, legacy if boundary == 'decode' else None)
    assert result.state == 'received' and result.output is None
    assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.receipt.usage.total_tokens == 42
    assert result.receipt.cost_status == 'estimated'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0


def test_preupgrade_queued_chronology_keeps_legacy_bytes_then_new_preview_uses_new_method(material_world, monkeypatch):
    w = material_world
    selection = chronology(w)
    with monkeypatch.context() as legacy:
        legacy.setattr(material_preparation, 'select_method', lambda *args: None)
        basis = material_preparation.preview(w[1], selection, w[0], config())
        value = {'text': '升级前已排队的案件时间线候选。', 'citations': [basis.manifest.sources[0].source_id]}
        body = response(value)
    with server(body) as (url, received, _):
        async def scenario():
            with monkeypatch.context() as legacy:
                legacy.setattr(material_preparation, 'select_method', lambda *args: None)
                _, lease, approved = grant(w, selection,
                    DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
                with w[0].session() as db:
                    queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
                    before = db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(queued.id)})
            assert approved == basis and basis.manifest.case_method is None
            assert 'case_method' not in basis.manifest.model_dump(mode='json')
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.output is not None and result.output.candidate.text == value['text']
            assert result.output.candidate.case_evidence is None
            assert 'case_evidence' not in result.output.candidate.model_dump(mode='json')
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(queued.id)}) == before
                validate_model_records(db)
        asyncio.run(scenario())
        assert len(received) == 1
    updated = material_preparation.preview(w[1], chronology(w, basis.manifest.stable_task_id), w[0], config())
    assert updated.manifest.case_method.method_id == 'case-evidence-v5'
    assert updated.manifest.conversation_history[1].content == value['text']


@pytest.mark.parametrize('failure', ['revoked_before_send', 'sent_unknown'])
def test_chronology_permission_and_unknown_transport_never_resend(material_world, failure):
    w = material_world
    selection = chronology(w)
    model_config = config(timeout_seconds=1)
    basis = material_preparation.preview(w[1], selection, w[0], model_config)
    with server(response(draft_for(basis.manifest)), pause=2) as (url, received, _):
        async def scenario():
            registry, lease, approved = grant(w, selection,
                DeepSeekProvider.for_synthetic_loopback(model_config, lambda: KEY, url))
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
            if failure == 'revoked_before_send':
                registry.revoke(w[1].session_id)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.state == ('failed_before_send' if failure == 'revoked_before_send' else 'sent_unknown')
            assert result.output is None and result.receipt.usage is None
            assert result.receipt.cost_status == ('not_sent' if failure == 'revoked_before_send' else 'unknown')
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
                assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
                validate_model_records(db)
        asyncio.run(scenario())
        assert len(received) == (0 if failure == 'revoked_before_send' else 1)


def test_oversize_saved_chronology_is_discarded_with_usage_and_replayable_ledger(material_world):
    w = material_world
    # A genuine large DOCX stays within the input budget, but its manifest plus
    # duplicated structured/display output must not exceed the persisted limit.
    add_document(w, [f'独立虚构证据第{number}段：' + '材料待核。' * 940 for number in range(8)])
    selection = chronology(w)
    basis = material_preparation.preview(w[1], selection, w[0], config())
    prepared = material_codec.prepare(d.MainMaterialRequest(run_id=uuid4(), message_id=uuid4(),
        scope=basis.expected_scope.model_copy(update={'input_revision': basis.expected_scope.input_revision + 1}),
        basis=basis), config())
    assert basis.wire_bytes <= config().max_input_bytes
    assert len(encoded(prepared).encode('utf-8')) <= MAX_RAW_BYTES
    draft = draft_for(basis.manifest)
    draft['statements'] += [{'kind': 'proposed_text', 'text': '🧪' * 1900,
        'support': [], 'opposing': [], 'unresolved': []} for _ in range(9)]
    from cn_contract.assistant.case_evidence import candidate
    rendered = candidate(draft, basis.manifest)
    assert len(encoded(basis.manifest).encode('utf-8')) + len(encoded(rendered).encode('utf-8')) > MAX_RAW_BYTES
    result, _ = execute(w, selection, draft)
    assert result.state == 'received' and result.output is None
    assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.receipt.usage.total_tokens == 42
    assert result.receipt.cost_status == 'estimated'


def oversize_case_basis(w):
    # Independently measure the full DTO; public preview is expected to reject it.
    add_document(w, [f'独立虚构证据第{number}段：' + '材料待核。' * 970 for number in range(8)])
    selection = chronology(w)
    with w[0].session() as db:
        manifest, _ = material_preparation.assemble(w[1], selection, db)
    basis = material_codec.build_basis(selection, manifest, config())
    value = d.MainMaterialRequest(run_id=uuid4(), message_id=uuid4(),
        scope=basis.expected_scope.model_copy(update={'input_revision': basis.expected_scope.input_revision + 1}),
        basis=basis)
    oversized = d.MainMaterialPreparedInput(request=value,
        wire_payload_json=material_codec.json_bytes(material_codec.build_request(value, config())).decode('utf-8'))
    assert len(oversized.wire_payload_json.encode('utf-8')) == basis.wire_bytes <= config().max_input_bytes
    assert len(encoded(oversized).encode('utf-8')) > MAX_RAW_BYTES
    print(json.dumps({'wire_bytes': basis.wire_bytes, 'wire_limit': config().max_input_bytes,
        'persisted_input_bytes': len(encoded(oversized).encode('utf-8')), 'persisted_limit': MAX_RAW_BYTES}))
    return selection, basis


def test_oversize_persisted_input_preview_rejects_before_message_or_transport(material_world, monkeypatch):
    w = material_world
    selection, _ = oversize_case_basis(w)
    tables = ('assistant_messages', 'assistant_runs', 'assistant_run_events',
        'assistant_model_attempts', 'assistant_model_receipts', 'assistant_model_outputs')
    with w[0].session() as db:
        before = [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables]
        conversation = service.read_conversation(w[1], w[2], db)
    observed = []
    save_message = service.save_message

    def observe_message(*args, **kwargs):
        observed.append(save_message(*args, **kwargs))
        return observed[-1]

    monkeypatch.setattr(service, 'save_message', observe_message)
    with server() as (url, received, _):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
                material_preparation.preview(w[1], selection, w[0], config())
            # The existing approval helper must also stop at its real preview.
            with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
                grant(w, selection, provider)
            assert not observed
            with w[0].session() as db:
                assert [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables] == before
                assert service.read_conversation(w[1], w[2], db) == conversation
                validate_model_records(db)
        asyncio.run(scenario())
        assert not received
    with w[0].session() as db:
        assert [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables] == before
        assert service.read_conversation(w[1], w[2], db) == conversation
        validate_model_records(db)


def test_oversize_persisted_input_rejects_before_ledger_or_transport_and_rolls_back_message(material_world, monkeypatch):
    """Internal enqueue boundary using an old-style basis, not the normal preview flow."""
    w = material_world
    selection, basis = oversize_case_basis(w)
    tables = ('assistant_messages', 'assistant_runs', 'assistant_run_events',
        'assistant_model_attempts', 'assistant_model_receipts', 'assistant_model_outputs')
    with w[0].session() as db:
        before = [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables]
        conversation = service.read_conversation(w[1], w[2], db)
    observed = []
    save_message = service.save_message

    def observe_message(actor, cid, request, db):
        run = save_message(actor, cid, request, db)
        counts = [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables]
        assert counts[:3] == [amount + 1 for amount in before[:3]]
        assert counts[3:] == before[3:]
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages WHERE id=:id'), {'id': str(run.message_id)}) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs WHERE id=:id'), {'id': str(run.id)}) == 1
        current = service.read_conversation(actor, cid, db)
        assert run.scope == current.scope == conversation.scope.model_copy(update={
            'input_revision': conversation.scope.input_revision + 1})
        observed.append(run)
        return run

    monkeypatch.setattr(service, 'save_message', observe_message)
    with server() as (url, received, _):
        async def scenario():
            # Exercise a trusted internal caller that predates preview validation.
            # Real registry, authorization, rebuild and prepare checks stay enabled.
            registry = MainModelRegistry()
            registry.configure(DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
            policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=selection.expected_scope.workspace_id,
                actor_id=w[1].user_id, config_sha256=sha(encoded(config())),
                allowed_content_sha256s=(basis.manifest_sha256,), max_total_usd='1', max_calls=1,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
            registry.grant(policy, w[1].session_id, basis=basis)
            lease = registry.resolve(w[1], selection.expected_scope)
            with w[0].session() as db:
                # Catch inside the caller transaction: rollback must be the adapter's savepoint.
                with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
                    material_attempts.enqueue(w[1], selection, basis, db, lease)
                assert len(observed) == 1
                assert [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables] == before
                assert service.read_conversation(w[1], w[2], db) == conversation
                validate_model_records(db)
        asyncio.run(scenario())
        assert not received
    with w[0].session() as db:
        assert [db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in tables] == before
        assert service.read_conversation(w[1], w[2], db) == conversation
        validate_model_records(db)
