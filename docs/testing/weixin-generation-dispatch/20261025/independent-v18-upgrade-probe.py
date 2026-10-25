"""Synthetic end-to-end proof: v19 delivery cannot be laundered by v18 upgrade."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from cn_contract.ops.file_paths import sqlite_readonly_uri
from cn_contract.storage_schema import identify_schema, schema_rows
from cn_contract.web import local_server, workspace_upgrade
from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
from tests.integration.test_weixin_generation_dispatch_integrity import (
    chain, deliver, freeze_v18, validate,
)
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_provenance_backup import original_material


def tree(root):
    return ({path.relative_to(root).as_posix(): path.read_bytes()
             for path in root.rglob('*') if path.is_file()},
            sorted(path.relative_to(root).as_posix()
                   for path in root.rglob('*') if path.is_dir()))


def test_native_upgrade_rejects_nonzero_delivery_under_exact_v18_before_any_write(world, tmp_path):
    history = chain(world)
    root, database = history['root'], history['database']
    _, version, original = original_material(history)
    receipt = deliver(history, history['one'][1], history['first'])
    assert receipt.task_binding_id == history['first'].task_binding_id
    assert receipt.task_binding_id != history['mapping'].task_binding_id
    validate(history)
    freeze_v18(history)
    marker_path = root/'workspace.json'
    marker = json.loads(marker_path.read_text('utf-8'))
    with closing(sqlite3.connect(sqlite_readonly_uri(root/'workbench.db'), uri=True)) as connection:
        rows = connection.execute(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        assert rows == schema_rows('weixin-target-provenance-v1', native=True)
        assert identify_schema(rows, native=True) == 'weixin-target-provenance-v1'
        assert connection.execute('PRAGMA quick_check').fetchall() == [('ok',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert connection.execute('SELECT id FROM local_workspace_identity').fetchall() == [(marker['workspace_id'],)]
        marker['schema_sha256'] = local_server._schema_hash(connection)
    marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding='utf-8')
    # The schema, native identity and refreshed marker pass startup validation.
    assert local_server._open_workspace(root, data_parent=tmp_path) == root
    with database.session() as records, pytest.raises(ValueError, match='WEIXIN_DISPATCH_INTEGRITY'):
        validate_dispatch_records(records, allow_dispatch=True)
    database.engine.dispose()
    original_path = root/'protected'/version.storage_ref
    assert original_path.read_bytes() == original
    assert not (root/'upgrade-backups').exists()
    assert not list(root.glob('upgrade-*.json'))
    before_files, before_directories = tree(root)
    with local_server._worker_lock(root):
        with pytest.raises(ValueError, match='^WORKSPACE_DATABASE_MISMATCH$') as refusal:
            workspace_upgrade.upgrade(root)
    after_files, after_directories = tree(root)
    assert after_files == before_files
    assert after_directories == before_directories
    assert original_path.read_bytes() == original
    assert not (root/'upgrade-backups').exists()
    assert not list(root.glob('upgrade-*.json'))
    proof = {
        'synthetic_only': True,
        'v19_nonzero_receipt_validated': True,
        'exact_v18_schema': 'weixin-target-provenance-v1',
        'refreshed_marker_and_native_startup_validated': True,
        'v18_dispatch_validator_refused': True,
        'actual_upgrade_refusal': str(refusal.value),
        'file_bytes_unchanged': True,
        'directories_unchanged': True,
        'original_bytes_unchanged': True,
        'upgrade_backup_and_receipt_absent': True,
        'before_file_sha256': {name: sha256(data).hexdigest() for name, data in before_files.items()},
        'after_file_sha256': {name: sha256(data).hexdigest() for name, data in after_files.items()},
        'before_directories': before_directories,
        'after_directories': after_directories,
        'not_in_root_test_count': True,
    }
    (Path(__file__).parent/'independent-v18-upgrade-proof.json').write_text(
        json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
