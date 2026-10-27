"""Run the shipped browser modules' asynchronous/input checks in existing Node."""
from pathlib import Path
import shutil
import subprocess

import pytest
from tests.integration.test_api import api


@pytest.mark.parametrize('script', ['test_assistant_state.mjs', 'test_assistant_transport_input.mjs',
                                   'test_assistant_material_state.mjs', 'test_assistant_material_dom.mjs',
                                   'test_assistant_generation_state.mjs', 'test_assistant_generation_render.mjs',
                                   'test_assistant_material_generation.mjs',
                                   'test_assistant_generation_entry.mjs', 'test_assistant_profile_generation.mjs',
                                   'test_assistant_profile_panel.mjs', 'test_assistant_tasks.mjs',
                                   'test_assistant_weixin.mjs', 'test_assistant_weixin_generations.mjs',
                                   'test_assistant_weixin_pending.mjs'])
def test_browser_module_behaviour(script):
    node = shutil.which('node')
    assert node, 'The existing local Node runtime is required.'
    result = subprocess.run([node, '--test', str(Path(__file__).parents[2]/'scripts'/script)],
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_chat_module_import_graph_is_served_as_javascript(api):
    """Node import tests do not exercise the HTTP static-file allowlist."""
    import re
    client, _, _, module = api
    pending = ['assistant.mjs']
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        response = client.get('/static/' + name)
        assert response.status_code == 200, (name, response.status_code)
        assert response.headers['content-type'].startswith('text/javascript'), name
        assert response.content == (module.STATIC / name).read_bytes(), name
        pending.extend(re.findall(r"from\s+['\"]\./([a-z-]+\.mjs)['\"]", response.text))
    assert 'assistant-context.mjs' in visited
    assert 'assistant-weixin-generations.mjs' in visited
    assert 'assistant-weixin-pending.mjs' in visited
    assert client.get('/static/original.bin').status_code == 404
