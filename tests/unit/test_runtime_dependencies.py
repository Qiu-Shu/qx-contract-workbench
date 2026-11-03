"""T10 dependency release gate: actual fixed local bytes; no target imports/network."""
import importlib.util
import json
from pathlib import Path
import pytest

from tests.helpers import runtime_archive_fixture

ROOT=Path(__file__).resolve().parents[2]


def gate():
    path=ROOT/'scripts/verify_runtime_dependencies.py'
    assert path.exists(), 'A dedicated fixed runtime/build/template approval gate is required'
    spec=importlib.util.spec_from_file_location('runtime_gate_under_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_runtime_gate_checks_fixed_bytes_and_new_template_release_blockers():
    module=gate();path=ROOT/'sources/runtime-dependencies.lock.json'
    dev=module.verify_manifest(path,'development',project_root=ROOT)
    assert dev['ok'] and dev['checked_packages']==55 and dev['checked_build_packages']==1
    release=module.verify_manifest(path,'release',project_root=ROOT)
    assert not release['ok']
    assert 'DEPENDENCY_PRODUCTION_APPROVAL_MISSING:jinja2' in release['errors']
    assert 'DEPENDENCY_PRODUCTION_APPROVAL_MISSING:markupsafe' in release['errors']
    assert 'BUILD_PRODUCTION_APPROVAL_MISSING:setuptools' in release['errors']
    assert 'TEMPLATE_COMPONENT_PRODUCTION_APPROVAL_MISSING' in release['errors']


@pytest.mark.parametrize('defect',['missing','unknown_scope','hash','traversal','absolute','extra_root','component','edge'])
def test_runtime_gate_malformed_inputs_are_controlled_not_pass(tmp_path,defect):
    module=gate();payload=json.loads((ROOT/'sources/runtime-dependencies.lock.json').read_text(encoding='utf-8'))
    target=payload['packages'][-2]
    if defect=='missing':del target['metadata_cache']
    elif defect=='unknown_scope':target['scope']='production-approved-by-filename'
    elif defect=='hash':target['artifact_sha256']='0'*64
    elif defect=='traversal':target['metadata_cache']='../synthetic-no-read'
    elif defect=='absolute':target['metadata_cache']=str(tmp_path/'synthetic-no-read')
    elif defect=='extra_root':payload['roots']['base'].append('unregistered-template')
    elif defect=='component':payload['T10_template_component']['autoescape_required']=False
    else:target['resolved_dependencies']=[{'name':'not-registered','version':'0','requirement':'not-registered','extras':[]}]
    path=tmp_path/'manifest.json';path.write_text(json.dumps(payload),encoding='utf-8')
    result=module.verify_manifest(path,'development',project_root=ROOT)
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('defect',['empty_notice','python','requires','extras','native_sha','native_scalar','scope_string','nonutc','duplicate','nonfinite','deep'])
def test_gate_does_not_accept_inconsistent_or_ambiguous_evidence(tmp_path,defect):
    module=gate();payload=json.loads((ROOT/'sources/runtime-dependencies.lock.json').read_text())
    target=payload['packages'][-1]
    mode='development'
    if defect=='empty_notice':target['license_evidence']=[]
    elif defect=='python':target['requires_python']='<0'
    elif defect=='requires':target['transitive_requires']=['fake-runtime==0']
    elif defect=='extras':target['enabled_extras']=['fake']
    elif defect=='native_sha':target['native_member_evidence']['native_members'][0]['sha256']='0'*64
    elif defect=='native_scalar':target['native_member_evidence']=False
    elif defect in {'scope_string','nonutc'}:
        mode='release'
        approval={'approved_by':'11111111-1111-4111-8111-111111111111','approved_at':'2026-01-01T00:00:00+00:00','approved_scope':['production']}
        payload.update(approval,approved_for_production=True,production_blockers=[])
        for p in payload['packages']+payload['build_packages']:p.update(approval)
        payload['T10_template_component']['production_approval']=approval.copy()
        for p in payload['packages']+payload['build_packages']:
            if defect=='scope_string':p['approved_scope']='production'
            else:p['approved_at']='2026-01-01T08:00:00+08:00'
    raw=json.dumps(payload)
    if defect=='duplicate':raw=raw[:-1]+',"packages":'+json.dumps(payload['packages'])+'}'
    elif defect=='nonfinite':raw=raw[:-1]+',"unexpected":NaN}'
    elif defect=='deep':raw='['*10000+'0'+']'*10000
    path=tmp_path/'malformed.json';path.write_text(raw)
    assert not module.verify_manifest(path,mode,project_root=ROOT)['ok']


def test_isolated_archive_manifest_is_valid_before_any_header_is_mutated(tmp_path):
    """The green case the negative cases are measured against.

    Without this, `assert not result['ok']` in the two tests below would be
    satisfied by any structural complaint, which is exactly the failure mode
    this gate must not have. The manifest covers only jinja2 + markupsafe, and
    the wheels are the real registered bytes.
    """
    module=gate()
    manifest=runtime_archive_fixture.build(tmp_path)
    assert runtime_archive_fixture.sha256((tmp_path/'wheels'/'jinja2-3.1.6-py3-none-any.whl').read_bytes())==runtime_archive_fixture.registered_sha('jinja2')
    result=module.verify_manifest(manifest,'development',project_root=tmp_path)
    assert result['ok'], result
    assert result['errors']==[] and result['checked_packages']==2
    assert result['native_build_verified'] is False and result['network_calls']==0


# The parameter ids carry the expected error type on purpose. The old ids were
# `[encrypted]` / `[unsupported_compression]`, which read as if the case name
# were the whole claim; `[encrypted-RuntimeError]` says what the refusal must be.
# This is a rename only: same body, same exact-match assertion, nothing relaxed.
@pytest.mark.parametrize(
    'defect,expected',
    [('encrypted','RuntimeError'),('unsupported_compression','NotImplementedError')],
    ids=['encrypted-RuntimeError','unsupported_compression-NotImplementedError'])
def test_malformed_wheel_headers_are_controlled_no_execution(tmp_path,defect,expected):
    module=gate()
    # Same fixture, same bytes, same gate: first prove the isolated manifest
    # closes, then flip one header field of the jinja2 wheel and nothing else.
    baseline=module.verify_manifest(runtime_archive_fixture.build(tmp_path/'valid'),'development',project_root=tmp_path/'valid')
    assert baseline['ok'] and baseline['errors']==[], (
        'the isolated manifest must be valid before the header is mutated, otherwise a '
        'refusal below could be any structural complaint: %r' % (baseline,))
    mutated=runtime_archive_fixture.build(tmp_path/'defect',defect=defect)
    result=module.verify_manifest(mutated,'development',project_root=tmp_path/'defect')
    assert not result['ok'], result
    # Exact match, not a substring search: a single targeted refusal and no
    # other structural error is the whole claim being made here.
    assert result['errors']==['MANIFEST_INVALID:'+expected], (
        'expected exactly one archive-boundary refusal (%s), got %r' % (expected,result['errors']))
    assert result['checked_packages']==0

