"""Build an isolated, structurally valid manifest for the archive-boundary tests.

Why this exists
---------------
`tests/unit/test_runtime_dependencies.py` used to corrupt the ZIP headers of the
wheel at `packages[-2]['wheel_cache']` and then call `verify_manifest()` with the
*full* 56-package manifest. Two things were wrong with that:

* the registered cache path does not exist in a source checkout, so the test died
  while reading its own input — it never reached the archive at all;
* even with the wheel present, the full manifest cannot reach the archive step,
  because a missing sibling artifact aborts the package loop first. `ok=False`
  in that situation says "something is missing", not "the corrupt header was
  recognised".

So these tests need their own manifest: a small one whose whole structural chain
closes, with the real package bytes. This module builds it.

What is real and what is harness
--------------------------------
Real: the wheels (bytes verified against the frozen lock's registered digest),
their METADATA, their PyPI registry documents, their licence notices, and the
gate module itself — unchanged.

Harness: `pyproject.toml`, `requirements.lock`, `requirements-build.lock` and the
manifest's root/closure fields, which are rewritten to describe only the two
packages involved. That is unavoidable: the gate cross-checks the manifest
against the project's lock files, so a subset manifest needs a subset lock.

Two packages, not one, because the gate checks the dependency closure and
jinja2 3.1.6 declares `MarkupSafe>=2.0`. A single-package manifest fails
`DEPENDENCY_EDGE_INVALID` — that is the gate working, not a workaround.

This module proves nothing about the frozen 56-package gate. Those four nodes
stay failed and are reported as such.
"""
import hashlib
import io
import json
import shutil
import struct
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WHEELS = ROOT / 'tests' / 'fixtures' / 'runtime_wheels'
LOCK = ROOT / 'sources' / 'runtime-dependencies.lock.json'
PACKAGES = ('jinja2', 'markupsafe')
# the package whose headers the negative cases mutate
SUBJECT = 'jinja2'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _copy(root, relative, folder):
    source = ROOT / relative
    target = root / folder / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert target.read_bytes() == source.read_bytes(), relative
    return target.relative_to(root).as_posix()


def _notices(root, package):
    staged = []
    for index, evidence in enumerate(package['license_evidence']):
        source = ROOT / evidence['local_target']
        target = root / 'notices' / package['name'] / ('%d-' % index + source.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assert sha256(target.read_bytes()) == evidence['sha256'], evidence['local_target']
        entry = dict(evidence)
        entry['local_target'] = target.relative_to(root).as_posix()
        staged.append(entry)
    return staged


def _native(root, package):
    evidence = package.get('native_member_evidence')
    if not isinstance(evidence, dict):
        return
    for key in ('native_members', 'startup_or_postinstall_members', 'C_source_members'):
        for member in evidence.get(key, []):
            local = member.get('local_target')
            if not local:
                continue
            source = ROOT / local
            target = root / 'notices' / package['name'] / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            member['local_target'] = target.relative_to(root).as_posix()


def _mutate(raw, defect):
    """Change exactly one header field and nothing else in the archive."""
    buffer = bytearray(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        member = next(i for i in archive.infolist() if i.filename.endswith('.dist-info/METADATA'))
    offset = member.header_offset
    central = buffer.find(b'PK\x01\x02')
    while central >= 0:
        name_len = struct.unpack_from('<H', buffer, central + 28)[0]
        entry = bytes(buffer[central + 46:central + 46 + name_len]).decode()
        if entry == member.filename:
            break
        central = buffer.find(b'PK\x01\x02', central + 4)
    assert central >= 0, 'central directory entry not found'
    if defect == 'encrypted':
        struct.pack_into('<H', buffer, offset + 6, member.flag_bits | 1)
        struct.pack_into('<H', buffer, central + 8, member.flag_bits | 1)
    elif defect == 'unsupported_compression':
        struct.pack_into('<H', buffer, offset + 8, 99)
        struct.pack_into('<H', buffer, central + 10, 99)
    else:
        raise AssertionError('unknown defect: %r' % (defect,))
    return bytes(buffer)


def build(root, defect=None):
    """Stage a self-consistent manifest under `root`; return its path.

    `root` doubles as the gate's `project_root`, so every evidence path handed to
    the gate lives inside it and the real project's lock files are never used.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    registered = {p['name']: p for p in lock['packages']}

    manifest = dict(lock)
    manifest['packages'] = []
    manifest['build_packages'] = []
    manifest['roots'] = {'base': [], 'test': [], 'build': []}

    for name in PACKAGES:
        package = json.loads(json.dumps(registered[name]))
        package['metadata_cache'] = _copy(root, package['metadata_cache'], 'meta')
        package['registry_cache'] = _copy(root, package['registry_cache'], 'registry')
        package['license_evidence'] = _notices(root, package)
        _native(root, package)

        source = WHEELS / package['artifact_filename']
        assert source.is_file(), (
            'the real wheel bytes are required for this test; expected %s' % source)
        raw = source.read_bytes()
        if defect and name == SUBJECT:
            raw = _mutate(raw, defect)
        wheels_dir = root / 'wheels'
        if not wheels_dir.is_dir():
            wheels_dir.mkdir()
        (wheels_dir / package['artifact_filename']).write_bytes(raw)
        package['wheel_cache'] = 'wheels/' + package['artifact_filename']
        package['artifact_sha256'] = sha256(raw)
        package['artifact_bytes'] = len(raw)

        # the registry document must describe the bytes actually fed in, or the
        # gate refuses at REGISTRY_ARTIFACT_INVALID before reading the archive
        registration = json.loads((root / package['registry_cache']).read_bytes())
        for artifact in registration['urls']:
            if artifact['filename'] == package['artifact_filename']:
                artifact['digests']['sha256'] = package['artifact_sha256']
                artifact['size'] = package['artifact_bytes']
        (root / package['registry_cache']).write_bytes(json.dumps(registration).encode())
        package['registry_sha256'] = sha256((root / package['registry_cache']).read_bytes())

        manifest['packages'].append(package)
        manifest['roots']['base'].append(name)

    manifest['roots']['base'].sort()
    manifest['root_requirements'] = {
        'base': ['%s==%s' % (name, registered[name]['version'])
                 for name in manifest['roots']['base']],
        'test': [],
        'build': [],
    }

    (root / 'requirements.lock').write_text('\n'.join(
        '%s==%s --hash=sha256:%s' % (name, registered[name]['version'],
                                     next(p for p in manifest['packages']
                                          if p['name'] == name)['artifact_sha256'])
        for name in sorted(PACKAGES)) + '\n')
    (root / 'requirements-build.lock').write_text('')
    (root / 'pyproject.toml').write_text(
        '[build-system]\n'
        'requires = []\n'
        'build-backend = "setuptools.build_meta"\n'
        '\n'
        '[project]\n'
        'name = "archive-boundary-isolated"\n'
        'version = "0.0.0"\n'
        'requires-python = ">=3.9"\n'
        'dependencies = %s\n'
        '\n'
        '[project.optional-dependencies]\n'
        'test = []\n' % json.dumps(manifest['root_requirements']['base']))

    target = root / 'manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    return target


def registered_sha(name):
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    return next(p for p in lock['packages'] if p['name'] == name)['artifact_sha256']
