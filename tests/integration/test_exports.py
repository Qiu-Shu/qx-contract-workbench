from io import BytesIO
import zipfile
import pytest
from tests.helpers.synthetic_exports import setup,suggestion,approved,package,api


@pytest.mark.parametrize('audience',['internal','client','counterparty'])
def test_three_audiences_real_new_chinese_draft_docx(tmp_path,audience):
    world=setup(tmp_path);value=approved(world,suggestion(world))
    bundle=package(world,audience,[value])
    assert bundle.audience==audience and bundle.artifacts
    with world[0].session() as db:
        for artifact in bundle.artifacts:
            assert artifact.mode=='draft' and artifact.approval_id is None
            raw=api().download_artifact(artifact.id,world[1],db=db).read()
            with zipfile.ZipFile(BytesIO(raw)) as z:
                assert b'DRAFT' in b' '.join(z.read(n) for n in z.namelist())
        report=next(a for a in bundle.artifacts if a.type=='review_report_docx')
        raw=api().download_artifact(report.id,world[1],db=db).read()
        with zipfile.ZipFile(BytesIO(raw)) as z:
            assert '模拟'.encode() in z.read('word/document.xml')


def test_candidate_file_tamper_blocks_download(tmp_path):
    from pathlib import Path
    from cn_contract.security import ServiceError
    world=setup(tmp_path);bundle=package(world)
    artifact=bundle.artifacts[0];path=Path(artifact.storage_ref)
    path.chmod(0o600);path.write_bytes(b'fictional corruption')
    with world[0].session() as db,pytest.raises(ServiceError): api().download_artifact(artifact.id,world[1],db=db)


def test_partial_file_write_caught_commit_leaves_no_artifact(tmp_path,monkeypatch):
    import builtins
    from pathlib import Path
    from sqlalchemy import select
    from cn_contract.persistence import ExportRow
    world=setup(tmp_path);database,actor,_,_,_,_,run=world
    storage=api('storage');storage.initialize_storage(database)
    original=builtins.open
    class Partial:
        def __init__(self,stream):self.stream=stream
        def __enter__(self):self.stream.__enter__();return self
        def __exit__(self,*args):return self.stream.__exit__(*args)
        def write(self,data):self.stream.write(data[:11]);raise OSError('synthetic partial disk failure')
    def opened(path,mode='r',*args,**kwargs):
        stream=original(path,mode,*args,**kwargs)
        return Partial(stream) if mode=='xb' and Path(path).parent.name=='derived_exports' else stream
    with database.session() as db:
        with monkeypatch.context() as scope:
            scope.setattr(builtins,'open',opened)
            with pytest.raises(OSError):api().prepare_exports(run,'internal',[],actor,db=db)
    with database.session() as db:
        assert not list(db.scalars(select(ExportRow)))
        assert not list(db.scalars(select(storage.ExportRecordRow).where(storage.ExportRecordRow.kind=='bundle')))
    root=database.storage_root/'derived_exports'
    assert not root.exists() or not list(root.iterdir()), 'partial derived bytes must be transaction owned before writing'


def test_case_assistant_can_read_approved_draft_without_patch_management(tmp_path):
    from cn_contract.domain import Role
    world=setup(tmp_path,reader=True);value=approved(world,suggestion(world));bundle=package(world,patches=[value])
    database=world[0];reader=database._synthetic_t09_reader
    with database.session() as db:
        assert api().read_bundle(bundle.id,reader,db=db)==bundle
        assert api().download_artifact(bundle.artifacts[0].id,reader,db=db).read()
        with pytest.raises(Exception):api().revoke_patch(world[3].id,value.id,reader,db=db)


def test_report_title_has_no_border_and_all_pages_share_watermark_settings(tmp_path):
    from lxml import etree
    world=setup(tmp_path);bundle=package(world)
    with world[0].session() as db:raw=api().download_artifact(bundle.artifacts[0].id,world[1],db=db).read()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        styles=etree.fromstring(archive.read('word/styles.xml'))
        assert not styles.xpath('//w:style[@w:styleId="Title"]/w:pPr/w:pBdr',namespaces=ns)
        settings=etree.fromstring(archive.read('word/settings.xml'))
        assert not settings.xpath('//w:evenAndOddHeaders[not(@w:val="0")]',namespaces=ns)
        document=etree.fromstring(archive.read('word/document.xml'))
        assert not document.xpath('//w:sectPr/w:titlePg[not(@w:val="0")]',namespaces=ns)
        text=''.join(document.xpath('//w:t/text()',namespaces=ns))
        assert '主体身份' in text and '材料不足' in text and '读取材料范围' in text
        assert 'insufficient_material' not in text


@pytest.mark.parametrize('audience',['client','counterparty'])
@pytest.mark.parametrize('part',['word/comments.xml','docProps/custom.xml','customXml/item1.xml'])
def test_outward_all_zip_parts_exclude_private_source_payload(tmp_path,audience,part):
    canary='SYNTHETIC_INTERNAL_BOTTOMLINE_NEVER_OUTWARD'
    world=setup(tmp_path,extras={part:'<synthetic>'+canary+'</synthetic>'})
    value=approved(world,suggestion(world));bundle=package(world,audience,[value])
    assert len(bundle.artifacts)==1
    with world[0].session() as db:
        for artifact in bundle.artifacts:
            raw=api().download_artifact(artifact.id,world[1],db=db).read()
            with zipfile.ZipFile(BytesIO(raw)) as z:
                assert all(canary.encode() not in z.read(name) for name in z.namelist())


@pytest.mark.parametrize('operation',['approval','bundle','revoke'])
def test_record_failure_caught_commit_rolls_back_whole_operation(tmp_path,monkeypatch,operation):
    from sqlalchemy import select,func
    world=setup(tmp_path);storage=api('storage');storage.initialize_storage(world[0])
    value=approved(world,suggestion(world)) if operation=='revoke' else suggestion(world)
    with world[0].session() as db:before=db.scalar(select(func.count()).select_from(storage.ExportRecordRow))
    root=world[0].storage_root/'derived_exports';before_files=set(root.glob('*'))
    original=storage.append
    def failing(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('synthetic after flush')
    with world[0].session() as db:
        with monkeypatch.context() as scope:
            scope.setattr(storage,'append',failing)
            with pytest.raises(RuntimeError):
                if operation=='approval':api().approve_patch(world[3].id,world[6].id,value,world[2],db=db)
                elif operation=='bundle':api().prepare_exports(world[6],'internal',[],world[1],db=db)
                else:api().revoke_patch(world[3].id,value.id,world[2],db=db)
    with world[0].session() as db:assert db.scalar(select(func.count()).select_from(storage.ExportRecordRow))==before
    assert set(root.glob('*'))==before_files


def test_patch_and_bundle_operations_have_hash_only_audit(tmp_path):
    import json
    from sqlalchemy import select
    from cn_contract.persistence import AuditRow
    world=setup(tmp_path);value=approved(world,suggestion(world));bundle=package(world,patches=[value])
    with world[0].session() as db:
        api().revoke_patch(world[3].id,value.id,world[2],db=db)
        rows=list(db.scalars(select(AuditRow).where(AuditRow.action.in_(['patch_approved','export_prepared','patch_revoked']))))
    assert len(rows)==3
    for row in rows:
        assert value.old_text not in row.payload and value.new_text not in row.payload and value.reason not in row.payload
        payload=json.loads(row.payload)
        assert len(payload['after_hash'])==64 and 'reason_sha256' in payload
