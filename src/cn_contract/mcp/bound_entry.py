"""Check the project source binding before importing the finite offline MCP tools.

Invoke this file by its absolute path with the project interpreter's ``-I -X
utf8`` flags. Module execution would import ``cn_contract.__init__`` before this
check. This is a startup source check, not dependency-byte or OS attestation;
it cannot prevent source changes after the check or attest a host cache.
"""

from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module, metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import sys
import tomllib


MAX_BINDING_BYTES = 2 * 1024 * 1024
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_FILES = 2048
_BINDING_FILE = 'plugins/qx-contract-offline-codex/runtime-binding.json'
_ENTRY_FILE = 'src/cn_contract/mcp/bound_entry.py'
_OFFLINE_FILE = 'src/cn_contract/mcp/offline_server.py'
_OFFLINE_MODULE = 'cn_contract.mcp.offline_server'
_MCP_FILE = 'plugins/qx-contract-offline-codex/.mcp.json'
_PLUGIN_FILE = 'plugins/qx-contract-offline-codex/.codex-plugin/plugin.json'
_ADAPTER_VERSION = '0.1.4'
_SOURCE_EXTENSIONS = frozenset({'.py', '.js', '.mjs', '.css', '.html'})
_FIXED_FILES = frozenset({
    'config/defaults.json', 'pyproject.toml', 'requirements.lock',
    'requirements-build.lock', 'sources/runtime-dependencies.lock.json',
    'sources/pdfjs-assets.lock.json',
      'sources/ocr-assets.lock.json','sources/ocr-environment.lock.json','requirements-ocr-windows-py312.lock',
    'tests/fixtures/synthetic/sales_basic.docx',
    'tests/fixtures/synthetic/service_basic.docx',
    'tests/fixtures/synthetic/lease_basic.docx',
    'tests/fixtures/synthetic/nda_basic.docx',
    'tests/fixtures/synthetic/provenance.json', _MCP_FILE, _PLUGIN_FILE})
_BUILD_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
_VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9.!+_-]{0,63}\Z')
_CONSTANT_FIELDS = {
    'format_version': 2,
    'scope': 'LOCAL_CODEX_SOURCE_RUNTIME_STARTUP_BINDING',
    'adapter_version': _ADAPTER_VERSION,
    'entry_file': _ENTRY_FILE, 'offline_module': _OFFLINE_MODULE,
    'offline_file': _OFFLINE_FILE, 'runtime_bundled': False,
    'startup_hashes_enforced': True,
    'hash_scope': 'SOURCE_FILES_AND_SELECTED_LOCKS_NOT_DEPENDENCY_BYTES_OR_OS_ATTESTATION',
    'expected_tools': ['workbench_status', 'deepseek_offline_example', 'read_selected_case'],
    'real_models_enabled': False, 'qcc_enabled': False,
    'host_installation': 'NOT_RUN', 'chatgpt_connection': 'NOT_RUN',
    'production': 'BLOCKED'}
_VARIABLE_FIELDS = frozenset({'build_id', 'repository_root', 'python_version',
                            'installed_versions', 'repository_file_hashes'})


class BindingRejected(Exception):
    """A fixed non-reflecting startup error."""

    def __init__(self):
        super().__init__('BOUND_ENTRY_REJECTED')


@dataclass(frozen=True)
class RuntimeContext:
    """Technical test seam; the CLI always obtains its own runtime context."""

    python_version: str
    installed_versions: dict[str, str]
    python_executable: Path
    entry_file: Path


@dataclass(frozen=True)
class BindingVerification:
    build_id: str
    file_count: int
    dependency_count: int


def _reject() -> None:
    raise BindingRejected()


def _checked_path(path: Path, *, directory: bool = False) -> Path:
    """Check nominal ancestors before resolving; never follow a known link."""
    if not path.is_absolute():
        _reject()
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, 'st_file_attributes', 0)
                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            _reject()
        if item != path and not stat.S_ISDIR(info.st_mode):
            _reject()
    info = path.lstat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            _reject()
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _reject()
    if path.resolve(strict=True) != path:
        _reject()
    return path


def _root_path(root: Path) -> Path:
    if not isinstance(root, Path) or not root.is_absolute():
        _reject()
    return _checked_path(root, directory=True)


def _bytes(root: Path, relative: str, *, maximum: int = _MAX_FILE_BYTES) -> bytes:
    path = _checked_path(root / relative)
    if path.stat().st_size > maximum:
        _reject()
    with path.open('rb') as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        _reject()
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _json(root: Path, relative: str, *, maximum: int = _MAX_FILE_BYTES):
    return json.loads(_bytes(root, relative, maximum=maximum).decode('utf-8'),
                      object_pairs_hook=_unique_object,
                      parse_constant=lambda _: _reject())


def _inventory(root: Path) -> dict[str, str]:
    selected = set(_FIXED_FILES)
    source = _checked_path(root / 'src', directory=True)
    pending = [source]
    seen_entries = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                seen_entries += 1
                if seen_entries > _MAX_FILES * 4:
                    _reject()
                path = Path(entry.path)
                info = path.lstat()
                if (stat.S_ISLNK(info.st_mode)
                        or getattr(info, 'st_file_attributes', 0)
                        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                    _reject()
                if stat.S_ISDIR(info.st_mode):
                    _checked_path(path, directory=True)
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    if path.suffix.lower() in _SOURCE_EXTENSIONS:
                        selected.add(path.relative_to(root).as_posix())
                else:
                    _reject()
    if not {_ENTRY_FILE, _OFFLINE_FILE} <= selected or len(selected) > _MAX_FILES:
        _reject()
    return {relative: sha256(_bytes(root, relative)).hexdigest()
            for relative in sorted(selected)}


def inventory_repository_files(root: Path) -> dict[str, str]:
    """Capture all present runtime source extensions, including untracked files.

    This authoring helper does not write a binding or enable a host. Fixed
    metadata, locks and the original four offline fixtures are also included.
    """
    try:
        return _inventory(_root_path(root))
    except Exception:
        raise BindingRejected() from None


def _locked_versions(root: Path) -> tuple[str, dict[str, str]]:
    lock = _json(root, 'sources/runtime-dependencies.lock.json')
    if type(lock) is not dict or type(lock.get('target')) is not dict:
        _reject()
    python_version = lock['target'].get('python_full_version')
    if type(python_version) is not str or not re.fullmatch(r'3\.12\.[0-9]+', python_version):
        _reject()
    packages = lock.get('packages')
    build_packages = lock.get('build_packages')
    if (type(packages) is not list or type(build_packages) is not list
            or not 1 <= len(packages) <= 128 or not 1 <= len(build_packages) <= 16):
        _reject()
    versions = {}
    for package in [*packages, *build_packages]:
        if type(package) is not dict:
            _reject()
        name, version = package.get('name'), package.get('version')
        if (type(name) is not str or not _NAME.fullmatch(name)
                or type(version) is not str or not _VERSION.fullmatch(version)
                or name in versions):
            _reject()
        versions[name] = version
    project = tomllib.loads(_bytes(root, 'pyproject.toml').decode('utf-8'))['project']
    if project.get('name') != 'qx-contract-workbench':
        _reject()
    # The project distribution is represented only by pyproject.toml. A
    # dependency-lock self-reference would otherwise be silently overwritten.
    if 'qx-contract-workbench' in versions:
        _reject()
    project_version = project.get('version')
    if type(project_version) is not str or not _VERSION.fullmatch(project_version):
        _reject()
    versions['qx-contract-workbench'] = project_version
    return python_version, dict(sorted(versions.items()))


def _source_configuration(root: Path) -> None:
    defaults = _json(root, 'config/defaults.json', maximum=65536)
    if (type(defaults) is not dict or defaults.get('model_provider_default') != 'mock'
            or defaults.get('qcc_enabled_default') is not False):
        _reject()
    manifest = _json(root, _MCP_FILE, maximum=65536)
    expected = {'mcpServers': {'qx-contract-offline': {
        'command': (root / '.venv/Scripts/python.exe').as_posix(),
        'args': ['-I', '-X', 'utf8', (root / _ENTRY_FILE).as_posix()],
        'cwd': root.as_posix(), 'enabled': True}}}
    if manifest != expected:
        _reject()
    server = manifest['mcpServers']['qx-contract-offline']
    if server['enabled'] is not True:
        _reject()
    plugin = _json(root, _PLUGIN_FILE, maximum=65536)
    if (type(plugin) is not dict or plugin.get('name') != 'qx-contract-offline-codex'
            or plugin.get('version') != _ADAPTER_VERSION
            or plugin.get('mcpServers') != './.mcp.json'):
        _reject()


def _actual_context(versions: dict[str, str]) -> RuntimeContext:
    return RuntimeContext(python_version=platform.python_version(),
        installed_versions={name: metadata.version(name) for name in versions},
        python_executable=Path(sys.executable).absolute(),
        entry_file=Path(__file__).absolute())


def _payload_build_id(payload: dict) -> str:
    canonical = json.dumps({key: value for key, value in payload.items() if key != 'build_id'},
                           ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                           allow_nan=False).encode('utf-8')
    return 'qx-offline-source-0.1.4-' + sha256(canonical).hexdigest()[:32]


def _verify(root: Path, context: RuntimeContext | None) -> BindingVerification:
    root = _root_path(root)
    payload = _json(root, _BINDING_FILE, maximum=MAX_BINDING_BYTES)
    if type(payload) is not dict or set(payload) != set(_CONSTANT_FIELDS) | _VARIABLE_FIELDS:
        _reject()
    for key, value in _CONSTANT_FIELDS.items():
        if type(payload[key]) is not type(value) or payload[key] != value:
            _reject()
    build_id = payload['build_id']
    if type(build_id) is not str or not _BUILD_ID.fullmatch(build_id):
        _reject()
    if type(payload['repository_root']) is not str or payload['repository_root'] != root.as_posix():
        _reject()
    hashes = payload['repository_file_hashes']
    if type(hashes) is not dict or not 1 <= len(hashes) <= _MAX_FILES:
        _reject()
    for relative, digest in hashes.items():
        if (type(relative) is not str or '\\' in relative or ':' in relative
                or PurePosixPath(relative).is_absolute()
                or PurePosixPath(relative).as_posix() != relative
                or any(part in ('', '.', '..') for part in relative.split('/'))
                or type(digest) is not str or not _HASH.fullmatch(digest)):
            _reject()
    # Compare the independently enumerated set, not just old listed files.
    if hashes != _inventory(root):
        _reject()
    _source_configuration(root)
    python_version, versions = _locked_versions(root)
    if (type(payload['python_version']) is not str or payload['python_version'] != python_version
            or type(payload['installed_versions']) is not dict
            or payload['installed_versions'] != versions):
        _reject()
    context = context or _actual_context(versions)
    if (not isinstance(context, RuntimeContext) or context.python_version != python_version
            or context.installed_versions != versions
            or context.entry_file != root / _ENTRY_FILE
            or context.python_executable != root / '.venv/Scripts/python.exe'):
        _reject()
    _checked_path(context.entry_file)
    _checked_path(context.python_executable)
    if build_id != _payload_build_id(payload):
        _reject()
    return BindingVerification(build_id, len(hashes), len(versions))


def verify_runtime_binding(root: Path, *, context: RuntimeContext | None = None) -> BindingVerification:
    """Read only the controlled source-plugin binding under this repository.

    There is no caller-selectable binding path, environment override or MCP
    argument. ``context`` is an internal pure-test seam, never a CLI option.
    All failures carry the same public code without filenames or input values.
    """
    try:
        return _verify(root, context)
    except Exception:
        raise BindingRejected() from None


def build_binding_snapshot(root: Path) -> dict:
    """Read-only authoring helper for the parent to freeze once source is stable.

    The helper does not write or install anything. After writing this result to
    the fixed source binding, run the actual absolute-path entry with --check.
    """
    try:
        root = _root_path(root)
        _source_configuration(root)
        python_version, versions = _locked_versions(root)
        context = _actual_context(versions)
        if (context.python_version != python_version or context.installed_versions != versions
                or context.python_executable != root / '.venv/Scripts/python.exe'
                or context.entry_file != root / _ENTRY_FILE):
            _reject()
        payload = {**_CONSTANT_FIELDS,
            'expected_tools': list(_CONSTANT_FIELDS['expected_tools']),
            'repository_root': root.as_posix(), 'python_version': python_version,
            'installed_versions': versions, 'repository_file_hashes': _inventory(root)}
        return {**payload, 'build_id': _payload_build_id(payload)}
    except Exception:
        raise BindingRejected() from None


def main(arguments: list[str] | None = None) -> int:
    """--check prints safe status; normal STDIO emits no pre-protocol stdout."""
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    try:
        if arguments not in ([], ['--check']):
            _reject()
        root = Path(__file__).absolute().parents[3]
        result = verify_runtime_binding(root)
        if arguments:
            print(json.dumps({'status': 'BOUND_ENTRY_VERIFIED', 'build_id': result.build_id},
                             ensure_ascii=True, separators=(',', ':')))
            return 0
        # The imported package is reached through the verified project src,
        # rather than a current directory or an external PYTHONPATH override.
        sys.path.insert(0, str(root / 'src'))
        server = import_module(_OFFLINE_MODULE)
        if Path(server.__file__).absolute() != root / _OFFLINE_FILE:
            _reject()
        server.main()
        return 0
    except Exception:
        print('BOUND_ENTRY_REJECTED', file=sys.stderr)
        return 78


if __name__ == '__main__':
    raise SystemExit(main())
