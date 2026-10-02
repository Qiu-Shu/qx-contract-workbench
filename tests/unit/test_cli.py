import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONUTF8='1')
    return subprocess.run([sys.executable, '-m', 'cn_contract.cli', *args], cwd=ROOT,
                          env=env, capture_output=True, text=True, encoding='utf-8')


def test_help_is_available():
    result = run_cli('--help')
    assert result.returncode == 0, 'T01 CLI help implementation missing: ' + result.stderr
    assert 'config-validate' in result.stdout


def test_config_command_reports_actual_hash():
    result = run_cli('config-validate')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['config_sha256'] == '0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887'
    assert data['qcc_enabled'] is False
    assert data['model_provider'] == 'mock'


def test_invalid_file_returns_nonzero(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{"qcc_enabled_default":true}')
    result = run_cli('config-validate', '--path', str(path))
    assert result.returncode == 1
    assert 'CONFIG_INVALID' in result.stderr


def test_cli_does_not_pretend_review_is_implemented():
    result = run_cli('review', 'synthetic.docx')
    assert result.returncode != 0
    assert 'invalid choice' in result.stderr


def test_schema_check_detects_stale_file_without_overwriting(tmp_path):
    path = tmp_path / 'schema.json'
    path.write_text('{"outdated":true}')
    result = run_cli('schema', '--output', str(path), '--check')
    assert result.returncode == 1
    assert 'SCHEMA_OUT_OF_DATE' in result.stderr
    assert json.loads(path.read_text()) == {'outdated': True}


def test_checked_in_schema_matches_current_domain():
    result = run_cli('schema', '--check')
    assert result.returncode == 0, result.stderr


def run_defaults_script(path):
    return subprocess.run([sys.executable, str(ROOT / 'scripts/verify_defaults.py'), '--file', str(path)],
                          cwd=ROOT, capture_output=True, text=True, encoding='utf-8')


def test_verify_defaults_reads_the_requested_file(tmp_path):
    result = run_defaults_script(tmp_path / 'does-not-exist.json')
    assert result.returncode != 0
    assert 'CONFIG_INVALID' in result.stderr


def test_verify_defaults_rejects_invalid_requested_file(tmp_path):
    path = tmp_path / 'invalid.json'
    path.write_text('{')
    result = run_defaults_script(path)
    assert result.returncode != 0
    assert 'CONFIG_INVALID' in result.stderr


def test_verify_defaults_changed_file_is_not_baseline(tmp_path):
    data = json.loads((ROOT / 'config/defaults.json').read_text())
    data['qcc_case_budget_credits'] = 10
    path = tmp_path / 'changed.json'
    path.write_text(json.dumps(data))
    result = run_defaults_script(path)
    assert result.returncode != 0
    assert 'DEFAULTS_HASH_MISMATCH' in result.stderr
