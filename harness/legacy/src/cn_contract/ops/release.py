"""Current server artifacts bind a restricted manifest; no caller approval grants."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from ..config import PROJECT_ROOT, DEFAULTS_PATH
from ..domain import ReleaseConfig, ReleaseManifest
from .backup import checked_file, strict_json, encode
from .secrets import scan_candidates


def _load_script(name):
    path = PROJECT_ROOT/'scripts'/(name+'.py')
    spec = importlib.util.spec_from_file_location('cn_server_'+name, path)
    module = importlib.util.module_from_spec(spec)
    # Fixed server-owned implementation path, never code selected by data.
    spec.loader.exec_module(module)
    return module


def build_release_manifest(config, *, mode='development'):
    config = ReleaseConfig.model_validate_json(config.model_dump_json())
    if mode not in ('development', 'production'): raise ValueError('UNKNOWN_RELEASE_MODE')
    lock = (PROJECT_ROOT/'sources/upstream.lock.json').resolve()
    supplied = Path(config.source_lock_ref)
    supplied = supplied if supplied.is_absolute() else PROJECT_ROOT/supplied
    cfg = Path(config.config_ref)
    cfg = cfg if cfg.is_absolute() else PROJECT_ROOT/cfg
    if supplied.resolve() != lock or cfg.resolve() != DEFAULTS_PATH.resolve():
        raise ValueError('SERVER_REGISTERED_SOURCE_AND_CONFIG_REQUIRED')
    refs = [lock, DEFAULTS_PATH]
    groups = {'rules': config.rule_version_refs, 'tests': config.test_evidence_refs, 'deployment': config.deployment_evidence_refs}
    resolved, hashes = {}, {}
    for group, names in groups.items():
        resolved[group] = []
        for name in names:
            path = Path(name); path = path if path.is_absolute() else PROJECT_ROOT/path
            raw = checked_file(path, PROJECT_ROOT)
            refs.append(path); hashes[path.relative_to(PROJECT_ROOT).as_posix()] = hashlib.sha256(raw).hexdigest()
            resolved[group].append((path, raw))
    raw_lock = checked_file(lock, PROJECT_ROOT)
    raw_config = checked_file(DEFAULTS_PATH, PROJECT_ROOT)
    candidates = {p.relative_to(PROJECT_ROOT).as_posix(): checked_file(p, PROJECT_ROOT) for p in refs}
    if not scan_candidates(candidates).ok: raise ValueError('SECRET_CANDIDATE_BLOCKED')
    # Current approved source/runtime gates retain their independent scopes.
    source = _load_script('verify_sources')
    runtime = _load_script('verify_runtime_dependencies')
    source_result = source.verify_manifest(lock, mode='release')
    runtime_result = runtime.verify_manifest(PROJECT_ROOT/'sources/runtime-dependencies.lock.json', mode='release', project_root=PROJECT_ROOT)
    blockers = ['LAWYER_GOLD_PENDING', 'HOST_REGION_UNAPPROVED', 'OS_SANDBOX_NOT_EXECUTED', 'PRODUCTION_TLS_NOT_DEPLOYED', 'DATA_POLICY_AND_KEY_CUSTODY_UNAPPROVED', 'BLIND_AND_SHADOW_LIVE_ACCEPTANCE_PENDING']
    blockers.extend('SOURCE:'+e for e in source_result.errors)
    blockers.extend('RUNTIME:'+e for e in runtime_result['errors'])
    # Generic file refs only bind bytes; they never assert approval or currentness.
    currentness = {name: 'HASH_BOUND_ONLY_APPROVAL_AND_CURRENT_SOURCE_NOT_ESTABLISHED' for name in hashes}
    if not resolved['rules']: blockers.append('RULE_APPROVAL_EVIDENCE_MISSING')
    if not resolved['tests']: blockers.append('CURRENT_TEST_EVIDENCE_MISSING')
    if not resolved['deployment']: blockers.append('RESTORE_AND_DEPLOYMENT_EVIDENCE_MISSING')
    if mode == 'production' and blockers: raise ValueError('PRODUCTION_BLOCKED:'+str(len(blockers)))
    def group_hash(name): return hashlib.sha256(encode([(p.relative_to(PROJECT_ROOT).as_posix(), hashlib.sha256(raw).hexdigest()) for p, raw in resolved[name]])).hexdigest()
    return ReleaseManifest(source_lock_sha256=hashlib.sha256(raw_lock).hexdigest(), rules_sha256=group_hash('rules'),
        config_sha256=hashlib.sha256(raw_config).hexdigest(), test_evidence_sha256=group_hash('tests'), deployment_evidence_sha256=group_hash('deployment'),
        approved_by=None, approved_at=None, mode=mode, blockers=tuple(blockers), evidence_hashes=hashes,
        evidence_currentness=currentness, created_at=datetime.now(timezone.utc))
