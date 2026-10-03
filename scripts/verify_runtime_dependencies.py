"""Read fixed local dependency evidence; never install, import target packages or fetch.

This checks cache evidence, not native build reproducibility, legal approval or
runtime egress. Release approval is a separate, deliberately closed gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import re
import stat
import tomllib
import zipfile

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def unique_keys(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('DUPLICATE_JSON_KEY')
        result[key]=value
    return result


def strict_json(raw):
    if len(raw)>5*1024*1024:raise ValueError('MANIFEST_LIMIT')
    result=json.loads(raw,object_pairs_hook=unique_keys,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
    todo=[(result,0)]
    while todo:
        value,depth=todo.pop()
        if depth>50:raise ValueError('MANIFEST_DEPTH_LIMIT')
        if isinstance(value,dict):todo.extend((v,depth+1) for v in value.values())
        elif isinstance(value,list):todo.extend((v,depth+1) for v in value)
    return result


def verify_manifest(path, mode='development', *, project_root=ROOT):
    errors = []
    checked = {'checked_packages': 0, 'checked_build_packages': 0}
    root = Path(project_root).resolve()

    def fail(code):
        if code not in errors:
            errors.append(code)

    def read_local(relative):
        if (not isinstance(relative, str) or not relative or '\\' in relative
                or ':' in relative or PureWindowsPath(relative).is_absolute()
                or Path(relative).is_absolute() or '..' in Path(relative).parts):
            raise ValueError('UNSAFE_EVIDENCE_PATH')
        target = root / relative
        if not target.resolve().is_relative_to(root):
            raise ValueError('UNSAFE_EVIDENCE_PATH')
        for ancestor in [target, *target.parents]:
            if ancestor == root:
                break
            info = ancestor.lstat()
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, 'st_file_attributes', 0) & 0x400):
                raise ValueError('REPARSE_EVIDENCE_PATH')
        if not target.is_file() or target.stat().st_size > 100 * 1024 * 1024:
            raise ValueError('EVIDENCE_FILE_INVALID')
        return target.read_bytes()

    def exact(raw, digest, size=None):
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('HASH_INVALID')
        if hashlib.sha256(raw).hexdigest() != digest or (size is not None and len(raw) != size):
            raise ValueError('HASH_BYTES_MISMATCH')

    def approved(record, scope):
        try:
            from uuid import UUID
            UUID(record['approved_by'])
            stamp = datetime.fromisoformat(record['approved_at'].replace('Z', '+00:00'))
            return (stamp.utcoffset() is not None and stamp.utcoffset().total_seconds()==0
                    and isinstance(record['approved_scope'],list) and scope in record['approved_scope'])
        except (KeyError, ValueError, TypeError, AttributeError):
            return False

    try:
        if mode not in {'development', 'release'}:
            raise ValueError('MODE_INVALID')
        payload = strict_json(Path(path).read_bytes())
        packages = payload['packages']; builds = payload['build_packages']
        if not isinstance(packages, list) or not isinstance(builds, list):
            raise ValueError('PACKAGES_INVALID')
        records = {}
        metadata = {}
        for group, count_key in [(packages, 'checked_packages'), (builds, 'checked_build_packages')]:
            for p in group:
                name = p['name']
                if canonicalize_name(name) != name or name in records:
                    raise ValueError('PACKAGE_NAME_INVALID')
                records[name] = p
                if (p['scope'] not in {'development', 'development_runtime_only'} or p['review_status'] not in {
                        'read_verified', 'read_verified_candidate',
                        'development_fixed_wheel_closure_reviewed_production_blocked'}):
                    raise ValueError('PACKAGE_SCOPE_INVALID')
                wheel = read_local(p['wheel_cache']); exact(wheel, p['artifact_sha256'], p['artifact_bytes'])
                meta = read_local(p['metadata_cache']); exact(meta, p['metadata_sha256'])
                registry = read_local(p['registry_cache']); exact(registry, p['registry_sha256'])
                registration = strict_json(registry)
                artifact = next(a for a in registration['urls'] if a['filename'] == p['artifact_filename'])
                if (artifact['digests']['sha256'] != p['artifact_sha256']
                        or artifact['size'] != len(wheel) or artifact['yanked']):
                    raise ValueError('REGISTRY_ARTIFACT_INVALID')
                with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
                    names = archive.namelist()
                    member = next(n for n in names if n.endswith('.dist-info/METADATA') and n.count('/') == 1)
                    if archive.read(member) != meta:
                        raise ValueError('WHEEL_METADATA_MISMATCH')
                    if not isinstance(p['license_evidence'],list) or not p['license_evidence']:
                        raise ValueError('LICENSE_EVIDENCE_MISSING')
                    for evidence in p['license_evidence']:
                        raw = read_local(evidence['local_target'])
                        exact(raw, evidence['sha256'], evidence['bytes'])
                        if archive.read(evidence['path']) != raw:
                            raise ValueError('WHEEL_NOTICE_MISMATCH')
                    if 'native_member_evidence' in p:
                        native=p['native_member_evidence']
                        if not isinstance(native,dict):raise ValueError('NATIVE_EVIDENCE_INVALID')
                        for evidence in native.get('native_members',[])+native.get('C_source_members',[]):
                            raw=archive.read(evidence['path']);exact(raw,evidence['sha256'],evidence['bytes'])
                            if evidence.get('local_target') and read_local(evidence['local_target'])!=raw:
                                raise ValueError('NATIVE_SOURCE_BYTES_INVALID')
                    for declaration in p.get('bundled_code_license_declarations',[]):
                        for evidence in declaration.get('embedded_evidence',[]):
                            raw=read_local(evidence['local_target']);exact(raw,evidence['sha256'],evidence['bytes'])
                            if archive.read(evidence['path'])!=raw:raise ValueError('BUNDLED_BYTES_INVALID')
                msg = BytesParser().parsebytes(meta)
                if canonicalize_name(msg['Name']) != name or msg['Version'] != p['version']:
                    raise ValueError('PACKAGE_METADATA_INVALID')
                if msg.get_all('Requires-Dist',[])!=p['transitive_requires']:
                    raise ValueError('REQUIRES_DIST_INVALID')
                if (SpecifierSet(msg.get('Requires-Python') or '')!=SpecifierSet(p.get('requires_python') or '')
                        or not SpecifierSet(p.get('requires_python') or '').contains(payload['target']['python_full_version'])):
                    raise ValueError('REQUIRES_PYTHON_INVALID')
                metadata[name] = msg
                checked[count_key] += 1
                if mode == 'release' and not approved(p, 'production'):
                    prefix = 'BUILD' if count_key == 'checked_build_packages' else 'DEPENDENCY'
                    fail(f'{prefix}_PRODUCTION_APPROVAL_MISSING:{name}')

        requirements = payload['root_requirements']
        for kind in ('base', 'test', 'build'):
            names = [canonicalize_name(Requirement(r).name) for r in requirements[kind]]
            if names != payload['roots'][kind] or any(n not in records for n in names):
                raise ValueError('ROOTS_INVALID')
            for raw in requirements[kind]:
                req = Requirement(raw)
                if not req.specifier.contains(records[canonicalize_name(req.name)]['version']):
                    raise ValueError('ROOT_VERSION_INVALID')
        project = tomllib.loads(read_local('pyproject.toml').decode('utf-8'))
        normalize = lambda values: [str(Requirement(v)).lower() for v in values]
        if normalize(project['project']['dependencies']) != normalize(requirements['base']):
            raise ValueError('PROJECT_ROOTS_INVALID')
        if (normalize(project['project']['optional-dependencies']['test'])!=normalize(requirements['test'])
                or normalize(project['build-system']['requires'])!=normalize(requirements['build'])):
            raise ValueError('PROJECT_TEST_BUILD_ROOTS_INVALID')
        locked = {}
        for line in read_local('requirements.lock').decode().splitlines():
            if not line.strip() or line.startswith(('#', '--')):
                continue
            raw, digest = line.split(' --hash=sha256:')
            req = Requirement(raw); name = canonicalize_name(req.name)
            if name in locked:
                raise ValueError('DUPLICATE_LOCK_PACKAGE')
            locked[name] = (str(req.specifier), digest)
        if locked != {p['name']: ('==' + p['version'], p['artifact_sha256']) for p in packages}:
            raise ValueError('LOCK_MANIFEST_MISMATCH')
        build_locked={}
        for line in read_local('requirements-build.lock').decode().splitlines():
            if not line.strip() or line.startswith(('#','--')):continue
            raw,digest=line.split(' --hash=sha256:');req=Requirement(raw);name=canonicalize_name(req.name)
            if name in build_locked:raise ValueError('DUPLICATE_BUILD_LOCK')
            build_locked[name]=(str(req.specifier),digest)
        if build_locked!={p['name']:('=='+p['version'],p['artifact_sha256']) for p in builds}:
            raise ValueError('BUILD_LOCK_MANIFEST_MISMATCH')

        by_name = {p['name']: p for p in packages}
        env = payload['target']['marker_environment']
        reached = set(); extras = {n: set() for n in by_name}
        for raw in requirements['base'] + requirements['test']:
            req = Requirement(raw); name = canonicalize_name(req.name)
            reached.add(name); extras[name].update(req.extras)
        changed = True
        while changed:
            changed = False
            for name in list(reached):
                for raw in metadata[name].get_all('Requires-Dist', []):
                    req = Requirement(raw)
                    if req.marker and not any(req.marker.evaluate({**env, 'extra': e}) for e in [''] + sorted(extras[name])):
                        continue
                    dep = canonicalize_name(req.name)
                    if dep not in by_name or not req.specifier.contains(by_name[dep]['version']):
                        raise ValueError('DEPENDENCY_EDGE_INVALID')
                    before = len(reached), len(extras[dep]); reached.add(dep); extras[dep].update(req.extras)
                    changed |= before != (len(reached), len(extras[dep]))
        if reached != set(by_name):
            raise ValueError('DEPENDENCY_CLOSURE_INVALID')
        for name in sorted(reached):
            edges = []; excluded = []
            for raw in metadata[name].get_all('Requires-Dist', []):
                req = Requirement(raw)
                if req.marker and not any(req.marker.evaluate({**env, 'extra': e}) for e in [''] + sorted(extras[name])):
                    excluded.append(raw); continue
                dep = canonicalize_name(req.name)
                edges.append({'name': dep, 'version': by_name[dep]['version'], 'requirement': raw, 'extras': sorted(req.extras)})
            if (edges != by_name[name]['resolved_dependencies'] or excluded != by_name[name]['excluded_requirements']
                    or sorted(extras[name])!=by_name[name]['enabled_extras']):
                raise ValueError('STORED_EDGE_MISMATCH')
        component = payload['T10_template_component']
        if (component['packages'] != ['jinja2==3.1.6', 'markupsafe==3.0.4']
                or component['autoescape_required'] is not True
                or component['source_kind'] != 'fixed_official_package_bytes'
                or component['templates'] != 'independent_project_local_templates'):
            raise ValueError('TEMPLATE_COMPONENT_INVALID')
        if mode == 'release':
            if not isinstance(component.get('production_approval'), dict) or not approved(component['production_approval'], 'production'):
                fail('TEMPLATE_COMPONENT_PRODUCTION_APPROVAL_MISSING')
            if payload.get('approved_for_production') is not True or not approved(payload, 'production'):
                fail('RUNTIME_PRODUCTION_APPROVAL_MISSING')
            # The evidence carries explicit unresolved native/usage/security limits.
            if payload.get('production_blockers'):
                fail('RUNTIME_PRODUCTION_BLOCKERS_UNRESOLVED')
    except (OSError, ValueError, TypeError, KeyError, StopIteration, AttributeError, RuntimeError, RecursionError, zipfile.BadZipFile) as error:
        fail(f'MANIFEST_INVALID:{type(error).__name__}:{error}' if isinstance(error, ValueError) else f'MANIFEST_INVALID:{type(error).__name__}')
    return {'ok': not errors, 'mode': mode, **checked, 'errors': errors,
            'native_build_verified': False, 'network_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT / 'sources/runtime-dependencies.lock.json')
    parser.add_argument('--mode', choices=['development', 'release'], default='development')
    args = parser.parse_args()
    result = verify_manifest(args.manifest, args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)
