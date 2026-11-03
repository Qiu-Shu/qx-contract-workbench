"""The local recovery setting must not replace a user's existing profile."""
import importlib.util
from pathlib import Path
import yaml
import pytest


def load_deployer():
    path = Path(__file__).resolve().parents[1] / 'scripts/deploy-model-recovery.py'
    spec = importlib.util.spec_from_file_location('deploy_model_recovery', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deploy_appends_only_policy_and_is_idempotent(tmp_path):
    module = load_deployer()
    template = tmp_path / 'config/cordis.patch.yml'
    template.parent.mkdir()
    block = '\n# qunxing-model-recovery-v1\n- id: llm-deepseek\n  config:\n    retryPolicy:\n      mode: normal\n      retryableCodes: [MALFORMED_RESPONSE, STREAM_CLOSED, TRANSPORT]\n'
    template.write_text('- id: unrelated\n  disabled: true\n' + block, encoding='utf-8')
    profile = tmp_path / '.local/dsh-home/profiles/web/cordis.patch.yml'
    profile.parent.mkdir(parents=True)
    original = '# user configuration\r\n- id: unrelated\r\n  config: {choice: mine}\r\n'
    profile.write_bytes(original.encode('utf-8'))
    module.deploy(tmp_path)
    first = profile.read_bytes()
    assert first.startswith(original.encode('utf-8'))
    entries = yaml.safe_load(first.decode('utf-8'))
    assert len([row for row in entries if row.get('id') == 'llm-deepseek']) == 1
    assert b'MALFORMED_RESPONSE' in first and b'STREAM_CLOSED' in first
    backups = list((tmp_path / '.local/backups').glob('model-recovery-*.yml'))
    assert len(backups) == 1 and backups[0].read_bytes() == original.encode('utf-8')
    module.deploy(tmp_path)
    assert profile.read_bytes() == first
    assert list((tmp_path / '.local/backups').glob('model-recovery-*.yml')) == backups


@pytest.mark.parametrize('original', [
    '[{"id":"custom","config":{"choice":"mine"}}]\n',
    '- id: custom\n  config: {choice: mine}\n...\n',
    '[]\n',
])
def test_deploy_preserves_valid_yaml_forms(tmp_path, original):
    module = load_deployer()
    template = tmp_path / 'config/cordis.patch.yml'
    template.parent.mkdir()
    template.write_text('- id: llm-deepseek\n  config:\n    retryPolicy: {mode: normal, retryableCodes: [MALFORMED_RESPONSE]}\n', encoding='utf-8')
    profile = tmp_path / '.local/dsh-home/profiles/web/cordis.patch.yml'
    profile.parent.mkdir(parents=True)
    profile.write_bytes(original.encode('utf-8'))
    module.deploy(tmp_path)
    result = yaml.safe_load(profile.read_bytes())
    assert result[:-1] == yaml.safe_load(original)
    assert result[-1]['id'] == 'llm-deepseek'
    assert next((tmp_path / '.local/backups').glob('*.yml')).read_bytes() == original.encode('utf-8')
    saved = profile.read_bytes()
    module.deploy(tmp_path)
    assert profile.read_bytes() == saved
