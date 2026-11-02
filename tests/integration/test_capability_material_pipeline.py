"""Actual preparation, model wire, immutable result and historical validation."""
import asyncio
import json
from pathlib import Path
import pytest
from cn_contract.assistant import material_preparation, material_attempts, material_codec
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.security import ServiceError
from test_assistant_material_generation import material_world, selection_for, grant, response
from test_assistant_generation import world
from test_assistant_main_provider import config, server, KEY
from tests.unit.test_skill_registry import package, registry


@pytest.mark.parametrize('workflow', ['sales','case','contract'])
def test_registered_method_reaches_wire_ledger_and_output(material_world, tmp_path, workflow):
    database, actor, _, _ = material_world
    bindings = [package(tmp_path, 'sales'), package(tmp_path, 'case')]
    database._capability_registry = registry(tmp_path, bindings)
    selection = selection_for(material_world, workflow)
    basis = material_preparation.preview(actor, selection, database, config())
    assert basis.manifest.capability.workflow == workflow
    from tests.helpers.contract_review import response as contract_response
    with server(contract_response(basis) if workflow == 'contract' else response(basis)) as (url, received, _):
        async def scenario():
            _, lease, approved = grant(material_world, selection,
                DeepSeekProvider.for_synthetic_loopback(config(), lambda:KEY, url))
            with database.session() as db:
                attempt = material_attempts.enqueue(actor, selection, approved, db, lease)
            result = await execute_attempt(actor, attempt.id, database, lease)
            assert result.output is not None
            assert result.output.manifest.capability == approved.manifest.capability
            assert await execute_attempt(actor, attempt.id, database, lease) == result
            with database.session() as db:
                validate_model_records(db)
            return result
        result = asyncio.run(scenario())
        assert len(received) == 1
        wire = json.loads(received[0]['body'])
        sent = json.loads(wire['messages'][1]['content'])['capability']
        assert sent['method_sha256'] == result.output.manifest.capability.method_sha256
        assert sent['source_id'] == result.output.manifest.capability.source_id
        assert 'root' not in sent
    # Historical results use their recorded method, independent of today's install.
    for binding in bindings:
        (Path(binding['root'])/'skills/instructions/SKILL.md').write_text('已改为另一版本', encoding='utf-8')
    with database.session() as db:
        validate_model_records(db)


def test_changed_skill_between_preview_and_enqueue_is_blocked(material_world, tmp_path):
    database, actor, _, _ = material_world
    binding = package(tmp_path)
    database._capability_registry = registry(tmp_path, [binding])
    selection = selection_for(material_world)
    basis = material_preparation.preview(actor, selection, database, config())
    with server(response(basis)) as (url, received, _):
        async def scenario():
            _, lease, approved = grant(material_world, selection,
                DeepSeekProvider.for_synthetic_loopback(config(), lambda:KEY, url))
            (Path(binding['root'])/'skills/instructions/SKILL.md').write_text('更换来源', encoding='utf-8')
            with database.session() as db, pytest.raises(ServiceError) as error:
                material_attempts.enqueue(actor, selection, approved, db, lease)
            assert error.value.code == 'CAPABILITY_UNAVAILABLE' and received == []
        asyncio.run(scenario())


def test_unconfigured_history_keeps_exact_previous_wire(material_world):
    database, actor, _, _ = material_world
    selection = selection_for(material_world)
    basis = material_preparation.preview(actor, selection, database, config())
    assert 'capability' not in basis.manifest.model_dump(mode='json')
    assert material_codec.rebuild_basis(basis, config()) == basis


def test_client_cannot_substitute_its_own_method_snapshot(material_world, tmp_path):
    database, actor, _, _ = material_world
    database._capability_registry = registry(tmp_path, [package(tmp_path)])
    selection = selection_for(material_world)
    basis = material_preparation.preview(actor, selection, database, config())
    forged = material_codec.build_basis(selection, basis.manifest.model_copy(update={
        'capability':basis.manifest.capability.model_copy(update={'source_id':'client-selected-source'})}), config())
    with server(response(basis)) as (url, received, _):
        async def scenario():
            _, lease, _ = grant(material_world, selection,
                DeepSeekProvider.for_synthetic_loopback(config(), lambda:KEY, url))
            with database.session() as db, pytest.raises(ServiceError):
                material_attempts.enqueue(actor, selection, forged, db, lease)
            assert not received
        asyncio.run(scenario())


def test_native_boot_loads_trusted_adjacent_registry(tmp_path):
    from cn_contract.web.local_server import initialize_workspace, build_local_app
    binding = package(tmp_path, 'sales')
    registry(tmp_path, [binding])
    root = tmp_path/'workspace'
    initialize_workspace(root, 'fixture-lawyer', 'fixture123', data_parent=tmp_path)
    app = build_local_app(root, data_parent=tmp_path)
    try:
        assert app.state.database._capability_registry.resolve('sales').source_id == binding['source_id']
    finally:
        app.state.database.engine.dispose()
