import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def verifier():
    location = ROOT / 'scripts' / 'verify_sources.py'
    assert location.is_file(), 'T00 source verification implementation missing'
    spec = importlib.util.spec_from_file_location('verify_sources', location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_manifest


def manifest(tmp_path, overrides=None):
    sources = [dict(id=f'G{i:02}', repo=f'https://github.com/example/g{i}',
                    status='candidate', adoption='reference_only', included_in_runtime=False,
                    commit=None, release=None, files=[], license_expression='MIT',
                    license_text_sha256=None, dependency_review='pending',
                    model_license_review='not_applicable', verified_at=None,
                    approved_by=None, approved_scope=[], known_limits=[])
               for i in range(1, 14)]
    for source in sources:
        if source['id'] in (overrides or {}):
            source.update(overrides[source['id']])
    path = tmp_path / 'sources' / 'upstream.lock.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'schema_version': '2.0', 'sources': sources}), encoding='utf-8')
    return path


def test_release_rejects_missing_commit(tmp_path):
    path = manifest(tmp_path, {'G04': {'included_in_runtime': True, 'adoption': 'runtime_dependency'}})
    result = verifier()(path, 'release')
    assert result.ok is False
    assert any('SOURCE_UNLOCKED:G04' in e for e in result.errors)


def test_reference_only_not_dependency(tmp_path):
    result = verifier()(manifest(tmp_path), 'release')
    assert result.ok is True
    assert result.checked_sources == 13


def test_license_gate(tmp_path):
    forbidden = '独立测试限制文本 不构成原包A内容 只测试许可扫描'
    fingerprint = hashlib.sha256(forbidden.encode()).hexdigest()
    runtime = tmp_path / 'prompts'
    runtime.mkdir()
    (runtime / 'renamed.md').write_text('prefix\n' + forbidden + '\nsuffix', encoding='utf-8')
    path = manifest(tmp_path, {'G11': {'license_expression': 'AGPL-3.0',
                                     'restricted_content_fingerprints': [fingerprint],
                                     'fingerprint_window': len(forbidden)}})
    result = verifier()(path, 'development')
    assert result.ok is False
    assert any('LICENSE_BLOCKED:G11' in e for e in result.errors)


def test_local_file_tampering_is_rejected(tmp_path):
    target = tmp_path / 'sources' / 'evidence.txt'
    path = manifest(tmp_path, {'G06': {'files': [{'path': 'LICENSE', 'sha256': 'a' * 64,
                                                  'usage': 'text', 'local_target': 'sources/evidence.txt'}]}})
    target.write_text('changed', encoding='utf-8')
    result = verifier()(path, 'development')
    assert result.ok is False
    assert any('FILE_HASH_MISMATCH:G06' in e for e in result.errors)


@pytest.mark.parametrize('commit', ['main', 'latest', '0123', 'x' * 40])
def test_release_rejects_mutable_or_fake_ref(tmp_path, commit):
    result = verifier()(manifest(tmp_path, {'G08': {'included_in_runtime': True, 'commit': commit}}), 'release')
    assert not result.ok
    assert any('SOURCE_UNLOCKED:G08' in e for e in result.errors)


def test_manifest_missing_source_fails(tmp_path):
    path = manifest(tmp_path)
    payload = json.loads(path.read_text())
    payload['sources'].pop()
    path.write_text(json.dumps(payload))
    result = verifier()(path, 'development')
    assert not result.ok
    assert any('SOURCE_SET_INCOMPLETE' in e for e in result.errors)


def test_evidence_path_escape_rejected(tmp_path):
    path = manifest(tmp_path, {'G06': {'files': [{'path': 'LICENSE', 'sha256': 'a' * 64,
                                                  'usage': 'text', 'local_target': '../outside.txt'}]}})
    result = verifier()(path, 'development')
    assert not result.ok
    assert any('EVIDENCE_PATH_INVALID:G06' in e for e in result.errors)


def test_adopted_source_requires_license_and_approval(tmp_path):
    path = manifest(tmp_path, {'G06': {'commit': 'a' * 40, 'included_in_runtime': True}})
    result = verifier()(path, 'release')
    assert not result.ok
    assert any('LICENSE_EVIDENCE_MISSING:G06' in e for e in result.errors)
    assert any('PRODUCTION_APPROVAL_MISSING:G06' in e for e in result.errors)


def test_bad_json_returns_result(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{')
    result = verifier()(path, 'development')
    assert not result.ok
    assert any('MANIFEST_INVALID' in e for e in result.errors)


def test_restricted_fingerprint_file_is_loaded(tmp_path):
    forbidden = 'This isolated synthetic licensing text belongs only to this test.'
    payload = {'sha256_windows': [hashlib.sha256(forbidden.encode()).hexdigest()],
               'window_characters': len(forbidden)}
    path = manifest(tmp_path, {'G11': {'restricted_fingerprint_file': 'sources/restricted.json'}})
    evidence = path.parent / 'restricted.json'
    evidence.write_text(json.dumps(payload))
    data = json.loads(path.read_text())
    data['sources'][10]['restricted_fingerprint_sha256'] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    path.write_text(json.dumps(data))
    runtime = tmp_path / 'src'
    runtime.mkdir()
    (runtime / 'paste.txt').write_text(forbidden)
    result = verifier()(path, 'development')
    assert not result.ok
    assert any('LICENSE_BLOCKED:G11' in e for e in result.errors)


def test_fingerprint_evidence_tampering_fails_closed(tmp_path):
    path = manifest(tmp_path, {'G11': {'restricted_fingerprint_file': 'sources/restricted.json',
                                     'restricted_fingerprint_sha256': 'a' * 64}})
    (path.parent / 'restricted.json').write_text('{}')
    result = verifier()(path, 'development')
    assert not result.ok
    assert any('LICENSE_SCAN_FAILED:G11' in e for e in result.errors)


def test_runtime_target_cannot_hide_behind_reference_flag(tmp_path):
    code = tmp_path / 'src'
    code.mkdir()
    target = code / 'copied.py'
    target.write_text('x = 1')
    path = manifest(tmp_path, {'G04': {'files': [{'path': 'upstream.py',
                                                 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                                 'usage': 'code', 'local_target': 'src/copied.py'}]}})
    result = verifier()(path, 'release')
    assert not result.ok
    assert any('ADOPTION_CONFLICT:G04' in e for e in result.errors)


@pytest.mark.parametrize('target_name', ['./src/copied.py', 'sources/../src/copied.py'])
def test_equivalent_runtime_paths_cannot_hide(tmp_path, target_name):
    code = tmp_path / 'src'
    code.mkdir()
    target = code / 'copied.py'
    target.write_text('x = 1')
    path = manifest(tmp_path, {'G04': {'files': [{'path': 'upstream.py',
                                                 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                                                 'usage': 'code', 'local_target': target_name}]}})
    result = verifier()(path, 'release')
    assert not result.ok
    assert any('ADOPTION_CONFLICT:G04' in e for e in result.errors)


def test_runtime_adoption_requires_inclusion_flag(tmp_path):
    path = manifest(tmp_path, {'G04': {'adoption': 'runtime_dependency'}})
    result = verifier()(path, 'release')
    assert not result.ok
    assert any('ADOPTION_CONFLICT:G04' in e for e in result.errors)


@pytest.mark.parametrize('mode', ['development', 'release'])
def test_production_status_cannot_bypass_lock_with_false_inclusion(tmp_path, mode):
    path = manifest(tmp_path, {'G04': {'status': 'production_approved'}})
    result = verifier()(path, mode)
    assert not result.ok
    assert any('SOURCE_UNLOCKED:G04' in e for e in result.errors)


@pytest.mark.parametrize('field', ['usage', 'license_text_sha256', 'dependency_review'])
def test_malformed_record_fields_fail_closed(tmp_path, field):
    path = manifest(tmp_path, {'G04': {'included_in_runtime': True,
                                     'adoption': 'runtime_dependency', field: []}})
    if field == 'usage':
        data = json.loads(path.read_text())
        data['sources'][3]['files'] = [{'path': 'LICENSE', 'sha256': 'a' * 64,
                                       'usage': [], 'local_target': 'sources/missing.txt'}]
        path.write_text(json.dumps(data))
    result = verifier()(path, 'release')
    assert not result.ok


def test_malformed_status_returns_failure_instead_of_crashing(tmp_path):
    result = verifier()(manifest(tmp_path, {'G04': {'status': []}}), 'development')
    assert not result.ok
    assert any('SOURCE_STATUS_INVALID:G04' in e for e in result.errors)


def test_g11_file_hashes_detect_renamed_copy_without_extra_fingerprints(tmp_path):
    text = 'synthetic restricted material, unrelated to real A package'
    path = manifest(tmp_path, {'G11': {'files': [{'path': 'SKILL.md',
                                                  'sha256': hashlib.sha256(text.encode()).hexdigest(),
                                                  'usage': 'text', 'local_target': 'sources/skill.txt'}]}})
    (path.parent / 'skill.txt').write_text(text)
    (tmp_path / 'prompts').mkdir()
    (tmp_path / 'prompts' / 'renamed.txt').write_text(text)
    result = verifier()(path, 'development')
    assert not result.ok
    assert any('LICENSE_BLOCKED:G11' in e for e in result.errors)


def test_code_hash_is_not_license_evidence(tmp_path):
    path = manifest(tmp_path)
    code = path.parent / 'code.py'
    code.write_text('x = 1')
    payload = json.loads(path.read_text())
    payload['sources'][3].update(status='production_approved', included_in_runtime=True,
                                adoption='runtime_dependency', commit='a' * 40,
                                approved_by='synthetic-reviewer', approved_at='2026-10-02T00:00:00Z',
                                approved_scope=['test'], dependency_review='reviewed',
                                license_text_sha256=hashlib.sha256(code.read_bytes()).hexdigest(),
                                files=[{'path': 'code.py', 'sha256': hashlib.sha256(code.read_bytes()).hexdigest(),
                                        'usage': 'code', 'local_target': 'sources/code.py'}])
    path.write_text(json.dumps(payload))
    result = verifier()(path, 'release')
    assert not result.ok
    assert any('LICENSE_EVIDENCE_MISSING:G04' in e for e in result.errors)


@pytest.mark.parametrize('element', [None, 'invalid-file-record'])
def test_g11_invalid_file_elements_do_not_crash_license_scan(tmp_path, element):
    result = verifier()(manifest(tmp_path, {'G11': {'files': [element]}}), 'development')
    assert not result.ok
    assert any('FILES_INVALID:G11' in e for e in result.errors)


@pytest.mark.parametrize('mode', ['development', 'release'])
@pytest.mark.parametrize('plugin_path', [
    'plugins/synthetic/skills/probe/SKILL.md',
    'plugins/synthetic/prompts/review.md',
    'plugins/synthetic/server.py',
    'plugins/synthetic/.codex-plugin/plugin.json',
    'plugins/synthetic/.mcp.json',
    'plugins/synthetic/runtime-binding.json',
])
def test_g11_plugin_delivery_rejects_restricted_copy(tmp_path, mode, plugin_path):
    restricted = b'Independent F13 synthetic restricted bytes; no upstream material.'
    for relative_path in ('src/probe.txt', plugin_path):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(restricted)
    path = manifest(tmp_path, {'G11': {
        'restricted_file_sha256': [hashlib.sha256(restricted).hexdigest()],
    }})

    result = verifier()(path, mode)

    assert not result.ok
    assert set(result.errors) == {
        'LICENSE_BLOCKED:G11:src/probe.txt',
        f'LICENSE_BLOCKED:G11:{plugin_path}',
    }


@pytest.mark.parametrize('mode', ['development', 'release'])
def test_g11_isolated_source_evidence_is_not_runtime(tmp_path, mode):
    restricted = b'Independent F13 quarantined evidence; no upstream material.'
    path = manifest(tmp_path, {'G11': {'files': [{
        'path': 'SKILL.md', 'sha256': hashlib.sha256(restricted).hexdigest(),
        'usage': 'text', 'local_target': 'sources/evidence/G11/SKILL.md',
    }]}})
    evidence = path.parent / 'evidence' / 'G11' / 'SKILL.md'
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(restricted)

    result = verifier()(path, mode)

    assert result.ok
    assert result.errors == []


@pytest.mark.parametrize('mode', ['development', 'release'])
def test_plugin_runtime_target_cannot_hide_behind_reference_flag(tmp_path, mode):
    target = tmp_path / 'plugins' / 'synthetic' / 'server.py'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'pass  # Independent F13 synthetic plugin implementation\n')
    path = manifest(tmp_path, {'G04': {'files': [{
        'path': 'upstream.py', 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'usage': 'code', 'local_target': 'plugins/synthetic/server.py',
    }]}})

    result = verifier()(path, mode)

    assert not result.ok
    assert 'ADOPTION_CONFLICT:G04:runtime_target_marked_excluded' in result.errors
