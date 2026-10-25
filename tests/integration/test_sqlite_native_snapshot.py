"""Reference verification can open deep snapshots without changing their sources."""
import shutil

from cn_contract.ops import workspace_backup
from cn_contract.ops.file_paths import filesystem_path
from tests.integration.test_assistant_attachment_backup import source


def test_deep_snapshot_reference_validation_preserves_original_logical_paths(source,tmp_path):
    root,database,*_=source
    database.engine.dispose()
    deep=tmp_path
    while len(str(deep/'workbench.db'))<300:
        deep/='独立 合成%23#快照'
    assert len(str(deep/'workbench.db'))>=300
    shutil.copytree(filesystem_path(root),filesystem_path(deep))
    expected=workspace_backup._references(root,workspace_backup._inventory(root),source=True)
    before=workspace_backup._inventory(deep)
    assert workspace_backup._references(deep,before)==expected
    assert all(not item['logical_ref'].startswith('\\\\?\\') for item in expected)
    assert workspace_backup._inventory(deep)==before
    assert workspace_backup._references(deep,before,source=True)==expected
    assert workspace_backup._inventory(deep)==before
