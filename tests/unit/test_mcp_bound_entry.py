"""A3 source entry: bindings must be verified before importing the MCP server."""

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / 'src/cn_contract/mcp/bound_entry.py'
BINDING = 'plugins/qx-contract-offline-codex/runtime-binding.json'
CANARY = 'PRIVATE_PATH_OR_CONTENT_CANARY'


def api():
    assert ENTRY.is_file(), 'the source binding entry is not implemented'
    name = '_qx_bound_entry_test'
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ENTRY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def put(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else value.encode('utf-8'))
    return path


def jput(root, relative, value):
    return put(root, relative, json.dumps(value, ensure_ascii=False))


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'fictional-source'
    root.mkdir()
    for path in ('src/cn_contract/__init__.py', 'src/cn_contract/domain.py',
                 'src/cn_contract/mcp/__init__.py',
                 'src/cn_contract/mcp/offline_server.py',
                 'src/cn_contract/mcp/bound_entry.py',
                 'src/cn_contract/web/static/ui.js',
                 'src/cn_contract/web/static/ui.css',
                 'src/cn_contract/web/templates/ui.html'):
        put(root, path, b'# independently fictional byte input\n')
    put(root, '.venv/Scripts/python.exe', b'fictional interpreter metadata')
    put(root, 'pyproject.toml', '[project]\nname="qx-contract-workbench"\nversion="0.1.0"\n')
    put(root, 'requirements.lock', b'fictional runtime lock bytes')
    put(root, 'requirements-build.lock', b'fictional build lock bytes')
    jput(root, 'config/defaults.json', {'model_provider_default': 'mock',
                                     'qcc_enabled_default': False})
    jput(root, 'sources/runtime-dependencies.lock.json', {
        'target': {'python_full_version': '3.12.14'},
        'packages': [{'name': 'mcp', 'version': '2.2.0'}],
        'build_packages': [{'name': 'setuptools', 'version': '84.0.0'}]})
    for name in ('sales_basic.docx', 'service_basic.docx', 'lease_basic.docx',
                 'nda_basic.docx', 'provenance.json'):
        put(root, 'tests/fixtures/synthetic/' + name, b'fictional fixed fixture')
    jput(root, 'plugins/qx-contract-offline-codex/.mcp.json', {
        'mcpServers': {'qx-contract-offline': {
            'command': (root / '.venv/Scripts/python.exe').as_posix(),
            'args': ['-I', '-X', 'utf8',
                     (root / 'src/cn_contract/mcp/bound_entry.py').as_posix()],
            'cwd': root.as_posix(), 'enabled': True}}})
    jput(root, 'plugins/qx-contract-offline-codex/.codex-plugin/plugin.json', {
        'name': 'qx-contract-offline-codex', 'version': '0.1.3',
        'mcpServers': './.mcp.json'})
    return root


def fixture_payload(root):
    files = {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file() and (
                 p.relative_to(root).parts[0] == 'src'
                 or p.relative_to(root).as_posix() in {
                     'config/defaults.json', 'pyproject.toml', 'requirements.lock',
                     'requirements-build.lock', 'sources/runtime-dependencies.lock.json',
                     'plugins/qx-contract-offline-codex/.mcp.json',
                     'plugins/qx-contract-offline-codex/.codex-plugin/plugin.json'}
                 or p.relative_to(root).as_posix().startswith('tests/fixtures/synthetic/'))}
    payload = {
        'format_version': 2, 'scope': 'LOCAL_CODEX_SOURCE_RUNTIME_STARTUP_BINDING',
        'adapter_version': '0.1.3', 'repository_root': root.as_posix(),
        'entry_file': 'src/cn_contract/mcp/bound_entry.py',
        'offline_module': 'cn_contract.mcp.offline_server',
        'offline_file': 'src/cn_contract/mcp/offline_server.py',
        'python_version': '3.12.14',
        'installed_versions': {'mcp': '2.2.0', 'setuptools': '84.0.0',
                               'qx-contract-workbench': '0.1.0'},
        'runtime_bundled': False, 'startup_hashes_enforced': True,
        'hash_scope': 'SOURCE_FILES_AND_SELECTED_LOCKS_NOT_DEPENDENCY_BYTES_OR_OS_ATTESTATION',
        'repository_file_hashes': dict(sorted(files.items())),
        'expected_tools': ['workbench_status', 'deepseek_offline_example'],
        'real_models_enabled': False, 'qcc_enabled': False,
        'host_installation': 'NOT_RUN', 'chatgpt_connection': 'NOT_RUN',
        'production': 'BLOCKED'}
    digest = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode('utf-8')).hexdigest()
    payload['build_id'] = 'qx-offline-source-0.1.3-' + digest[:32]
    return payload


def verify(root, payload=None, **context_changes):
    module = api()
    jput(root, BINDING, payload or fixture_payload(root))
    context = {'python_version': '3.12.14',
               'installed_versions': {'mcp': '2.2.0', 'setuptools': '84.0.0',
                                      'qx-contract-workbench': '0.1.0'},
               'python_executable': root / '.venv/Scripts/python.exe',
               'entry_file': root / 'src/cn_contract/mcp/bound_entry.py'}
    context.update(context_changes)
    return module.verify_runtime_binding(root, context=module.RuntimeContext(**context))


def test_verified_fictional_binding_has_no_business_or_sdk_import(repository):
    before = set(sys.modules)
    result = verify(repository)
    assert result.build_id == fixture_payload(repository)['build_id']
    assert result.file_count == 20
    assert result.dependency_count == 3
    assert not any(name == 'mcp' or name.startswith('mcp.')
                   or name == 'cn_contract' or name.startswith('cn_contract.')
                   for name in set(sys.modules) - before)


@pytest.mark.parametrize('relative', [
    'src/cn_contract/domain.py', 'src/cn_contract/mcp/offline_server.py',
    'src/cn_contract/mcp/bound_entry.py', 'src/cn_contract/web/static/ui.js',
    'src/cn_contract/web/static/ui.css', 'src/cn_contract/web/templates/ui.html',
    'config/defaults.json', 'requirements.lock', 'requirements-build.lock',
    'tests/fixtures/synthetic/sales_basic.docx',
    'plugins/qx-contract-offline-codex/.mcp.json'])
def test_changed_bound_file_is_rejected(repository, relative):
    payload = fixture_payload(repository)
    put(repository, relative, CANARY)
    with pytest.raises(api().BindingRejected):
        verify(repository, payload)


@pytest.mark.parametrize('relative', [
    'src/cn_contract/untracked.py', 'src/cn_contract/nested/hidden.js',
    'src/cn_contract/.hidden.css', 'src/cn_contract/new.html',
    'src/cn_contract/UPPER.PY'])
def test_new_untracked_runtime_source_cannot_escape_old_inventory(repository, relative):
    payload = fixture_payload(repository)
    put(repository, relative, CANARY)
    with pytest.raises(api().BindingRejected):
        verify(repository, payload)


@pytest.mark.parametrize('mutation', [
    'missing', 'extra', 'escape', 'backslash', 'absolute', 'hash_upper',
    'hash_bad', 'format', 'root', 'entry', 'offline_module', 'extra_key',
    'live_model', 'live_qcc', 'tools', 'false_enforcement', 'build_canary',
    'binding_version', 'build_label', 'dependency_missing', 'dependency_extra',
    'dependency_mismatch', 'python', 'bool_format'])
def test_binding_shape_and_policy_mismatch_are_rejected(repository, mutation):
    payload = fixture_payload(repository)
    hashes = payload['repository_file_hashes']
    if mutation == 'missing': del hashes['src/cn_contract/domain.py']
    elif mutation == 'extra': hashes['not-runtime.txt'] = '0' * 64
    elif mutation == 'escape': hashes['../' + CANARY] = '0' * 64
    elif mutation == 'backslash': hashes['src\\cn_contract\\domain.py'] = '0' * 64
    elif mutation == 'absolute': hashes[repository.as_posix() + '/src/cn_contract/domain.py'] = '0' * 64
    elif mutation == 'hash_upper': hashes['src/cn_contract/domain.py'] = 'A' * 64
    elif mutation == 'hash_bad': hashes['src/cn_contract/domain.py'] = CANARY
    elif mutation == 'format': payload['format_version'] = 1
    elif mutation == 'root': payload['repository_root'] = repository.parent.as_posix()
    elif mutation == 'entry': payload['entry_file'] = 'src/cn_contract/mcp/offline_server.py'
    elif mutation == 'offline_module': payload['offline_module'] = CANARY
    elif mutation == 'extra_key': payload[CANARY] = True
    elif mutation == 'live_model': payload['real_models_enabled'] = True
    elif mutation == 'live_qcc': payload['qcc_enabled'] = True
    elif mutation == 'tools': payload['expected_tools'].append(CANARY)
    elif mutation == 'false_enforcement': payload['startup_hashes_enforced'] = False
    elif mutation == 'build_canary': payload['build_id'] = CANARY + '\n'
    elif mutation == 'build_label': payload['build_id'] = 'qx-offline-source-0.1.3-arbitrary-label'
    elif mutation == 'binding_version': payload['adapter_version'] = '0.1.2'
    elif mutation == 'dependency_missing': del payload['installed_versions']['mcp']
    elif mutation == 'dependency_extra': payload['installed_versions'][CANARY] = '1.0'
    elif mutation == 'dependency_mismatch': payload['installed_versions']['mcp'] = '2.3.0'
    elif mutation == 'python': payload['python_version'] = '3.13.0'
    elif mutation == 'bool_format': payload['format_version'] = True
    with pytest.raises(api().BindingRejected):
        verify(repository, payload)


@pytest.mark.parametrize('context_changes', [
    {'python_version': '3.13.0'},
    {'installed_versions': {'mcp': '2.3.0', 'setuptools': '84.0.0',
                            'qx-contract-workbench': '0.1.0'}},
    {'entry_file': Path('relative.py')},
    {'python_executable': Path('other-python.exe')}])
def test_actual_runtime_context_must_match(repository, context_changes):
    with pytest.raises(api().BindingRejected):
        verify(repository, **context_changes)


@pytest.mark.parametrize('section', ['packages', 'build_packages'])
def test_project_distribution_cannot_self_reference_in_dependency_lock(repository, section):
    lock_path = 'sources/runtime-dependencies.lock.json'
    original = (repository / lock_path).read_text(encoding='utf-8')
    for version in ('9.9.9', '0.1.0'):
        lock = json.loads(original)
        lock[section].append({'name': 'qx-contract-workbench', 'version': version})
        jput(repository, lock_path, lock)
        # Rebind all actual source bytes and the payload identifier. The context
        # still has the project distribution at 0.1.0, so overwrite would pass.
        with pytest.raises(api().BindingRejected):
            verify(repository)
        with pytest.raises(api().BindingRejected):
            api().build_binding_snapshot(repository)


@pytest.mark.parametrize('key,value', [
    ('model_provider_default', 'deepseek'), ('qcc_enabled_default', True),
    ('qcc_enabled_default', 0)])
def test_rebinding_enabled_defaults_does_not_bypass_offline_policy(repository, key, value):
    defaults = {'model_provider_default': 'mock', 'qcc_enabled_default': False}
    defaults[key] = value
    jput(repository, 'config/defaults.json', defaults)
    with pytest.raises(api().BindingRejected):
        verify(repository)


def test_duplicate_binding_key_is_rejected(repository):
    module = api()
    path = put(repository, BINDING,
               '{"format_version":2,"format_version":2,"' + CANARY + '":true}')
    with pytest.raises(module.BindingRejected):
        module.verify_runtime_binding(repository)
    assert path.is_file()


def test_oversized_binding_is_rejected_without_content_reflection(repository):
    module = api()
    put(repository, BINDING, CANARY * (module.MAX_BINDING_BYTES // len(CANARY) + 1))
    with pytest.raises(module.BindingRejected) as caught:
        module.verify_runtime_binding(repository)
    assert str(caught.value) == 'BOUND_ENTRY_REJECTED'


def test_bound_hardlink_is_rejected(repository, tmp_path):
    target = repository / 'src/cn_contract/domain.py'
    os.link(target, tmp_path / 'linked-copy.py')
    with pytest.raises(api().BindingRejected):
        verify(repository)


def test_source_symlink_and_directory_link_are_rejected(repository, tmp_path):
    outside = put(tmp_path, 'outside.py', CANARY)
    path = repository / 'src/cn_contract/new.py'
    try:
        path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f'local symlink creation unavailable: {exc.winerror}')
    with pytest.raises(api().BindingRejected):
        verify(repository)
    path.unlink()
    linked = repository / 'src/cn_contract/linked'
    linked.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(api().BindingRejected):
        verify(repository)


def test_snapshot_capture_includes_new_source_and_ignores_only_nonruntime_bytes(repository):
    module = api()
    put(repository, 'src/cn_contract/new.py', b'# new runtime')
    put(repository, 'src/cn_contract/__pycache__/cache.pyc', b'not source')
    put(repository, 'docs/other.md', b'not runtime')
    inventory = module.inventory_repository_files(repository)
    assert 'src/cn_contract/new.py' in inventory
    assert not any(path.endswith('.pyc') for path in inventory)
    assert 'docs/other.md' not in inventory


def test_capture_is_deterministic_read_only_and_covers_added_source(repository, monkeypatch):
    module = api()
    monkeypatch.setattr(module, '_actual_context', lambda versions: module.RuntimeContext(
        python_version='3.12.14', installed_versions=versions,
        python_executable=repository / '.venv/Scripts/python.exe',
        entry_file=repository / 'src/cn_contract/mcp/bound_entry.py'))
    first = module.build_binding_snapshot(repository)
    assert first == fixture_payload(repository)
    assert first == module.build_binding_snapshot(repository)
    assert not (repository / BINDING).exists()
    first['expected_tools'].append('not-an-enabled-tool')
    assert module.build_binding_snapshot(repository)['expected_tools'] == [
        'workbench_status', 'deepseek_offline_example']
    put(repository, 'src/cn_contract/extra.py', '# extra runtime source')
    second = module.build_binding_snapshot(repository)
    assert second['build_id'] != first['build_id']
    assert 'src/cn_contract/extra.py' in second['repository_file_hashes']
    assert verify(repository, second).build_id == second['build_id']


def test_check_only_outputs_fixed_safe_status_without_importing_tools(monkeypatch, capsys):
    module = api()
    result = module.BindingVerification('qx-offline-source-0.1.3-' + '0' * 32, 20, 3)
    monkeypatch.setattr(module, 'verify_runtime_binding', lambda root: result)
    monkeypatch.setattr(module, 'import_module', lambda name: pytest.fail('check must not import tools'))
    assert module.main(['--check']) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'status': 'BOUND_ENTRY_VERIFIED', 'build_id': result.build_id}
    assert captured.err == ''


def test_guard_succeeds_before_import_and_stdio_has_no_startup_stdout(monkeypatch, capsys):
    module = api()
    sequence = []
    result = module.BindingVerification('qx-offline-source-0.1.3-' + '0' * 32, 20, 3)
    def check(root):
        assert root == ROOT
        sequence.append('verified')
        return result
    class FakeServer:
        __file__ = str(ROOT / 'src/cn_contract/mcp/offline_server.py')
        @staticmethod
        def main():
            sequence.append('tools-started')
    def load(name):
        assert sequence == ['verified']
        assert name == 'cn_contract.mcp.offline_server'
        assert sys.path[0] == str(ROOT / 'src')
        sequence.append('imported')
        return FakeServer
    monkeypatch.setattr(module, 'verify_runtime_binding', check)
    monkeypatch.setattr(module, 'import_module', load)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    assert module.main([]) == 0
    assert sequence == ['verified', 'imported', 'tools-started']
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


@pytest.mark.parametrize('arguments', [[], ['--check'], [CANARY]])
def test_direct_cli_mismatch_never_imports_business_or_reflects_paths(repository, arguments):
    api()
    shutil.copyfile(ENTRY, repository / 'src/cn_contract/mcp/bound_entry.py')
    marker = repository / 'business-imported.txt'
    put(repository, 'src/cn_contract/__init__.py',
        'from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("imported")\n')
    put(repository, 'src/cn_contract/mcp/offline_server.py',
        'raise RuntimeError(' + repr(CANARY) + ')\n')
    jput(repository, BINDING, {'format_version': 1, 'private': CANARY})
    completed = subprocess.run([sys.executable, '-I', '-X', 'utf8',
        str(repository / 'src/cn_contract/mcp/bound_entry.py'), *arguments],
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert completed.returncode == 78
    assert not marker.exists()
    assert completed.stdout == ''
    assert completed.stderr == 'BOUND_ENTRY_REJECTED\n'
    assert CANARY not in completed.stdout + completed.stderr
    assert str(repository) not in completed.stdout + completed.stderr


@pytest.mark.parametrize('arguments', [[], ['--check']])
def test_rejected_subprocess_never_attempts_business_or_sdk_import(repository, arguments):
    api()
    guard = repository / 'src/cn_contract/mcp/bound_entry.py'
    shutil.copyfile(ENTRY, guard)
    jput(repository, BINDING, {'format_version': 1})
    marker = repository / 'forbidden-import.txt'
    runner = put(repository, 'import-sentinel.py', (
        'import importlib.abc, runpy, sys\n'
        'from pathlib import Path\n'
        'class ImportSentinel(importlib.abc.MetaPathFinder):\n'
        '    def find_spec(self, fullname, path=None, target=None):\n'
        '        if fullname.split(".")[0] in ("cn_contract", "mcp", "mcp_types"):\n'
        '            Path(' + repr(str(marker)) + ').write_text(fullname)\n'
        '            raise RuntimeError("forbidden business or SDK import")\n'
        'sys.meta_path.insert(0, ImportSentinel())\n'
        'sys.argv = [' + repr(str(guard)) + ', *sys.argv[1:]]\n'
        'runpy.run_path(' + repr(str(guard)) + ', run_name="__main__")\n'))
    completed = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(runner), *arguments],
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert completed.returncode == 78
    assert not marker.exists()
    assert completed.stdout == ''
    assert completed.stderr == 'BOUND_ENTRY_REJECTED\n'


def test_actual_current_source_cli_matches_its_binding_verification():
    module = api()
    try:
        expected = module.verify_runtime_binding(ROOT)
    except module.BindingRejected:
        expected = None
    completed = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(ENTRY), '--check'],
                               capture_output=True, text=True, encoding='utf-8', timeout=15)
    if expected is None:
        assert completed.returncode == 78
        assert completed.stdout == ''
        assert completed.stderr == 'BOUND_ENTRY_REJECTED\n'
    else:
        assert completed.returncode == 0
        assert json.loads(completed.stdout) == {
            'status': 'BOUND_ENTRY_VERIFIED', 'build_id': expected.build_id}
        assert completed.stderr == ''
