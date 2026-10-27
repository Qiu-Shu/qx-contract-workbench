"""Portable offline replay, frozen inputs, and append-only output checks."""
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / 'scripts/contract_calculation_replay.py'
spec = importlib.util.spec_from_file_location('calculation_replay', SCRIPT)
replay_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_module)


def test_replay_has_no_network_and_does_not_promote(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('network prohibited in offline replay')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    report = replay_module.replay()
    assert report['records'] == 12 and report['unique_cases'] == 5
    assert report['check_statuses'] == {'not_covered': 42, 'blocked': 9, 'consistent': 9}
    assert report['new_model_requests'] == 0 and not report['promotion_allowed']
    assert report['post_hoc'] and report['model_quality_improvement'] is None
    assert report['fresh_holdout_cases'] == 0


@pytest.mark.parametrize('filename', ['plans.json', 'responses.json'])
def test_fixture_drift_fails_before_replay(tmp_path, monkeypatch, filename):
    fixtures = tmp_path / 'fixtures'
    shutil.copytree(replay_module.FIXTURES, fixtures)
    with (fixtures / filename).open('a', encoding='utf-8') as f:
        f.write('\n')
    monkeypatch.setattr(replay_module, 'FIXTURES', fixtures)
    with pytest.raises(ValueError, match='Frozen fixture changed'):
        replay_module.replay()


def test_cli_works_from_other_directory_and_never_overwrites(tmp_path):
    output = tmp_path / 'result.json'
    command = [sys.executable, '-X', 'utf8', str(SCRIPT), '--output', str(output)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    first = output.read_bytes()
    assert json.loads(first)['records'] == 12
    again = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
    assert again.returncode != 0 and 'FileExistsError' in again.stderr
    assert output.read_bytes() == first
