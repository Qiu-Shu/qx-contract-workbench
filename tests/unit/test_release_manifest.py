"""T12 source evidence and real approvals, not client labels or installation."""
from pathlib import Path
import pytest
from cn_contract.domain import ReleaseConfig
from tests.helpers.synthetic_operations import feature


def test_production_missing_actual_lock_cannot_build(tmp_path):
    build = feature('release', 'build_release_manifest')
    cfg = ReleaseConfig(source_lock_ref=str(tmp_path/'missing.lock.json'), rule_version_refs=(),
        config_ref='config/defaults.json', test_evidence_refs=(), deployment_evidence_refs=())
    with pytest.raises(ValueError):
        build(cfg, mode='production')


def test_actual_server_development_manifest_remains_unapproved():
    build = feature('release', 'build_release_manifest')
    cfg = ReleaseConfig(source_lock_ref='sources/upstream.lock.json', rule_version_refs=(),
        config_ref='config/defaults.json', test_evidence_refs=(), deployment_evidence_refs=())
    result = build(cfg)
    assert result.mode == 'development' and result.approved_by is None and result.approved_at is None
    assert result.blockers and 'LAWYER_GOLD_PENDING' in result.blockers
    assert any(x.startswith('SOURCE:') for x in result.blockers) and any(x.startswith('RUNTIME:') for x in result.blockers)
    with pytest.raises(ValueError, match='PRODUCTION_BLOCKED'):
        build(cfg, mode='production')


def test_client_approved_json_is_only_hash_bound(tmp_path):
    from cn_contract.config import PROJECT_ROOT
    from uuid import uuid4
    path = PROJECT_ROOT/'.audit-local'/('t12-untrusted-approval-'+str(uuid4())+'.json')
    path.write_bytes(b'{"approved":true,"decision":"GO","production_ready":true}')
    cfg = ReleaseConfig(source_lock_ref='sources/upstream.lock.json', rule_version_refs=(),
        config_ref='config/defaults.json', test_evidence_refs=(str(path),), deployment_evidence_refs=(str(path),))
    result = feature('release', 'build_release_manifest')(cfg)
    assert result.approved_by is None and result.blockers
    assert all('NOT_ESTABLISHED' in s for s in result.evidence_currentness.values())
    with pytest.raises(ValueError): feature('release', 'build_release_manifest')(cfg, mode='production')


def test_real_release_cli_development_artifact_and_production_block():
    import json, subprocess, sys
    from cn_contract.config import PROJECT_ROOT
    from uuid import uuid4
    output = PROJECT_ROOT/'.local'/('t12-cli-'+str(uuid4())+'.json')
    args = [sys.executable, '-X', 'utf8', '-m', 'cn_contract.cli', 'release-manifest', '--output', str(output)]
    result = subprocess.run(args, capture_output=True, cwd=PROJECT_ROOT, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_bytes())
    assert data['approved_by'] is None and data['blockers'] and data['mode'] == 'development'
    repeated = subprocess.run(args, capture_output=True, cwd=PROJECT_ROOT, encoding='utf-8')
    assert repeated.returncode != 0
    production = output.with_name('production-'+output.name)
    result = subprocess.run([*args[:-1], str(production), '--mode', 'production'], capture_output=True, cwd=PROJECT_ROOT, encoding='utf-8')
    assert result.returncode != 0 and not production.exists()
