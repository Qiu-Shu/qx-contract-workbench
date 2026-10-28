"""T10 dependency release gate: actual fixed local bytes; no target imports/network."""
import importlib.util
import json
from pathlib import Path
import pytest

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
    assert dev['ok'] and dev['checked_packages']==56 and dev['checked_build_packages']==1
    release=module.verify_manifest(path,'release',project_root=ROOT)
    assert not release['ok']
    assert 'DEPENDENCY_PRODUCTION_APPROVAL_MISSING:jinja2' in release['errors']
    assert 'DEPENDENCY_PRODUCTION_APPROVAL_MISSING:markupsafe' in release['errors']
    assert 'DEPENDENCY_PRODUCTION_APPROVAL_MISSING:qrcode' in release['errors']
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
    elif defect=='native_sha':
        target=next(p for p in payload['packages'] if p.get('native_member_evidence',{}).get('native_members'))
        target['native_member_evidence']['native_members'][0]['sha256']='0'*64
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


@pytest.mark.parametrize('defect',['encrypted','unsupported_compression'])
def test_malformed_wheel_headers_are_controlled_no_execution(defect):
    import hashlib,struct,tempfile,zipfile,io
    module=gate();payload=json.loads((ROOT/'sources/runtime-dependencies.lock.json').read_text())
    package=payload['packages'][-2]
    raw=bytearray((ROOT/package['wheel_cache']).read_bytes())
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        member=next(i for i in z.infolist() if i.filename.endswith('.dist-info/METADATA'))
    # Rewrite only METADATA headers; do not read or execute package source.
    offset=member.header_offset
    central=raw.find(b'PK\x01\x02')
    while central>=0:
        name_len=struct.unpack_from('<H',raw,central+28)[0]
        name=bytes(raw[central+46:central+46+name_len]).decode()
        if name==member.filename:break
        central=raw.find(b'PK\x01\x02',central+4)
    assert central>=0
    if defect=='encrypted':
        struct.pack_into('<H',raw,offset+6,member.flag_bits|1);struct.pack_into('<H',raw,central+8,member.flag_bits|1)
    else:
        struct.pack_into('<H',raw,offset+8,99);struct.pack_into('<H',raw,central+10,99)
    with tempfile.TemporaryDirectory(dir=ROOT/'.audit-local',prefix='t10-malformed-wheel-') as name:
        directory=Path(name);wheel=directory/package['artifact_filename'];wheel.write_bytes(raw)
        package['wheel_cache']=wheel.relative_to(ROOT).as_posix();package['artifact_sha256']=hashlib.sha256(raw).hexdigest()
        registration=json.loads((ROOT/package['registry_cache']).read_text())
        for artifact in registration['urls']:
            if artifact['filename']==package['artifact_filename']:artifact['digests']['sha256']=package['artifact_sha256']
        registry=directory/'registry.json';registry.write_text(json.dumps(registration))
        package['registry_cache']=registry.relative_to(ROOT).as_posix();package['registry_sha256']=hashlib.sha256(registry.read_bytes()).hexdigest()
        manifest=directory/'manifest.json';manifest.write_text(json.dumps(payload))
        assert not module.verify_manifest(manifest,'development',project_root=ROOT)['ok']
