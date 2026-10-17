"""Run the shipped browser modules' asynchronous/input checks in existing Node."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('script', ['test_assistant_state.mjs', 'test_assistant_transport_input.mjs'])
def test_browser_module_behaviour(script):
    node = shutil.which('node')
    assert node, 'The existing local Node runtime is required.'
    result = subprocess.run([node, '--test', str(Path(__file__).parents[2]/'scripts'/script)],
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
