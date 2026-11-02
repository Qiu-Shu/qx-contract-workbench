"""Explicit v6 persistence on fixed fiction and local loopback, not content scoring."""
import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import material_attempts, material_preparation, trademark_triage
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login
from tests.helpers.case_evidence import add_document, response
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.helpers.trademark_support import SLOTS, span
from tests.helpers.trademark_triage import KINDS
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import KEY, config, server
from tests.integration.test_assistant_material_generation import grant
from tests.integration.test_assistant_material_routes import boot
from tests.integration.test_trademark_triage_pipeline import execute, selection_for


@pytest.fixture
def support_world(world):
    database, actor, conversation, _, _ = world
    database._assistant_synthetic_hashes = frozenset()
    w = database, actor, conversation.scope.conversation_id, None
    add_document(w, [
        '虚构记录：纸上印有澄原公司字样，书写者不详，所涉标识未注明。',
        '虚构职员于2025年3月转述澄原公司在2022年使用青禾牌；记录形成时间不明。',
    ])
    return w


def select_v6(*args):
    return trademark_triage.select_method(*args, method_id='trademark-triage-v6')


@pytest.fixture
def explicit_v6(monkeypatch):
    monkeypatch.setattr(material_preparation, 'trademark_triage_for', select_v6)


def payload(w, selection):
    manifest = material_preparation.preview(w[1], selection, w[0], config()).manifest
    # Follow-up manifests also contain messages; only attachments are evidence.
    sources = [s for s in manifest.sources if s.reference.kind == 'document']
    quotes = [dict(id=f'q{i}', source_id=s.source_id, start=0,
        end=len(s.reference.anchor.quote), exact_quote=s.reference.anchor.quote)
        for i, s in enumerate(sources, 1)]
    statements = [dict(id=f's{i}', quote_ids=[q['id']], **dict.fromkeys(SLOTS))
        for i, q in enumerate(quotes, 1)]
    factors = [dict(kind=k, holder=[], respondent=[], neutral=[],
        unresolved=['来源身份与完整原件尚待核验。']) for k in KINDS]
    value = dict(format_version='trademark-triage-v3', quotes=quotes,
        source_statements=statements, factors=factors, gaps=['补齐原件及陈述者身份。'])
    statements[1].update(speaker=span(value, 'q2', '虚构职员'),
        actor=span(value, 'q2', '澄原公司'), object=span(value, 'q2', '青禾牌'),
        event_time=span(value, 'q2', '2022年'), report_time=span(value, 'q2', '2025年3月'))
    factors[0]['neutral'] = [dict(
        text='第一份记录作者未知；第二份为职员转述，不能据此认定事实。',
        statement_ids=['s1', 's2'], relation='recorded', dependencies=[
            dict(statement_id='s2', slot='speaker'),
            dict(statement_id='s2', slot='event_time'),
            dict(statement_id='s2', slot='report_time')])]
    factors[0]['holder'] = [dict(text='仅在查明陈述者身份后，才可进一步评估该记录的来源。',
        statement_ids=['s1'], relation='conditional_inference',
        dependencies=[dict(statement_id='s1', slot='speaker')])]
    for statement in statements[2:]:
        factors[0]['neutral'].append(dict(text='补充记录保留为待核材料，不据此认定使用行为成立。',
            statement_ids=[statement['id']], relation='recorded', dependencies=[]))
    return value


def saved_bytes(w, attempt_id):
    with w[0].session() as db:
        return (
            db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'),
                {'id': str(attempt_id)}),
            db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
                {'id': str(attempt_id)}),
        )


def test_explicit_v6_two_rounds_preserve_sources_history_word_and_archive(
        support_world, explicit_v6, tmp_path):
    w = support_world
    chosen = selection_for(w)
    first, basis = execute(w, chosen, payload(w, chosen))
    assert first.output is not None and first.output.review_status == 'unverified'
    assert basis.manifest.trademark_triage.method_id == 'trademark-triage-v6'
    assert first.output.candidate.trademark_triage.format_version == 'trademark-triage-v3'
    assert trademark_triage.CURRENT_METHOD_ID == 'trademark-triage-v5'
    assert trademark_triage.select_method('case', basis.manifest.question).method_id == 'trademark-triage-v5'
    original = saved_bytes(w, first.id)
    add_document(w, ['虚构补件：原记录经档案保管人移交，未说明书写者；仅见一页。'])
    next_selection = selection_for(w, basis.manifest.stable_task_id)
    second, updated = execute(w, next_selection, payload(w, next_selection))
    assert second.output is not None and second.output.review_status == 'unverified'
    assert updated.manifest.stable_task_id == basis.manifest.stable_task_id
    assert len(updated.manifest.materials) == len(basis.manifest.materials) + 1
    assert updated.manifest.materials[:-1] == basis.manifest.materials
    assert [(m.role, m.content) for m in updated.manifest.conversation_history] == [
        ('user', basis.manifest.question), ('assistant', first.output.candidate.text)]
    assert updated.manifest.conversation_history[0].message_id == basis.manifest.sources[0].reference.message_id
    assert updated.manifest.conversation_history[1].message_id == first.output.id
    assert updated.manifest.history_format is None
    candidate = second.output.candidate.trademark_triage
    assert tuple(f.kind for f in candidate.factors) == KINDS
    assert len(candidate.quotes) == len(candidate.source_statements) == 3
    assert candidate.quotes[-1].source_id not in {s.source_id for s in basis.manifest.sources}
    assert '档案保管人' in candidate.quotes[-1].exact_quote
    assert candidate.factors[0].neutral[-1].statement_ids == ('s3',)
    sources = {s.source_id: s.reference for s in updated.manifest.sources}
    assert all(sources[q.source_id].kind == 'document' for q in candidate.quotes)
    assert '条件推断' in second.output.candidate.text
    assert '未知前提（未核实，不能据此确认结论）：s1 陈述者' in second.output.candidate.text
    assert '成文时间：未知' in second.output.candidate.text
    assert saved_bytes(w, first.id) == original
    with w[0].session() as db:
        for table in ('assistant_model_attempts', 'assistant_model_outputs', 'assistant_model_receipts'):
            assert db.scalar(text(f'SELECT COUNT(*) FROM {table}')) == 2
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_evidence_revisions')) == 0
        validate_model_records(db)
    with boot(w, tmp_path) as http:
        exported = http.client.get(http.url + '/material-generations/' + str(second.id) + '/document')
        assert exported.status_code == 200, exported.text
        body = '\n'.join(p.text for p in Document(BytesIO(exported.content)).paragraphs)
        assert second.output.candidate.text in body and '待律师核对' in body
        assert '来源陈述（模型提取，未认定事实）' in body
    root = Path(w[0].engine.url.database).parent
    archive = tmp_path / 'trademark-support-synthetic.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    info = workspace_backup.restore_workspace_backup(archive, tmp_path / 'support-restored', PASSPHRASE)
    restored_root = Path(info['restored_root'])
    restored = Database('sqlite:///' + str(restored_root / 'workbench.db'), restored_root / 'protected',
        w[0].settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            assert attempts.read_attempt(actor, first.id, db) == first
            assert attempts.read_attempt(actor, second.id, db) == second
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 2
            validate_model_records(db)
    finally:
        restored.engine.dispose()


def test_explicit_v6_queue_executes_after_selector_returns_to_v5(support_world, monkeypatch):
    w = support_world
    chosen = selection_for(w)
    with monkeypatch.context() as opted_in:
        opted_in.setattr(material_preparation, 'trademark_triage_for', select_v6)
        basis = material_preparation.preview(w[1], chosen, w[0], config())
        body = response(payload(w, chosen))
    with server(body) as (url, received, _):
        async def scenario():
            with monkeypatch.context() as opted_in:
                opted_in.setattr(material_preparation, 'trademark_triage_for', select_v6)
                _, lease, approved = grant(w, chosen,
                    DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
                assert approved == basis
                with w[0].session() as db:
                    queued = material_attempts.enqueue(w[1], chosen, approved, db, lease)
            original = saved_bytes(w, queued.id)[0]
            assert material_preparation.trademark_triage_for('case', basis.manifest.question).method_id == 'trademark-triage-v5'
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.output is not None
            assert result.output.manifest == basis.manifest
            assert result.output.candidate.trademark_triage.format_version == 'trademark-triage-v3'
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            assert saved_bytes(w, queued.id)[0] == original
            with w[0].session() as db:
                assert attempts.read_attempt(w[1], queued.id, db) == result
                validate_model_records(db)
            return result
        result = asyncio.run(scenario())
        assert len(received) == 1
        wire = json.loads(received[0]['body'])
        assert wire['messages'][0]['content'] == trademark_triage.method_system(basis.manifest.trademark_triage)
        assert json.loads(wire['messages'][1]['content']) == basis.manifest.model_dump(mode='json')
    following = selection_for(w, basis.manifest.stable_task_id)
    current = material_preparation.preview(w[1], following, w[0], config())
    assert current.manifest.trademark_triage.method_id == 'trademark-triage-v5'
    assert current.manifest.stable_task_id == basis.manifest.stable_task_id
    assert [(m.role, m.content) for m in current.manifest.conversation_history] == [
        ('user', basis.manifest.question), ('assistant', result.output.candidate.text)]


@pytest.mark.parametrize('damage', ['recorded_unknown', 'comparison_unknown', 'span_outside'])
def test_invalid_v6_support_keeps_one_receipt_without_output_or_resend(support_world, explicit_v6, damage):
    w = support_world
    chosen = selection_for(w)
    value = payload(w, chosen)
    if damage == 'recorded_unknown':
        value['factors'][0]['neutral'][0]['dependencies'] = [dict(statement_id='s1', slot='speaker')]
    elif damage == 'comparison_unknown':
        value['factors'][0]['neutral'][0].update(relation='comparison', dependencies=[
            dict(statement_id=s, slot=k) for s in ('s1', 's2') for k in ('actor', 'object')])
    else:
        value['source_statements'][1]['speaker']['end'] = 999
    result, _ = execute(w, chosen, value)
    assert result.state == 'received' and result.output is None
    assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.receipt.usage.total_tokens == 42 and result.receipt.cost_status == 'estimated'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1


@pytest.mark.parametrize('damage', ['span', 'dependency'])
def test_saved_v6_support_tampering_blocks_read_export_and_followup(
        support_world, explicit_v6, tmp_path, damage):
    w = support_world
    chosen = selection_for(w)
    result, basis = execute(w, chosen, payload(w, chosen))
    assert result.output is not None
    with w[0].session() as db:
        value = json.loads(db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(result.id)}))
        draft = value['candidate']['trademark_triage']
        if damage == 'span':
            draft['source_statements'][1]['speaker']['end'] += 1
        else:
            draft['factors'][0]['neutral'][0]['dependencies'][0]['slot'] = 'record_time'
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
        exported = http.client.get(http.url + '/material-generations/' + str(result.id) + '/document')
        assert exported.status_code == 409, exported.text
    following = selection_for(w, basis.manifest.stable_task_id)
    with pytest.raises(ValueError):
        material_preparation.preview(w[1], following, w[0], config())
