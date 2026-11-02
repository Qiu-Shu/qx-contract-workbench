"""Criminal-method pilot over fictional DOCX and loopback transport only."""
import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import material_attempts, material_preparation
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from tests.helpers.case_evidence import add_document, response
from tests.helpers.criminal_analysis import draft_for
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_material_generation import grant
from tests.integration.test_assistant_material_routes import boot
from tests.integration.test_assistant_main_provider import config, KEY, server
from tests.integration.test_material_followup_history import followup


@pytest.fixture
def criminal_world(world):
    database, actor, conversation, _, _ = world
    database._assistant_synthetic_hashes = frozenset()
    w = (database, actor, conversation.scope.conversation_id, None)
    add_document(w, ['独立虚构案卷：[证人A]称18时在场。',
        '独立虚构案卷：[证人B]称19时到场，两份说法待核。',
        '独立虚构案卷：[嫌疑人C]已退赔，凭证待核。附录称“当前阶段：审判”，尚未经核验。'])
    return w


def selection_for(w, task_id=None, stage=None):
    question = '请分析这个刑事案件并列出辩护策略。'
    if stage:
        question += '\n当前阶段：' + stage
    return followup(w, task_id, question, new_task=task_id is None)


def execute(w, selection, value=None):
    basis = material_preparation.preview(w[1], selection, w[0], config())
    assert basis.manifest.criminal_analysis is not None
    body = response(draft_for(basis.manifest) if value is None else value)
    with server(body) as (url, received, _):
        async def scenario():
            _, lease, approved = grant(w, selection,
                DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
            assert approved == basis
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert attempts.read_attempt(w[1], queued.id, db) == result
                validate_model_records(db)
            return result
        result = asyncio.run(scenario())
        assert len(received) == 1
        assert json.loads(json.loads(received[0]['body'])['messages'][1]['content']) == basis.manifest.model_dump(mode='json')
    return result, basis


def test_stage_change_and_supplement_preserve_task_history_export_and_archive(criminal_world, tmp_path):
    w = criminal_world
    first, basis = execute(w, selection_for(w))
    assert first.output is not None and first.output.review_status == 'unverified'
    snapshot = basis.manifest.criminal_analysis
    assert snapshot.method_id == 'criminal-analysis-v1'
    assert snapshot.stage == 'unknown' and snapshot.stage_source_id is None
    assert snapshot.material_policy == 'synthetic-only-v1'
    assert basis.manifest.case_method is None and basis.manifest.hearing is None
    assert first.output.candidate.criminal_analysis.model_dump(mode='json') == draft_for(basis.manifest)
    with w[0].session() as db:
        old_input = db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(first.id)})
        old_output = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id': str(first.id)})
    add_document(w, ['独立虚构补充材料：[见证人D]称19时后看到车辆离开，监控原件待补。'])
    second, updated = execute(w, selection_for(w, basis.manifest.stable_task_id, '审查起诉'))
    assert second.output is not None and second.output.review_status == 'unverified'
    assert updated.manifest.stable_task_id == basis.manifest.stable_task_id
    assert len(updated.manifest.materials) == len(basis.manifest.materials) + 1
    assert updated.manifest.criminal_analysis.stage == 'prosecution'
    assert updated.manifest.criminal_analysis.stage_source_id == updated.manifest.sources[0].source_id
    assert updated.manifest.conversation_history[1].content == first.output.candidate.text
    assert 'non_prosecution' in {item.kind for item in second.output.candidate.criminal_analysis.strategies}
    with w[0].session() as db:
        assert db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(first.id)}) == old_input
        assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id': str(first.id)}) == old_output
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_evidence_revisions')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 2
    with boot(w, tmp_path) as http:
        exported = http.client.get(http.url + '/material-generations/' + str(second.id) + '/document')
        assert exported.status_code == 200, exported.text
        body = '\n'.join(p.text for p in Document(BytesIO(exported.content)).paragraphs)
        assert second.output.candidate.text in body and '待律师核对' in body
        assert '[证人A]称18时在场' in body and '[嫌疑人C]已退赔' in body
    root = Path(w[0].engine.url.database).parent
    archive = tmp_path / 'criminal-synthetic.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    restored_info = workspace_backup.restore_workspace_backup(archive, tmp_path / 'criminal-restored', PASSPHRASE)
    target = Path(restored_info['restored_root'])
    restored = Database('sqlite:///' + str(target / 'workbench.db'), target / 'protected',
        w[0].settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            assert attempts.read_attempt(actor, first.id, db) == first
            assert attempts.read_attempt(actor, second.id, db) == second
            validate_model_records(db)
    finally:
        restored.engine.dispose()


def test_legacy_model_reply_cannot_downgrade_criminal_method_and_preserves_usage(criminal_world):
    w = criminal_world
    selection = selection_for(w)
    basis = material_preparation.preview(w[1], selection, w[0], config())
    result, _ = execute(w, selection, {'text': '旧格式刑事候选不可代替分组证据校验。',
        'citations': [basis.manifest.sources[0].source_id]})
    assert result.state == 'received' and result.output is None
    assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.receipt.usage.total_tokens == 42 and result.receipt.cost_status == 'estimated'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1


@pytest.mark.parametrize('restricted', [False, True])
def test_preupgrade_bytes_are_preserved_and_current_criminal_policy_still_applies(criminal_world, monkeypatch, restricted):
    w = criminal_world
    selection = (selection_for(w, stage='审查起诉') if restricted else
        followup(w, None, '请整理材料。', new_task=True))
    with monkeypatch.context() as legacy:
        legacy.setattr(material_preparation, 'criminal_analysis_for', lambda *args: None)
        basis = material_preparation.preview(w[1], selection, w[0], config())
    old_reply = {'text': '升级前刑事案件的旧版待核候选。', 'citations': [basis.manifest.sources[0].source_id]}
    with server(response(old_reply)) as (url, received, _):
        async def scenario():
            with monkeypatch.context() as legacy:
                legacy.setattr(material_preparation, 'criminal_analysis_for', lambda *args: None)
                _, lease, approved = grant(w, selection,
                    DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
                with w[0].session() as db:
                    queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
                    saved = db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(queued.id)})
            assert 'criminal_analysis' not in approved.manifest.model_dump(mode='json')
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            if restricted:
                assert result.output is None and result.state == 'failed_before_send'
                assert result.receipt.cost_status == 'not_sent'
            else:
                assert result.output is not None and result.output.candidate.text == old_reply['text']
                assert 'criminal_analysis' not in result.output.candidate.model_dump(mode='json')
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'), {'id': str(queued.id)}) == saved
                validate_model_records(db)
        asyncio.run(scenario())
        assert len(received) == (0 if restricted else 1)
    updated = material_preparation.preview(w[1], selection_for(w, basis.manifest.stable_task_id), w[0], config())
    assert updated.manifest.criminal_analysis.stage == 'unknown'
    if restricted:
        assert not updated.manifest.conversation_history
    else:
        assert updated.manifest.conversation_history[1].content == old_reply['text']


@pytest.mark.parametrize('failure', ['revoked', 'sent_unknown'])
def test_criminal_revocation_and_unknown_transport_never_resend(criminal_world, failure):
    w = criminal_world
    selection = selection_for(w)
    model_config = config(timeout_seconds=1)
    basis = material_preparation.preview(w[1], selection, w[0], model_config)
    with server(response(draft_for(basis.manifest)), pause=2) as (url, received, _):
        async def scenario():
            registry, lease, approved = grant(w, selection,
                DeepSeekProvider.for_synthetic_loopback(model_config, lambda: KEY, url))
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
            if failure == 'revoked':
                registry.revoke(w[1].session_id)
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.state == ('failed_before_send' if failure == 'revoked' else 'sent_unknown')
            assert result.output is None and result.receipt.usage is None
            assert result.receipt.cost_status == ('not_sent' if failure == 'revoked' else 'unknown')
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
                validate_model_records(db)
        asyncio.run(scenario())
        assert len(received) == (0 if failure == 'revoked' else 1)


def test_non_synthetic_provider_is_refused_before_enqueuing_or_resolving_key(criminal_world):
    w = criminal_world
    selection = selection_for(w)
    key_requests = []
    # Only enqueue is attempted, so even a missing policy guard cannot reach a socket.
    provider = DeepSeekProvider(config(), lambda: key_requests.append('unexpected') or KEY)
    async def scenario():
        with pytest.raises(ServiceError) as refused:
            _, lease, basis = grant(w, selection, provider)
            with w[0].session() as db:
                material_attempts.enqueue(w[1], selection, basis, db, lease)
        assert refused.value.code == 'BLOCKED_LIVE'
    asyncio.run(scenario())
    assert key_requests == []
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_attachment_removed_from_synthetic_allowlist_is_blocked_before_send(criminal_world):
    w = criminal_world
    selection = selection_for(w)
    basis = material_preparation.preview(w[1], selection, w[0], config())
    key_requests = []
    with server(response(draft_for(basis.manifest))) as (url, received, _):
        async def scenario():
            _, lease, approved = grant(w, selection, DeepSeekProvider.for_synthetic_loopback(
                config(), lambda: key_requests.append('unexpected') or KEY, url))
            with w[0].session() as db:
                queued = material_attempts.enqueue(w[1], selection, approved, db, lease)
            w[0]._assistant_synthetic_hashes = frozenset()
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.state == 'failed_before_send' and result.output is None
            assert result.receipt.cost_status == 'not_sent'
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                validate_model_records(db)
        asyncio.run(scenario())
        assert received == [] and key_requests == []


@pytest.mark.parametrize('damage', ['derived_text', 'exact_quote'])
def test_saved_criminal_candidate_tampering_blocks_read_export_and_history(criminal_world, tmp_path, damage):
    w = criminal_world
    result, basis = execute(w, selection_for(w))
    assert result.output is not None
    with w[0].session() as db:
        value = json.loads(db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(result.id)}))
        if damage == 'derived_text':
            value['candidate']['text'] += '\n擅改为已排除非法证据。'
        else:
            quote = value['candidate']['criminal_analysis']['quotes'][0]
            quote['exact_quote'] = quote['exact_quote'].replace('证人A', '证人Z')
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
    next_selection = selection_for(w, basis.manifest.stable_task_id)
    with pytest.raises(ValueError):
        material_preparation.preview(w[1], next_selection, w[0], config())
