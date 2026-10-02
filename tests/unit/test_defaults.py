import importlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
HASH = '0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887'


def config_module():
    assert (ROOT / 'src/cn_contract/config.py').is_file(), 'T01 config implementation missing'
    return importlib.import_module('cn_contract.config')


def test_defaults():
    settings = config_module().load_settings(ROOT / 'config/defaults.json')
    assert settings.qcc_enabled_default is False
    assert settings.qcc_case_budget_credits == Decimal('20')
    assert settings.qcc_max_calls == 6
    assert settings.qcc_default_pages_per_tool == 1
    assert settings.qcc_paid_auto_retries == 0
    assert settings.config_sha256 == HASH
    assert settings.model_provider_default == 'mock'


def test_no_silent_scope_or_model_expansion(tmp_path):
    module = config_module()
    payload = json.loads((ROOT / 'config/defaults.json').read_text())
    for field, value in [('qcc_enabled_default', True), ('model_provider_default', 'real'),
                         ('full_review_types', ['sales', 'service', 'lease', 'nda', 'labor']),
                         ('qcc_paid_auto_retries', 1), ('production_autosend', True)]:
        changed = dict(payload, **{field: value})
        location = tmp_path / 'defaults.json'
        location.write_text(json.dumps(changed))
        with pytest.raises(ValidationError):
            module.load_settings(location)


def test_config_hash_ignores_format_and_key_order(tmp_path):
    module = config_module()
    payload = json.loads((ROOT / 'config/defaults.json').read_text())
    location = tmp_path / 'same.json'
    location.write_text(json.dumps(dict(reversed(list(payload.items()))), indent=8))
    assert module.load_settings(location).config_sha256 == HASH


def test_config_change_has_new_hash(tmp_path):
    module = config_module()
    payload = json.loads((ROOT / 'config/defaults.json').read_text())
    payload['qcc_case_budget_credits'] = 10
    location = tmp_path / 'changed.json'
    location.write_text(json.dumps(payload))
    settings = module.load_settings(location)
    assert settings.qcc_case_budget_credits == Decimal('10')
    assert settings.config_sha256 != HASH


@pytest.mark.parametrize('field,value', [('upload_max_file_mib', -1), ('qcc_max_calls', 0),
                                        ('archive_max_ratio', 0), ('unknown', True)])
def test_invalid_config_rejected(tmp_path, field, value):
    module = config_module()
    payload = json.loads((ROOT / 'config/defaults.json').read_text())
    payload[field] = value
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError):
        module.load_settings(path)


def test_duplicate_json_key_rejected(tmp_path):
    module = config_module()
    path = tmp_path / 'duplicate.json'
    path.write_text('{"qcc_enabled_default":false,"qcc_enabled_default":true}')
    with pytest.raises(ValueError, match='DUPLICATE_CONFIG_KEY'):
        module.load_settings(path)


def test_config_frozen():
    settings = config_module().load_settings(ROOT / 'config/defaults.json')
    with pytest.raises(ValidationError):
        settings.qcc_max_calls = 100
