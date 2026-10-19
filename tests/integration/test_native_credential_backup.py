"""Native credentials remain outside portable case backups (synthetic markers only)."""
import json
from pathlib import Path
from zipfile import ZipFile

from cn_contract.ops import workspace_backup
from cn_contract.web import local_server


def test_native_model_ciphertext_is_not_exported_or_restored(tmp_path):
    parent = tmp_path / '独立 合成桌面'
    root = parent / 'workspaces' / 'main'
    local_server.initialize_workspace(root, 'synthetic-lawyer', 'fixture123', data_parent=parent)
    vault = parent / 'model-credentials'
    vault.mkdir()
    marker = b'INDEPENDENT-SYNTHETIC-ENCRYPTED-CREDENTIAL-MARKER'
    credential = vault / 'deepseek.bin'
    credential.write_bytes(marker)
    archive = tmp_path / 'synthetic.qxbak'
    passphrase = 'independent-synthetic-backup-only'
    workspace_backup.create_workspace_backup(root, archive, passphrase, data_parent=parent)
    plain = tmp_path / 'synthetic-decrypted.zip'
    workspace_backup._decrypt(archive, plain, passphrase)
    with ZipFile(plain) as content:
        manifest = json.loads(content.read('manifest.json'))
        assert {item['path'] for item in manifest['files']} == {'workbench.db', 'workspace.json'}
        assert all(marker not in content.read(name) for name in content.namelist())
        assert all('credential' not in name for name in content.namelist())
    restored = Path(workspace_backup.restore_workspace_backup(
        archive, parent / 'restores', passphrase)['restored_root'])
    assert not list(restored.rglob('*deepseek*'))
    assert not list(restored.rglob('*credential*'))
    assert credential.read_bytes() == marker
