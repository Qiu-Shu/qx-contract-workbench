"""Pinned local methods are input data; they never grant business permissions."""
import hashlib
import json
from pathlib import Path
import pytest
from cn_contract.security import ServiceError


def package(tmp_path, workflow='case', *, approved=True):
    root = tmp_path / workflow
    method = root / 'skills/instructions/SKILL.md'
    method.parent.mkdir(parents=True)
    method.write_text('# 合成方法\n保留相反证据；事实缺口明确标记。', encoding='utf-8')
    metadata = root / '.codex-plugin/plugin.json'
    metadata.parent.mkdir()
    metadata.write_text(json.dumps({'name':'fictional-'+workflow,'version':'0.2.0'}), encoding='utf-8')
    return {'workflow':workflow,'source_id':'fictional-'+workflow,'version':'0.2.0',
        'root':str(root),'source_reference':'https://example.invalid/fictional-'+workflow,
        'license_notice':'Independent synthetic test fixture; no upstream material.',
        'local_use_approved':approved,
        'metadata_sha256':hashlib.sha256(metadata.read_bytes()).hexdigest(),
        'method_sha256':hashlib.sha256(method.read_bytes()).hexdigest()}


def registry(tmp_path, bindings):
    from cn_contract.integrations.skill_registry import SkillRegistry
    path = tmp_path / 'capabilities.json'
    path.write_text(json.dumps({'schema_version':1,'skills':bindings}), encoding='utf-8')
    return SkillRegistry.from_file(path)


def test_pinned_source_and_builtin_contract_are_resolved(tmp_path):
    from cn_contract.assistant.contract_method import METHOD, METHOD_ID
    binding = package(tmp_path)
    value = registry(tmp_path, [binding])
    case = value.resolve('case')
    assert case.source_id == binding['source_id'] and case.version == '0.2.0'
    assert case.method_text == (Path(binding['root'])/'skills/instructions/SKILL.md').read_bytes().decode('utf-8')
    assert case.method_sha256 == binding['method_sha256']
    contract = value.resolve('contract')
    assert contract.source_id == 'qx-contract-workbench' and contract.version == METHOD_ID
    assert contract.method_text is None and contract.method_sha256 == hashlib.sha256(METHOD.encode()).hexdigest()


@pytest.mark.parametrize('change', ['method','metadata','missing','unapproved','mislabeled','absent'])
def test_unavailable_or_changed_source_never_falls_back(tmp_path, change):
    binding = package(tmp_path, approved=change != 'unapproved')
    if change == 'mislabeled':
        binding['version'] = '9.9.9'
    value = registry(tmp_path, [binding])
    root = Path(binding['root'])
    if change == 'method':
        (root/'skills/instructions/SKILL.md').write_text('被更换的方法', encoding='utf-8')
    elif change == 'metadata':
        (root/'.codex-plugin/plugin.json').write_text('{}', encoding='utf-8')
    elif change == 'missing':
        (root/'skills/instructions/SKILL.md').unlink()
    with pytest.raises(ServiceError) as error:
        value.resolve('sales' if change == 'absent' else 'case')
    assert error.value.code == 'CAPABILITY_UNAVAILABLE'


def test_duplicate_workflow_and_relative_root_are_rejected(tmp_path):
    binding = package(tmp_path)
    with pytest.raises(ValueError):
        registry(tmp_path, [binding, binding])
    with pytest.raises(ValueError):
        registry(tmp_path, [{**binding,'root':'../elsewhere'}])
