"""Long synthetic contract replies must not silently disappear on continuation."""
import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import material_attempts, material_codec, material_history, material_integrity, material_preparation, service
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt
from cn_contract.security import ServiceError
from tests.helpers.case_evidence import add_document
from tests.helpers.contract_review import draft_for, response
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config, KEY, server
from tests.integration.test_assistant_material_generation import material_world, grant, selection_for
from tests.integration.test_assistant_material_routes import boot
from tests.integration.test_contract_c4_material_flow import MaterialProvider
from tests.integration.test_contract_review_pipeline import execute, selection
from tests.integration.test_material_followup_history import followup


def _saved_long_contract(w, record_property, *, over_limit=False):
    chosen = (followup(w, None, '我们是供应方，请审查独立虚构合同。' + '虚构补充背景待核。' * 400,
        new_task=True, workflow='contract') if over_limit else selection(w))
    basis = material_preparation.preview(w[1], chosen, w[0], config())
    value = draft_for(basis.manifest)
    repetitions = 100 if over_limit else 70
    value['gaps'] = [f'容量测试事项{number + 1}：' + '独立虚构附件待核。' * repetitions for number in range(20)]
    first, basis = execute(w, chosen, value)
    assert first.state == 'received' and first.receipt.error_code is None
    assert first.output is not None and first.output.review_status == 'unverified'
    assert first.output.candidate.contract_review is not None
    source = basis.manifest.sources[0].reference
    pair = [
        dict(message_id=str(source.message_id), role='user', source_revision=source.source_revision,
            content=basis.manifest.question),
        dict(message_id=str(first.output.id), role='assistant', source_revision=source.source_revision,
            content=first.output.candidate.text),
    ]
    pair_bytes = len(json.dumps(pair, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    record_property('history_pair_utf8_bytes', pair_bytes)
    record_property('reply_characters', len(first.output.candidate.text))
    if over_limit:
        assert pair_bytes > 65536
        assert 18000 < len(first.output.candidate.text) <= 20000
    else:
        assert 32768 < pair_bytes <= 65536
    return w, first, basis


@pytest.fixture
def long_contract(material_world, record_property):
    return _saved_long_contract(material_world, record_property)


@pytest.fixture
def oversized_contract(material_world, record_property):
    return _saved_long_contract(material_world, record_property, over_limit=True)


def test_versioned_contract_history_carries_long_reply_and_new_attachment_through_second_send(long_contract, record_property):
    w, first, basis = long_contract
    with w[0].session() as db:
        original = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(first.id)})
    add_document(w, ['独立虚构补充协议：验收期限变更为交付后的十五日，其余事项仍待律师核对。'])
    chosen = selection(w, basis.manifest.stable_task_id)
    second, current = execute(w, chosen)
    record_property('continuation_wire_utf8_bytes', current.wire_bytes)
    assert current.manifest.model_dump(mode='json')['history_format'] == 'contract-full-text-v1'
    assert current.manifest.stable_task_id == basis.manifest.stable_task_id
    assert len(current.manifest.materials) == len(basis.manifest.materials) + 1
    assert [(item.role, item.content) for item in current.manifest.conversation_history] == [
        ('user', basis.manifest.question), ('assistant', first.output.candidate.text)]
    assert current.manifest.conversation_history[1].message_id == first.output.id
    assert second.output is not None and second.output.manifest == current.manifest
    with w[0].session() as db:
        assert attempts.read_attempt(w[1], first.id, db) == first
        assert attempts.read_attempt(w[1], second.id, db) == second
        validate_model_records(db)
        assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(first.id)}) == original
        attempt_count = db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))
        record_property('attempt_count', attempt_count)
        assert attempt_count == 2


def test_historical_assembly_keeps_old_whole_pair_omission_and_saved_reply_readable(long_contract):
    w, first, basis = long_contract
    chosen = selection(w, basis.manifest.stable_task_id)
    with w[0].session() as db:
        before = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(first.id)})
        historical, _ = material_preparation.assemble(w[1], chosen, db, historical=True,
            contract_review=basis.manifest.contract_review)
        assert historical.conversation_history == ()
        assert attempts.read_attempt(w[1], first.id, db) == first
        validate_model_records(db)
        assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id': str(first.id)}) == before


def test_contract_without_prior_reply_still_previews_with_empty_history(material_world):
    w = material_world
    current = material_preparation.preview(w[1], selection(w), w[0], config())
    assert current.manifest.workflow == 'contract'
    assert current.manifest.model_dump(mode='json').get('history_format') == 'contract-full-text-v1'
    assert current.manifest.conversation_history == ()
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_short_contract_reply_is_carried_forward_without_truncation(material_world):
    w = material_world
    first, basis = execute(w, selection(w))
    current = material_preparation.preview(w[1], selection(w, basis.manifest.stable_task_id), w[0], config())
    assert current.manifest.model_dump(mode='json')['history_format'] == 'contract-full-text-v1'
    assert [(item.role, item.content) for item in current.manifest.conversation_history] == [
        ('user', basis.manifest.question), ('assistant', first.output.candidate.text)]
    assert current.manifest.conversation_history[1].message_id == first.output.id


def test_oversized_reply_in_other_contract_task_does_not_block_new_task(oversized_contract):
    w, first, basis = oversized_contract
    current = material_preparation.preview(w[1], selection(w), w[0], config())
    assert current.manifest.stable_task_id != basis.manifest.stable_task_id
    assert current.manifest.conversation_history == ()
    with w[0].session() as db:
        assert attempts.read_attempt(w[1], first.id, db) == first
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1


def test_current_contract_preview_rejects_latest_pair_above_versioned_budget(oversized_contract):
    w, first, basis = oversized_contract
    chosen = selection(w, basis.manifest.stable_task_id)
    with pytest.raises(ServiceError) as failure:
        material_preparation.preview(w[1], chosen, w[0], config())
    assert (failure.value.code, failure.value.status_code) == ('MATERIAL_HISTORY_TOO_LARGE', 409)
    with w[0].session() as db:
        assert attempts.read_attempt(w[1], first.id, db) == first
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1


def test_http_capacity_error_never_authorizes_or_creates_second_attempt(oversized_contract, tmp_path):
    w, first, basis = oversized_contract
    chosen = selection(w, basis.manifest.stable_task_id)
    provider = MaterialProvider(config())
    registry = MainModelRegistry()
    registry.configure(provider)
    with boot(w, tmp_path, registry) as http:
        body = chosen.model_dump(mode='json')
        preview = http.client.post(http.url + '/material-preview', headers=http.headers, json=body)
        submitted = http.client.post(http.url + '/material-generations', headers=http.headers, json=body)
        assert not registry._grants
        assert provider.calls == []
        with w[0].session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert attempts.read_attempt(w[1], first.id, db) == first
        assert preview.status_code == 409, preview.text
        assert preview.json()['code'] == 'MATERIAL_HISTORY_TOO_LARGE'
        assert submitted.status_code == 409, submitted.text
        assert submitted.json()['code'] == 'MATERIAL_HISTORY_TOO_LARGE'


def test_new_history_format_is_not_accepted_by_other_material_workflows(material_world):
    w = material_world
    current = material_preparation.preview(w[1], selection_for(w, 'case'), w[0], config())
    assert 'history_format' not in current.manifest.model_dump(mode='json')
    raw = current.manifest.model_dump(mode='json') | {'history_format': 'contract-full-text-v1'}
    with pytest.raises(ValueError):
        d.MainMaterialManifest.model_validate(raw)


def test_new_format_empty_history_is_rebuilt_and_rejected_when_a_reply_exists(material_world):
    w = material_world
    _, first_basis = execute(w, selection(w))
    second, _ = execute(w, selection(w, first_basis.manifest.stable_task_id))
    with w[0].session() as db:
        row = dict(attempts._row(second.id, db))
        saved = attempts._input(row)
        assert saved.request.basis.manifest.model_dump(mode='json')['history_format'] == 'contract-full-text-v1'
        empty = saved.request.basis.manifest.model_copy(update={'conversation_history': ()})
        forged_basis = material_codec.build_basis(material_preparation.selection_for(saved.request.basis), empty, config())
        forged = material_codec.prepare(saved.request.model_copy(update={'basis': forged_basis}), config())
        # Rehash only in-memory candidate records; the immutable ledger remains untouched.
        row.update(input_json=encoded(forged), request_sha256=sha(forged.wire_payload_json))
        policy = d.MainModelPolicy.model_validate_json(row['policy_json'])
        run = service._owned_run(w[1], second.run_id, db)
        with pytest.raises(ValueError, match='MATERIAL_INPUT_INVALID'):
            material_integrity.validate_input(db, row, forged, config(), policy, run)
        assert attempts.read_attempt(w[1], second.id, db) == second
        validate_model_records(db)


def test_legacy_completed_contract_history_keeps_exact_saved_json_and_wire(material_world, monkeypatch):
    w = material_world
    with monkeypatch.context() as legacy:
        legacy.setattr(material_preparation, 'CURRENT_CONTRACT_HISTORY_FORMAT', None, raising=False)
        first, basis = execute(w, selection(w))
        second, _ = execute(w, selection(w, basis.manifest.stable_task_id))
        assert second.output.manifest.conversation_history[1].content == first.output.candidate.text
        with w[0].session() as db:
            frozen = [(item, dict(attempts._row(item.id, db)), db.scalar(text(
                'SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id': str(item.id)}))
                for item in (first, second)]
    with w[0].session() as db:
        for item, row, original_output in frozen:
            assert 'history_format' not in json.loads(row['input_json'])['request']['basis']['manifest']
            prepared = attempts._input(row)
            assert material_codec.prepare(prepared.request, config()).wire_payload_json == prepared.wire_payload_json
            assert encoded(material_codec.prepare(prepared.request, config())) == row['input_json']
            assert attempts.read_attempt(w[1], item.id, db) == item
            assert attempts._row(item.id, db)['input_json'] == row['input_json']
            assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
                {'id': str(item.id)}) == original_output
        validate_model_records(db)


def test_legacy_queued_contract_sends_the_original_wire_after_upgrade(material_world, monkeypatch):
    w = material_world
    chosen = selection(w)
    with monkeypatch.context() as legacy:
        legacy.setattr(material_preparation, 'CURRENT_CONTRACT_HISTORY_FORMAT', None, raising=False)
        basis = material_preparation.preview(w[1], chosen, w[0], config())
    with server(response(basis)) as (url, received, _):
        async def scenario():
            with monkeypatch.context() as legacy:
                legacy.setattr(material_preparation, 'CURRENT_CONTRACT_HISTORY_FORMAT', None, raising=False)
                _, lease, approved = grant(w, chosen, DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url))
                with w[0].session() as db:
                    queued = material_attempts.enqueue(w[1], chosen, approved, db, lease)
                    original = attempts._row(queued.id, db)['input_json']
                    prepared = attempts._input(attempts._row(queued.id, db))
            result = await execute_attempt(w[1], queued.id, w[0], lease)
            assert result.output is not None
            assert 'history_format' not in result.output.manifest.model_dump(mode='json')
            assert await execute_attempt(w[1], queued.id, w[0], lease) == result
            with w[0].session() as db:
                assert attempts._row(queued.id, db)['input_json'] == original
                assert attempts.read_attempt(w[1], queued.id, db) == result
                validate_model_records(db)
            return prepared.wire_payload_json
        original_wire = asyncio.run(scenario())
    assert len(received) == 1
    assert received[0]['body'] == original_wire.encode('utf-8')


def test_new_version_continues_legacy_long_reply_and_legacy_empty_followup(material_world, monkeypatch, record_property):
    w = material_world
    old_selector = material_history.select_history

    def before_capacity_guard(*args, **kwargs):
        kwargs['require_latest'] = False
        return old_selector(*args, **kwargs)

    with monkeypatch.context() as legacy:
        legacy.setattr(material_preparation, 'CURRENT_CONTRACT_HISTORY_FORMAT', None, raising=False)
        # Reproduce the known old selection rule through normal sends, without rewriting records.
        legacy.setattr(material_history, 'select_history', before_capacity_guard)
        _, first, basis = _saved_long_contract(w, record_property)
        second, legacy_basis = execute(w, selection(w, basis.manifest.stable_task_id))
        assert legacy_basis.manifest.conversation_history == ()
        assert 'history_format' not in legacy_basis.manifest.model_dump(mode='json')
        with w[0].session() as db:
            original_rows = [(item.id, attempts._row(item.id, db)['input_json'], db.scalar(text(
                'SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id': str(item.id)}))
                for item in (first, second)]
    third, current = execute(w, selection(w, basis.manifest.stable_task_id))
    assert current.manifest.model_dump(mode='json')['history_format'] == 'contract-full-text-v1'
    assert [item.content for item in current.manifest.conversation_history][1::2] == [
        first.output.candidate.text, second.output.candidate.text]
    assert third.output is not None
    with w[0].session() as db:
        for identifier, original_input, original_output in original_rows:
            assert attempts._row(identifier, db)['input_json'] == original_input
            assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
                {'id': str(identifier)}) == original_output
        assert attempts.read_attempt(w[1], first.id, db) == first
        assert attempts.read_attempt(w[1], second.id, db) == second
        validate_model_records(db)


def test_small_wire_budget_rejects_instead_of_adaptively_dropping_contract_history(long_contract):
    w, _, basis = long_contract
    chosen = selection(w, basis.manifest.stable_task_id)
    with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
        material_preparation.preview(w[1], chosen, w[0], config(max_input_bytes=40000))
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1


def test_preview_checks_persisted_envelope_even_when_wire_fits(material_world, record_property):
    w = material_world
    add_document(w, ['独立虚构容量材料。' * 600 for _ in range(8)])
    chosen = selection(w)
    with w[0].session() as db:
        manifest, _ = material_preparation.assemble(w[1], chosen, db)
    basis = material_codec.build_basis(chosen, manifest, config())
    request = d.MainMaterialRequest(run_id=uuid4(), message_id=uuid4(),
        scope=chosen.expected_scope.model_copy(update={'input_revision': chosen.expected_scope.input_revision + 1}),
        basis=basis)
    wire = json.dumps(material_codec.build_request(request, config()), ensure_ascii=False,
        sort_keys=True, separators=(',', ':'))
    prepared = d.MainMaterialPreparedInput(request=request, wire_payload_json=wire)
    envelope_bytes = len(encoded(prepared).encode('utf-8'))
    record_property('wire_utf8_bytes', len(wire.encode('utf-8')))
    record_property('prepared_utf8_bytes', envelope_bytes)
    assert len(wire.encode('utf-8')) <= 262144 < envelope_bytes
    with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
        material_preparation.preview(w[1], chosen, w[0], config())
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
