"""Actual malformed registry copies and real pytest evidence boundaries."""
import hashlib
import io
import json
import shutil
import struct
import zipfile
from uuid import uuid4
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from cn_contract.acceptance import registry, runner
from cn_contract.acceptance.definitions import DEFINITIONS

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = 'tests/fixtures/acceptance/acceptance-provenance.json'


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shadow_dataset(tmp_path, monkeypatch, mutate):
    # A legitimate server-owned clone stays inside the existing trusted root;
    # an outside pytest temp root would exercise only the earlier path guard.
    tmp_path = ROOT/'.local/t11-evidence-shadows'/uuid4().hex
    data = json.loads((ROOT/MANIFEST).read_text(encoding='utf-8'))
    for name in {MANIFEST, *(s[k] for s in data['samples'] for k in ('path', 'template_ref'))}:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    mutate(tmp_path, data)
    digest = save_json(tmp_path/MANIFEST, data)
    monkeypatch.setattr(registry, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(registry, 'BASE', tmp_path/'tests/fixtures/acceptance/synthetic')
    monkeypatch.setattr(registry, 'MANIFEST', tmp_path/MANIFEST)
    monkeypatch.setattr(registry, 'MANIFEST_SHA256', digest)


@pytest.mark.parametrize('framework', [[], [''], '虚构', None])
def test_malformed_family_framework_is_controlled_rejection(tmp_path, monkeypatch, framework):
    def mutate(root, data):
        sample = data['samples'][0]
        path = root/sample['template_ref']
        template = json.loads(path.read_text(encoding='utf-8'))
        template['transaction_framework'] = framework
        digest = save_json(path, template)
        for item in data['samples']:
            if item['template_ref'] == sample['template_ref']:
                item['template_sha256'] = digest
    shadow_dataset(tmp_path, monkeypatch, mutate)
    with pytest.raises(ValueError):
        registry.load_dataset()


def test_duplicate_physical_material_cannot_count_twice(tmp_path, monkeypatch):
    def mutate(root, data):
        first = data['samples'][0]
        second = next(s for s in data['samples'] if s['family'] == first['family'] and s['id'] != first['id'])
        for key in ('path', 'sha256', 'byte_size'):
            second[key] = first[key]
    shadow_dataset(tmp_path, monkeypatch, mutate)
    with pytest.raises(ValueError):
        registry.load_dataset()


def corrupt_document_header(raw, kind):
    with zipfile.ZipFile(io.BytesIO(raw)) as package:
        local = package.getinfo('word/document.xml').header_offset
        central = package.start_dir
    while raw[central:central+4] == b'PK\x01\x02':
        names, extras, comments = struct.unpack_from('<HHH', raw, central+28)
        if raw[central+46:central+46+names] == b'word/document.xml':
            break
        central += 46+names+extras+comments
    else:
        raise AssertionError('technical fixture must contain document header')
    result = bytearray(raw)
    if kind == 'method':
        struct.pack_into('<H', result, local+8, 99)
        struct.pack_into('<H', result, central+10, 99)
    else:
        struct.pack_into('<H', result, local+6, struct.unpack_from('<H', result, local+6)[0] | 1)
        struct.pack_into('<H', result, central+8, struct.unpack_from('<H', result, central+8)[0] | 1)
    return bytes(result)


@pytest.mark.parametrize('kind', ['bad_zip', 'method', 'encrypted'])
def test_malformed_document_container_is_controlled_rejection(tmp_path, monkeypatch, kind):
    def mutate(root, data):
        sample = data['samples'][0]
        path = root/sample['path']
        raw = b'owned-not-a-zip' if kind == 'bad_zip' else corrupt_document_header(path.read_bytes(), kind)
        path.write_bytes(raw)
        sample.update(sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw))
    shadow_dataset(tmp_path, monkeypatch, mutate)
    with pytest.raises(ValueError):
        registry.load_dataset()


def test_execution_snapshot_contains_consumed_helpers_originals_and_guards():
    nodes = tuple(dict.fromkeys(n for d in DEFINITIONS.values() for group in ('capability_tests', 'guard_tests', 'partial_tests') for n in d[group]))
    snapshot = runner._source_snapshot(nodes)
    required = {'sources/upstream.lock.json', 'sources/runtime-dependencies.lock.json',
                'requirements.lock', 'pyproject.toml', 'scripts/verify_sources.py',
                'scripts/verify_runtime_dependencies.py'}
    required.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests/helpers').glob('*.py'))
    required.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests/fixtures/synthetic').glob('*') if p.is_file())
    assert not required-snapshot.keys(), sorted(required-snapshot.keys())


def test_real_pytest_errors_are_separate_from_assertion_failures(tmp_path):
    node = 'tests/fixtures/acceptance/executor/fault_probe.py'
    _, evidence = runner._execute((node,), tmp_path)
    cases = list(ET.parse(evidence.junit_ref).iter('testcase'))
    assert len(cases) == 6
    assert evidence.exit_code == 1
    assert (evidence.passed, evidence.failed, evidence.errors, evidence.skipped) == (3, 1, 1, 1)


def test_true_parameter_interrupt_cannot_certify_complete_function(tmp_path, monkeypatch):
    root = ROOT/'.local/t11-interrupt-shadows'/uuid4().hex
    target = root/'tests/unit/test_owned_interrupt.py'
    target.parent.mkdir(parents=True)
    (root/'pyproject.toml').write_text('[tool.pytest.ini_options]\naddopts = ""\n', encoding='utf-8')
    target.write_text('import pytest\n'
        '@pytest.mark.parametrize("iteration", [0,1,2])\n'
        'def test_known_parameters(iteration):\n'
        '    if iteration == 1: raise KeyboardInterrupt("owned partial interruption")\n'
        '    assert iteration in (0,2)\n', encoding='utf-8')
    artifacts = root/'artifacts'
    artifacts.mkdir()
    monkeypatch.setattr(runner, 'PROJECT_ROOT', root)
    node = 'tests/unit/test_owned_interrupt.py::test_known_parameters'
    states, evidence = runner._execute((node,), artifacts)
    cases = list(ET.parse(evidence.junit_ref).iter('testcase'))
    named = [c for c in cases if 'classname' in c.attrib and 'name' in c.attrib]
    assert evidence.exit_code == 2 and evidence.source_stable
    assert len(named) == 1 and len(cases) == 2
    assert (evidence.passed, evidence.failed, evidence.errors, evidence.skipped) == (1, 0, 0, 0)
    assert states[node] == 'NOT_RUN'


def test_upstream_relative_filename_is_not_current_project_consumed_input():
    # Upstream GH file paths include README.md. Its actual adopted bytes are
    # under local_target; matching a coincidental workspace filename is wrong.
    snapshot = runner._source_snapshot(('tests/unit/test_sources.py::test_reference_only_not_dependency',))
    assert 'README.md' not in snapshot


@pytest.mark.parametrize('exit_code', [0, 1])
def test_pytest_exit_after_first_parameter_is_not_complete(tmp_path, monkeypatch, exit_code):
    root = ROOT/'.local/t11-exit-shadows'/uuid4().hex
    target = root/'tests/unit/test_owned_exit.py'
    target.parent.mkdir(parents=True)
    (root/'pyproject.toml').write_text('[tool.pytest.ini_options]\naddopts = ""\n', encoding='utf-8')
    target.write_text('import pytest\n'
        '@pytest.mark.parametrize("iteration", [0,1,2])\n'
        'def test_known_parameters(iteration):\n'
        f'    if iteration == 1: pytest.exit("owned partial exit", returncode={exit_code})\n'
        '    assert iteration in (0,2)\n', encoding='utf-8')
    artifacts = root/'artifacts'
    artifacts.mkdir()
    monkeypatch.setattr(runner, 'PROJECT_ROOT', root)
    node = 'tests/unit/test_owned_exit.py::test_known_parameters'
    states, evidence = runner._execute((node,), artifacts)
    assert evidence.exit_code == exit_code and evidence.source_stable
    assert evidence.passed == 1 and evidence.failed == evidence.errors == 0
    assert states[node] == 'NOT_RUN'


def test_native_collection_error_is_counted_without_classname(tmp_path, monkeypatch):
    root = ROOT/'.local/t11-collection-shadows'/uuid4().hex
    target = root/'tests/unit/test_owned_collection.py'
    target.parent.mkdir(parents=True)
    (root/'pyproject.toml').write_text('[tool.pytest.ini_options]\naddopts = ""\n', encoding='utf-8')
    target.write_text('raise RuntimeError("owned collection error")\n', encoding='utf-8')
    artifacts = root/'artifacts'
    artifacts.mkdir()
    monkeypatch.setattr(runner, 'PROJECT_ROOT', root)
    node = 'tests/unit/test_owned_collection.py'
    states, evidence = runner._execute((node,), artifacts)
    actual = list(ET.parse(evidence.junit_ref).iter('testcase'))
    assert len(actual) == 1 and actual[0].find('error') is not None
    assert evidence.exit_code == 2 and evidence.errors == 1 and evidence.failed == evidence.passed == 0
    assert states[node] == 'NOT_RUN'


def test_complete_node_pass_survives_other_node_assertion_exit_one(tmp_path):
    nodes = ('tests/fixtures/acceptance/executor/fault_probe.py::test_pass',
             'tests/fixtures/acceptance/executor/fault_probe.py::test_assertion_failure')
    states, evidence = runner._execute(nodes, tmp_path)
    assert evidence.exit_code == 1
    assert (evidence.passed, evidence.failed, evidence.errors) == (3, 1, 0)
    assert states[nodes[0]] == 'PASS' and states[nodes[1]] == 'FAIL'
