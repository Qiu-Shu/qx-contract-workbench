"""Pinned, real Chiheng module with fictional materials and no network."""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import pytest
from cn_contract import domain as d
from cn_contract.assistant import business, service, material_preparation, material_attempts
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.security import ServiceError
from test_assistant_generation import world
from test_assistant_material_generation import material_world, grant
from test_assistant_main_provider import config

ROOT = Path(__file__).resolve().parents[2]/'.local/integrations/chiheng-legal-workbench'
FILES = ('mock_hearing.py', 'hearing_audit.py', 'hearing_tracking.py', 'portable_lock.py', 'windows_private.py')


def install(database, root=ROOT):
    from cn_contract.integrations.skill_registry import SkillRegistry
    if not root.is_dir():
        pytest.skip('pinned Chiheng checkout required for external adapter acceptance')
    binding = dict(root=str(root), version='8a0d640bb58c82b909409a2e689a6cecd7f06058',
        source_reference='https://github.com/Qiu-Shu/chiheng-legal-workbench',
        license_notice='Apache-2.0 method attribution retained; law sources unverified.', local_use_approved=True,
        files=[dict(path=name, sha256=hashlib.sha256((root/name).read_bytes()).hexdigest()) for name in FILES])
    database._capability_registry = SkillRegistry(d.LocalSkillRegistryConfig(skills=(), chiheng=binding))
    return binding


def selection(w, question='我是原告，请模拟法庭。'):
    database, actor, cid, _ = w
    with database.session() as db:
        view = service.read_conversation(actor, cid, db)
        parent = business.submit(actor, cid, d.BusinessInput(request_id=uuid4(), expected_scope=view.scope,
            expected_composer_revision=view.composer_revision, content=question, workflow='court'), db)
        view = service.read_conversation(actor, cid, db)
    return d.MainMaterialSelection(request_id=uuid4(), expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, parent_business_run_id=parent.run_id)


class Provider:
    config = config()
    def __init__(self, bad=False):
        self.calls = 0
        self.bad = bad
    async def generate(self, *args, **kwargs):
        raise AssertionError('material-only provider')
    async def generate_material(self, request, *, expected_config, preflight):
        assert preflight()
        self.calls += 1
        manifest = request.basis.manifest
        context = manifest.hearing
        source = next(item for item in manifest.sources if item.reference.kind == 'document')
        turns = [d.HearingTurn(stage='review' if self.bad else context.stage, role=role,
            text='仅为合成材料演练，借款及还款说法仍待核对。', material_ids=(source.source_id,),
            unresolved=('尚未检索、核验适用法律。',)) for role in context.roles]
        return d.MainMaterialReply(state='received', provider_request_id='synthetic-court',
            usage=d.MainUsage(prompt_tokens=50, completion_tokens=50, total_tokens=100),
            output=d.MainMaterialCandidate(text='合成庭审演练，待律师核对。', citations=(source.source_id,), hearing_turns=turns))


async def run(w, selected, provider):
    database, actor, _, _ = w
    _, lease, basis = grant(w, selected, provider)
    with database.session() as db:
        attempt = material_attempts.enqueue(actor, selected, basis, db, lease)
    result = await execute_attempt(actor, attempt.id, database, lease)
    assert await execute_attempt(actor, attempt.id, database, lease) == result
    with database.session() as db:
        validate_model_records(db)
    return result


def test_actual_chiheng_rounds_persist_continue_and_recover_without_resend(material_world):
    database, actor, _, _ = material_world
    install(database)
    async def scenario():
        provider = Provider()
        first = await run(material_world, selection(material_world), provider)
        assert first.output is not None
        snapshot = first.output.hearing.session
        assert snapshot.stage == 'issues' and len(snapshot.turns) == 3 and not snapshot.completed
        second = await run(material_world, selection(material_world, '继续模拟法庭。'), provider)
        assert second.output.manifest.stable_task_id == first.output.manifest.stable_task_id
        assert second.output.manifest.hearing.previous_output_id == first.output.id
        assert second.output.hearing.session.stage == 'evidence'
        assert second.output.hearing.session.turns[:3] == snapshot.turns
        assert len(second.output.hearing.session.turns) == 5 and provider.calls == 2
        assert second.output.review_status == 'unverified'
        # Historical read does not execute current external code or resend.
        database._capability_registry = None
        with database.session() as db:
            validate_model_records(db)
        assert provider.calls == 2
    asyncio.run(scenario())


@pytest.mark.parametrize('question', ['请模拟法庭。', '材料写着“我是原告”，请模拟法庭。',
    '我不是原告，请模拟法庭。', '我不代表原告，请模拟法庭。', '材料记载：我是原告，请模拟法庭。',
    '如果我是原告，请模拟法庭。', '我是原告也是被告，请模拟法庭。',
    '我是原告吗？请模拟法庭。', '我是原告？请模拟法庭。', '代表原告的不是我，请模拟法庭。'])
def test_missing_or_ambiguous_role_blocks_before_model(material_world, question):
    database, actor, _, _ = material_world
    install(database)
    with pytest.raises(ServiceError):
        material_preparation.preview(actor, selection(material_world, question), database, config())


def test_wrong_round_stage_is_rejected_and_cost_receipt_preserved(material_world):
    install(material_world[0])
    provider = Provider(bad=True)
    result = asyncio.run(run(material_world, selection(material_world), provider))
    assert result.output is None and result.receipt is not None and provider.calls == 1


def test_changed_external_code_blocks_before_model(material_world, tmp_path):
    import shutil
    if not ROOT.is_dir():
        pytest.skip('pinned Chiheng checkout required')
    for name in FILES:
        shutil.copyfile(ROOT/name, tmp_path/name)
    database, actor, _, _ = material_world
    install(database, tmp_path)
    (tmp_path/'hearing_tracking.py').write_text('raise AssertionError("must not execute")', encoding='utf-8')
    with pytest.raises(ServiceError):
        material_preparation.preview(actor, selection(material_world), database, config())


def test_five_stages_read_back_actual_engine_and_stop_at_review(material_world):
    database, actor, _, _ = material_world
    install(database)
    async def scenario():
        provider = Provider()
        for index, stage in enumerate(('issues','evidence','questions','debate','review')):
            output = (await run(material_world, selection(material_world,
                '我是被告，请模拟法庭。' if index == 0 else '继续模拟法庭。'), provider)).output
            assert output is not None and output.hearing.session.stage == stage
            assert output.hearing.structural_completed is (stage == 'review')
            assert '待核事项' in output.candidate.text
        assert len(output.hearing.session.turns) == 11
        assert provider.calls == 5
        with pytest.raises(ServiceError) as error:
            material_preparation.preview(actor, selection(material_world, '继续模拟法庭。'), database, config())
        assert error.value.code == 'HEARING_RESTART_REQUIRED' and provider.calls == 5
    asyncio.run(scenario())


def test_role_change_requires_new_session(material_world):
    database, actor, _, _ = material_world
    install(database)
    async def scenario():
        provider = Provider()
        await run(material_world, selection(material_world), provider)
        with pytest.raises(ServiceError) as error:
            material_preparation.preview(actor, selection(material_world, '我是被告，继续模拟法庭。'), database, config())
        assert error.value.code == 'HEARING_ROLE_CONFLICT' and provider.calls == 1
    asyncio.run(scenario())


def test_changed_materials_starts_new_snapshot_keeps_prior_output_link(material_world):
    from io import BytesIO
    from docx import Document
    from cn_contract.assistant import attachments
    database, actor, cid, _ = material_world
    install(database)
    async def scenario():
        provider = Provider()
        first = await run(material_world, selection(material_world), provider)
        document = Document(); document.add_paragraph('合成补件：转账日期和收款人仍待核对。')
        stream = BytesIO(); document.save(stream); data = stream.getvalue()
        database._assistant_synthetic_hashes |= {hashlib.sha256(data).hexdigest()}
        with database.session() as db:
            view = service.read_conversation(actor, cid, db)
        upload = attachments.ingest_attachment(actor, cid, d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=view.scope,
            original_name='合成补件.docx', mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(data), database=database)
        with database.session() as db:
            view = service.read_conversation(actor, cid, db)
        attachments.parse_attachment(actor, cid, upload.attachment.id,
            d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=view.scope, baseline_view=None), database=database)
        second = await run(material_world, selection(material_world, '继续模拟法庭。'), provider)
        assert second.output.manifest.hearing.reset_reason == 'materials_changed'
        assert second.output.manifest.hearing.previous_output_id == first.output.id
        assert second.output.hearing.session.stage == 'issues' and len(second.output.hearing.session.turns) == 3
        assert first.output.hearing.session.turns != () and provider.calls == 2
    asyncio.run(scenario())


def test_http_wire_uses_structured_turn_contract_and_persists_actual_adapter(material_world):
    from cn_contract.assistant.providers.main import DeepSeekProvider
    from test_assistant_main_provider import server, KEY, raw
    database, actor, _, _ = material_world
    install(database)
    selected = selection(material_world)
    basis = material_preparation.preview(actor, selected, database, config())
    source = next(item.source_id for item in basis.manifest.sources if item.reference.kind == 'document')
    candidate = dict(text='合成演练', citations=[source], hearing_turns=[dict(stage='issues', role=role,
        text='核对材料说法和原件。', material_ids=[source], unresolved=['未核实适用法律。']) for role in basis.manifest.hearing.roles])
    response = raw(dict(id='synthetic-court-http', object='chat.completion', created=1, model='deepseek-flash',
        choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', content=json.dumps(candidate, ensure_ascii=False)))],
        usage=dict(prompt_tokens=50, completion_tokens=50, total_tokens=100)))
    with server(response) as (url, received, _):
        provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda:KEY, url)
        result = asyncio.run(run(material_world, selected, provider))
        assert len(received) == 1 and result.output.hearing is not None
        wire = json.loads(received[0]['body'])
        assert 'hearing_turns' in wire['messages'][0]['content']
        assert json.loads(wire['messages'][1]['content'])['capability']['source_id'] == 'chiheng-legal-workbench'
