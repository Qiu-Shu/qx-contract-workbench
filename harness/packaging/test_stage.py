"""The Python compatibility entry forwards to the current release pipeline."""
import json
import os
from pathlib import Path
import runpy
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parent


@pytest.mark.parametrize('node,found,expected', [('explicit-node', None, 'explicit-node'), ('', 'path-node', 'path-node')])
def test_wrapper_forwards_arguments_and_child_failure(node, found, expected):
    with patch.dict(os.environ, {'QX_BUILD_NODE': node}), patch('shutil.which', return_value=found), \
         patch('sys.argv', [str(ROOT/'stage.py'), 'synthetic stage', '--refresh']), \
         patch('subprocess.call', return_value=7) as call:
        with pytest.raises(SystemExit) as result:
            runpy.run_path(str(ROOT/'stage.py'), run_name='__main__')
    assert result.value.code == 7
    call.assert_called_once_with([expected, str(ROOT/'stage.cjs'), 'synthetic stage', '--refresh'])


def test_wrapper_reports_missing_node_before_staging():
    with patch.dict(os.environ, {'QX_BUILD_NODE': ''}), patch('shutil.which', return_value=None), \
         patch('subprocess.call') as call:
        with pytest.raises(SystemExit, match='Node.js 24 is required'):
            runpy.run_path(str(ROOT/'stage.py'), run_name='__main__')
    call.assert_not_called()


def test_packaged_verified_delivery_uses_the_data_workspace():
    rows = json.loads((ROOT/'payload-config/portable.json').read_text(encoding='utf-8'))
    plugins = [p for block in rows for p in block.get('insert', []) if p.get('id') == 'qx-verified-delivery']
    assert len(plugins) == 1
    assert plugins[0]['name'] == '@APP@/plugins/verified-delivery/index.mjs'
    assert plugins[0]['config']['workspace'] == '@DATA@/workspace'
