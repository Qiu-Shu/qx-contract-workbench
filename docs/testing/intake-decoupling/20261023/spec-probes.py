"""Independent CH-00A3 checks against fixed baseline; all HTTP data synthetic."""
import ast
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.integration.test_api import api, sign_in
from tests.integration.test_intake import create, conversion

BASE = '1a73e36f687b6dc0eab98892149737c02e8d9ce6'
ROOT = Path(__file__).resolve().parents[2]


def baseline(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT).decode('utf-8')


def function(source, name):
    return next(item for item in ast.parse(source).body
                if isinstance(item, ast.FunctionDef) and item.name == name)


def test_create_matter_body_preserved_except_relative_import_depth():
    old = function(baseline('src/cn_contract/web/services.py'), 'create_matter')
    new = function((ROOT / 'src/cn_contract/matters.py').read_text('utf-8'), 'create_matter')
    for item in ast.walk(old):
        if isinstance(item, ast.ImportFrom):
            assert item.level == 2
            item.level = 1
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
    for path in ('src/cn_contract/domain.py', 'src/cn_contract/storage_schema.py',
                 'src/cn_contract/intake/schema.py', 'src/cn_contract/schema_migrations.py'):
        assert (ROOT / path).read_bytes() == subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)


def test_record_bytes_errors_and_utc_match_baseline():
    from cn_contract import record_codec
    source = baseline('src/cn_contract/web/storage.py')
    module = ast.Module(body=[function(source, name) for name in ('now', 'encode', 'sha')], type_ignores=[])
    previous = {'datetime': datetime, 'timezone': timezone, 'json': json, 'hashlib': hashlib}
    exec(compile(module, '<baseline-codec>', 'exec'), previous)
    samples = [None, {'中文': '换行\n引号"', 'nested': [True, None, -0.0, 1.0, {'b': 2, 'a': 1}]},
               {'n': 10**80, 'emoji': '⚖️', 'empty': []}, ['a', {'x': (1, 2)}]]
    for value in samples:
        assert record_codec.encode(value).encode('utf-8') == previous['encode'](value).encode('utf-8')
        assert record_codec.sha(value) == previous['sha'](value)
    for value in (float('nan'), float('inf'), Decimal('1.25'), {1: 'a', '2': 'b'}):
        with pytest.raises(Exception) as before:
            previous['encode'](value)
        with pytest.raises(type(before.value)):
            record_codec.encode(value)
    lower = previous['now']()
    actual = record_codec.now()
    upper = previous['now']()
    assert actual.tzinfo is timezone.utc and lower <= actual <= upper


def test_legacy_aliases_share_actual_application_functions():
    from cn_contract import matters, record_codec
    from cn_contract.web import services, storage
    from cn_contract.intake import service
    assert services.create_matter is matters.create_matter
    assert service.matters is matters
    for name in ('now', 'encode', 'sha'):
        assert getattr(storage, name) is getattr(record_codec, name)
        assert getattr(service, name) is getattr(record_codec, name)


def test_conversion_failure_at_real_seam_rolls_back_all_rows_and_retry_succeeds(api, monkeypatch):
    from cn_contract import matters
    from cn_contract.security import ServiceError
    client, database, _, _ = api
    headers = sign_in(client)
    intake = create(client, headers)

    def counts(db):
        tables = [row[0] for row in db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))]
        return {table: db.scalar(text('SELECT COUNT(*) FROM "' + table + '"')) for table in tables}

    with database.session() as db:
        before = counts(db)
    original = matters.create_matter
    captured = []

    def fail(value, actor, db):
        result = original(value, actor, db)
        captured.append(str(result.id))
        assert db.scalar(text('SELECT COUNT(*) FROM matters')) == before['matters'] + 1
        raise ServiceError('STATE_CONFLICT', 409)

    monkeypatch.setattr(matters, 'create_matter', fail)
    response = client.post('/api/intakes/' + intake['id'] + '/convert', headers=headers, json=conversion())
    assert response.status_code == 409 and len(captured) == 1
    with database.session() as db:
        assert counts(db) == before
        assert db.scalar(text('SELECT matter_id FROM intake_cases WHERE id=:id'), {'id': intake['id']}) is None
    monkeypatch.setattr(matters, 'create_matter', original)
    retry = client.post('/api/intakes/' + intake['id'] + '/convert', headers=headers, json=conversion())
    assert retry.status_code == 200 and retry.json()['matter_id'] != captured[0]
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM matters')) == before['matters'] + 1
