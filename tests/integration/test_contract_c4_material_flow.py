"""Synthetic contract material flow through native consent; never uses a network."""
import asyncio
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, business, material_attempts, material_codec
from cn_contract.assistant import material_preparation, service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.policy import reservation
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt
from cn_contract.security import ServiceError, authenticate, login
from tests.integration.test_assistant_attachments import sample
from tests.integration.test_assistant_generation import SyntheticProvider, world


SECRET = 'SYNTHETIC_MATERIAL_FLOW_NOT_A_REAL_KEY_12345'
CONTRACT = ('独立虚构测试合同。甲方：虚构晨星公司；乙方：虚构海湾公司。'
    '货款总额100000元，预付款30000元，验收后支付剩余70000元。'
    '乙方应于2026年11月1日交货；附件另记交货日为2026年11月15日，待核。'
    '逾期付款每日按欠款的万分之五计收违约金。此材料仅用于离线工程验证。')


def prepare_synthetic_contract(database, actor, conversation):
    """Reusable production-service upload/parse/business/selection preparation."""
    cid = conversation.scope.conversation_id
    raw = sample(CONTRACT)
    database._assistant_synthetic_hashes = frozenset({sha256(raw).hexdigest()})
    uploaded = attachments.ingest_attachment(actor, cid, d.AssistantAttachmentInput(
        request_id=uuid4(), expected_scope=conversation.scope,
        original_name='独立虚构合同.docx',
        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)),
        BytesIO(raw), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    parsed = attachments.parse_attachment(actor, cid, uploaded.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope),
        database=database)
    with database.session() as db:
        current = service.read_conversation(actor, cid, db)
        result = business.submit(actor, cid, d.BusinessInput(request_id=uuid4(),
            expected_scope=current.scope, expected_composer_revision=current.composer_revision,
            content='请审查这份合同，核对付款金额、交货日期冲突及修改建议。'), db)
        current = service.read_conversation(actor, cid, db)
    selection = d.MainMaterialSelection(request_id=uuid4(), expected_scope=current.scope,
        expected_composer_revision=current.composer_revision, parent_business_run_id=result.run_id)
    return SimpleNamespace(raw=raw, uploaded=uploaded, parsed=parsed,
        business_result=result, selection=selection)


class MaterialProvider(SyntheticProvider):
    """Exercise the actual material wire encoder/decoder with a fixed local reply."""
    after_send = None

    async def generate_material(self, request, *, expected_config=None, preflight=None):
        assert expected_config == self.config
        assert callable(preflight) and preflight()
        wire = material_codec.build_request(request, self.config)
        self.calls.append(wire)
        source_id = next(item.source_id for item in request.basis.manifest.sources
            if item.reference.kind == 'document')
        candidate = {'text': '合成待核草稿：交货日期存在冲突，请律师核对。[' + source_id + ']',
            'citations': [source_id]}
        raw = json.dumps({'id': 'synthetic-material-response', 'object': 'chat.completion',
            'created': 1, 'model': self.config.model,
            'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30},
            'choices': [{'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': json.dumps(candidate)}}]}).encode()
        if self.after_send:
            self.after_send()
        return material_codec.decode(raw, request, self.config, SECRET)


@pytest.fixture
def material_flow(world):
    database, _, conversation, _, runtime = world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
    prepared = prepare_synthetic_contract(database, actor, conversation)
    registry = MainModelRegistry()
    providers = []

    def factory(config, resolver):
        provider = MaterialProvider(config)
        providers.append(provider)
        return provider

    return SimpleNamespace(database=database, actor=actor, token=token,
        config=runtime.provider.config, prepared=prepared, registry=registry, providers=providers,
        control=NativeModelControl(database, registry, provider_factory=factory))


def configure_and_preview(flow):
    configured = flow.control.configure({'config': flow.config, 'secret': SECRET})
    basis = material_preparation.preview(flow.actor, flow.prepared.selection, flow.database, flow.config)
    return {'session_token': flow.token, 'expected_config_version': configured['config_version'],
        'basis': basis, 'max_total_usd': str(reservation(flow.config)), 'valid_for_seconds': 120}


def enqueue(flow, basis, lease):
    with flow.database.session() as db:
        return material_attempts.enqueue(flow.actor, flow.prepared.selection, basis, db, lease)


def test_contract_material_flow_persists_source_bound_output_and_never_resends(material_flow):
    f = material_flow

    async def scenario():
        payload = configure_and_preview(f)
        basis = payload['basis']
        assert f.prepared.parsed.parse.reading_status == 'readable'
        assert basis.manifest.workflow == 'contract'
        assert basis.manifest.stable_task_id == f.prepared.business_result.task_id
        document_source = next(item for item in basis.manifest.sources if item.reference.kind == 'document')
        assert document_source.reference.anchor.quote == CONTRACT
        assert basis.manifest.materials[0].original_sha256 == sha256(f.prepared.raw).hexdigest()
        assert f.providers[0].calls == []
        with f.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert f.control.authorize_material(payload) == {'status': 'authorized'}
        lease = f.registry.resolve(f.actor, basis.expected_scope)
        assert lease.snapshot()[1].max_calls == 1
        assert f.control.authorize_material(payload) == {'status': 'authorized'}
        queued = enqueue(f, basis, lease)
        assert queued.state == 'reserved'
        completed = await execute_attempt(f.actor, queued.id, f.database, lease)
        assert completed.state == 'received'
        assert completed.output is not None
        assert completed.output.manifest == basis.manifest
        assert completed.output.review_status == 'unverified'
        assert completed.output.audience == 'internal'
        assert completed.receipt.estimated_cost_usd == Decimal('0.000018')
        assert completed.output.candidate.citations == (document_source.source_id,)
        assert f.control.authorize_material(payload) == {'status': 'existing'}
        assert enqueue(f, basis, lease) == completed
        assert await execute_attempt(f.actor, queued.id, f.database, lease) == completed
        with f.database.session() as db:
            assert attempts.read_attempt(f.actor, queued.id, db) == completed
            validate_model_records(db)
            business.validate_business_records(db, allowed=True)
            persisted = db.scalar(text('SELECT output_json FROM assistant_model_outputs'))
            assert d.MainMaterialOutputView.model_validate_json(persisted) == completed.output
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 1
        assert len(f.providers[0].calls) == 1
        wire = f.providers[0].calls[0]
        assert wire['model'] == 'deepseek-flash'
        assert 'C4材料草稿适配版' in wire['messages'][0]['content']
        assert '算式结果相等不能同时声称数值不符' in wire['messages'][0]['content']
        assert wire['thinking'] == {'type': 'disabled'}
        assert json.loads(wire['messages'][1]['content']) == basis.manifest.model_dump(mode='json')
        assert attachments.read_original(f.actor, basis.expected_scope.conversation_id,
            f.prepared.uploaded.attachment.id, database=f.database) == f.prepared.raw

    asyncio.run(scenario())


def test_material_preview_and_insufficient_budget_cannot_authorize_a_send(material_flow):
    f = material_flow

    async def scenario():
        payload = configure_and_preview(f)
        lease = f.registry.resolve(f.actor, payload['basis'].expected_scope)
        with pytest.raises(ServiceError):
            enqueue(f, payload['basis'], lease)
        payload['max_total_usd'] = '0.000000000001'
        with pytest.raises(ServiceError) as failure:
            f.control.authorize_material(payload)
        assert failure.value.code == 'BLOCKED_LIVE'
        with f.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert f.providers[0].calls == []

    asyncio.run(scenario())


def test_pre_c4_completed_material_history_remains_readable(material_flow, monkeypatch):
    f = material_flow

    async def scenario():
        with monkeypatch.context() as legacy:
            legacy.setattr(material_codec, 'system_for', lambda workflow: material_codec.SYSTEM)
            payload = configure_and_preview(f)
            f.control.authorize_material(payload)
            lease = f.registry.resolve(f.actor, payload['basis'].expected_scope)
            queued = enqueue(f, payload['basis'], lease)
            completed = await execute_attempt(f.actor, queued.id, f.database, lease)
            assert completed.output is not None
            assert f.providers[0].calls[0]['messages'][0]['content'] == material_codec.SYSTEM
        assert 'C4材料草稿适配版' in material_codec.system_for('contract')
        with f.database.session() as db:
            validate_model_records(db)
            assert attempts.read_attempt(f.actor, queued.id, db) == completed
            prepared = attempts._input(attempts._row(queued.id, db))
            assert material_codec.prepare(prepared.request, f.config) == prepared
        assert await execute_attempt(f.actor, queued.id, f.database, lease) == completed
        assert len(f.providers[0].calls) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize('moment', ['before_send', 'after_send'])
def test_material_revocation_blocks_send_or_discards_output_without_erasing_cost(material_flow, moment):
    f = material_flow

    async def scenario():
        payload = configure_and_preview(f)
        f.control.authorize_material(payload)
        lease = f.registry.resolve(f.actor, payload['basis'].expected_scope)
        queued = enqueue(f, payload['basis'], lease)
        revoke = lambda: f.control.revoke({'session_token': f.token})
        if moment == 'before_send':
            revoke()
        else:
            f.providers[0].after_send = revoke
        result = await execute_attempt(f.actor, queued.id, f.database, lease)
        assert result.output is None
        assert result.receipt.cost_status == ('not_sent' if moment == 'before_send' else 'estimated')
        assert len(f.providers[0].calls) == (0 if moment == 'before_send' else 1)
        assert await execute_attempt(f.actor, queued.id, f.database, lease) == result
        with f.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1

    asyncio.run(scenario())


def test_selected_material_change_after_authorization_never_sends(material_flow):
    f = material_flow

    async def scenario():
        payload = configure_and_preview(f)
        f.control.authorize_material(payload)
        lease = f.registry.resolve(f.actor, payload['basis'].expected_scope)
        queued = enqueue(f, payload['basis'], lease)
        current = attachments.read_materials(f.actor, queued.scope.conversation_id, database=f.database)
        attachments.select_materials(f.actor, queued.scope.conversation_id,
            d.AssistantMaterialSelectionInput(request_id=uuid4(), expected_scope=current.scope, items=()),
            database=f.database)
        result = await execute_attempt(f.actor, queued.id, f.database, lease)
        assert result.state == 'failed_before_send'
        assert result.receipt.cost_status == 'not_sent'
        assert result.output is None
        assert f.providers[0].calls == []

    asyncio.run(scenario())
