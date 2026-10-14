"""Move a complete invented library, never its original input."""
import importlib
import importlib.util
import json
import shutil

import pytest


def test_export_relative_assets_restore_elsewhere(tmp_path):
    assert importlib.util.find_spec('cn_contract.library.portability'), 'portable manifest missing'
    portable = importlib.import_module('cn_contract.library.portability')
    from cn_contract.library.law_sections import import_laws
    from cn_contract.library.index import build_generation, activate_generation
    from cn_contract.library.service import search, read_original
    from cn_contract.domain import LibraryQuery
    laws = tmp_path / 'laws'
    laws.mkdir()
    text = '第一条 虚构租赁法规，不是真实法源。'
    (laws / '虚构法律.md').write_text(text, encoding='utf-8')
    root = tmp_path / 'library'
    import_laws(root, laws, 'fiction')
    activate_generation(root, build_generation(root))
    destination = tmp_path / 'portable.json'
    portable.export_manifest(root, destination)
    raw = destination.read_text(encoding='utf-8')
    assert str(tmp_path) not in raw and 'aliases' not in raw
    assert json.loads(raw)['sources'][0]['asset_key'].endswith('/original')
    with pytest.raises(FileExistsError):
        portable.export_manifest(root, destination)
    moved = tmp_path / '异地 恢复资料库'
    shutil.copytree(root, moved)
    assert portable.relocate_library(moved)['ok'] is True
    hit = search(moved, LibraryQuery(text='租赁')).hits[0]
    assert read_original(moved, hit.record_id, hit.version_id).text == text
    asset = next((moved / 'assets').glob('*/original'))
    asset.write_text('损坏后的虚构资料', encoding='utf-8')
    with pytest.raises(ValueError, match='ASSET_'):
        portable.export_manifest(moved, tmp_path / 'broken.json')
