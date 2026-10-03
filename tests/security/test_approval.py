import pytest
from tests.helpers.synthetic_exports import setup,suggestion,approved,package,api
from cn_contract.security import ServiceError


def test_mock_formal_signer_still_blocked(tmp_path):
    world=setup(tmp_path);bundle=package(world)
    with world[0].session() as db,pytest.raises(ServiceError) as error:
        api().approve_bundle(bundle.id,bundle.manifest_sha256,world[2],db=db)
    assert error.value.code=='BLOCKED_LIVE'


def test_forged_run_provider_does_not_override_backend(tmp_path):
    world=setup(tmp_path);run=world[6]
    fake=run.model_copy(update={'manifest':run.manifest.model_copy(update={'model_provider':'real-provider'})})
    api('storage').initialize_storage(world[0])
    with world[0].session() as db,pytest.raises(ServiceError): api().prepare_exports(fake,'internal',[],world[1],db=db)


@pytest.mark.parametrize('revocation',['role','session'])
def test_current_high_approval_requires_current_distinct_reviewing_identity(tmp_path,monkeypatch,revocation):
    import json
    from cn_contract.review import workflow
    from cn_contract.domain import Severity
    from cn_contract.persistence import UserRow
    from cn_contract.security import ServiceError
    actual=workflow.controlled_findings
    def high(*args,**kwargs):
        return tuple(f.model_copy(update={'severity':Severity.HIGH}) if f.issue_type=='guarantee_material' else f for f in actual(*args,**kwargs))
    monkeypatch.setattr(workflow,'controlled_findings',high)
    world=setup(tmp_path);value=approved(world,suggestion(world));bundle=package(world,patches=[value])
    with world[0].session() as db:
        if revocation=='role':db.get(UserRow,str(world[2].user_id)).roles=json.dumps(['handling_lawyer'])
        else:
            from cn_contract.security import revoke_session
            revoke_session(world[2].session_id,db)
    with world[0].session() as db,pytest.raises(ServiceError):
        api().download_artifact(bundle.artifacts[0].id,world[1],db=db)


@pytest.mark.skipif(__import__('os').name!='nt',reason='Windows filesystem boundary')
def test_local_junction_cannot_redirect_generated_files(tmp_path):
    import subprocess
    from pathlib import Path
    from cn_contract.security import ServiceError
    world=setup(tmp_path);database=world[0];storage=api('storage');storage.initialize_storage(database)
    root=database.storage_root/'derived_exports'
    external=tmp_path/'synthetic-outside-root';external.mkdir()
    result=subprocess.run(['cmd','/c','mklink','/J',str(root),str(external)],capture_output=True)
    assert result.returncode==0 and root.is_junction()
    try:
        with database.session() as db,pytest.raises(ServiceError):api().prepare_exports(world[6],'internal',[],world[1],db=db)
        assert not list(external.iterdir())
    finally:
        if root.exists():root.rmdir()


def test_distinct_reviewing_draft_approval_does_not_require_formal_sign_grant(tmp_path,monkeypatch):
    from cn_contract.review import workflow
    from cn_contract.domain import Severity
    from cn_contract.persistence import MembershipRow
    actual=workflow.controlled_findings
    def high(*args,**kwargs):return tuple(f.model_copy(update={'severity':Severity.HIGH}) if f.issue_type=='guarantee_material' else f for f in actual(*args,**kwargs))
    monkeypatch.setattr(workflow,'controlled_findings',high)
    world=setup(tmp_path)
    with world[0].session() as db:db.get(MembershipRow,(str(world[3].id),str(world[2].user_id))).can_sign=False
    value=approved(world,suggestion(world));bundle=package(world,patches=[value])
    with world[0].session() as db:
        assert api().read_bundle(bundle.id,world[1],db=db)==bundle
        with pytest.raises(ServiceError):api().approve_bundle(bundle.id,bundle.manifest_sha256,world[2],db=db)
