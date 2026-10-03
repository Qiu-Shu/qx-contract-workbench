import pytest
from tests.helpers.synthetic_exports import setup,suggestion,approved,api,QUOTE,NEW
from cn_contract.security import ServiceError


def test_cross_run_native_exact_patch_preserves_original_and_duplicate(tmp_path):
    world=setup(tmp_path);value=approved(world,suggestion(world))
    database,actor,_,matter,context,_,_=world
    from cn_contract.persistence import read_original
    with database.session() as db:
        original=read_original(matter.id,value.document_version_id,actor,db)
        result=api('redline_adapter').apply_patch(context.document_versions[0],value,actor=actor,db=db)
        assert result.status=='applied' and result.target_sha256
        assert read_original(matter.id,value.document_version_id,actor,db)==original
        raw=api('storage').read_patch_artifact(matter.id,value.id,actor,db=db)
        assert api('redline_adapter').baseline_texts(raw,accept=False)==api('redline_adapter').baseline_texts(original,accept=False)
        assert api('redline_adapter').baseline_texts(raw,accept=True)[2]==NEW
        assert api('redline_adapter').baseline_texts(raw,accept=True)[3]==QUOTE


def test_dto_approved_by_is_not_backend_patch_proof(tmp_path):
    world=setup(tmp_path);value=suggestion(world)
    from cn_contract.domain import Patch
    fake=Patch.model_validate({**value.model_dump(mode='python'),'status':'approved','approved_by':world[2].user_id})
    api('storage').initialize_storage(world[0])
    with world[0].session() as db,pytest.raises(ServiceError):
        api('redline_adapter').apply_patch(world[4].document_versions[0],fake,actor=world[1],db=db)


@pytest.mark.parametrize('field',['new_text','reason','anchor_id','finding_id'])
def test_exact_approved_payload_mutation_rejected(tmp_path,field):
    from uuid import uuid4
    world=setup(tmp_path);value=approved(world,suggestion(world))
    replacement=uuid4() if field.endswith('_id') else '未经批准的改动'
    with world[0].session() as db,pytest.raises(ServiceError):
        api('redline_adapter').apply_patch(world[4].document_versions[0],value.model_copy(update={field:replacement}),actor=world[1],db=db)


def test_substring_is_manual_not_guessed_first_occurrence(tmp_path):
    world=setup(tmp_path);value=approved(world,suggestion(world,old='履约保证'))
    with world[0].session() as db:
        result=api('redline_adapter').apply_patch(world[4].document_versions[0],value,actor=world[1],db=db)
        assert result.status=='manual_required' and result.target_sha256 is None


def test_standalone_redline_read_rechecks_patch_revocation(tmp_path):
    world=setup(tmp_path);value=approved(world,suggestion(world))
    with world[0].session() as db:
        api('redline_adapter').apply_patch(world[4].document_versions[0],value,actor=world[1],db=db)
        api().revoke_patch(world[3].id,value.id,world[2],db=db)
    with world[0].session() as db,pytest.raises(ServiceError):
        api('storage').read_patch_artifact(world[3].id,value.id,world[1],db=db)


@pytest.mark.parametrize('structure',[
 '<w:bookmarkStart w:id="100001" w:name="synthetic"/><w:r><w:t>供应商另行提供履约保证。</w:t></w:r><w:bookmarkEnd w:id="100001"/>',
 '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:t>供应商另行提供履约保证。</w:t></w:r>',
 '<w:r><w:t>供应商另行提供履约保证。</w:t><w:br/></w:r>',
 '<w:r><w:t>供应商另行提供履约保证。</w:t></w:r><w:r><w:rPr><w:vanish/></w:rPr><w:t>内部隐藏辅助文字</w:t></w:r>',
],ids=['bookmark','field','linebreak','hidden'])
def test_complex_paragraph_has_explicit_manual_without_contract_copy(tmp_path,structure):
    from tests.helpers.synthetic_exports import BODY,package
    body=BODY.replace(BODY[BODY.index('<w:p><w:r><w:rPr>'):BODY.index('<w:p><w:r><w:t xml:space')],'<w:p>'+structure+'</w:p>')
    world=setup(tmp_path,body=body);value=approved(world,suggestion(world))
    with world[0].session() as db:
        result=api('redline_adapter').apply_patch(world[4].document_versions[0],value,actor=world[1],db=db)
        assert result.status=='manual_required'
    bundle=package(world,patches=[value])
    assert len(bundle.artifacts)==1 and bundle.artifacts[0].type=='review_report_docx'


def test_table_fallback_manual_row_binds_exact_old_new_reason_and_location(tmp_path):
    from io import BytesIO
    import zipfile
    from lxml import etree
    from tests.helpers.synthetic_exports import BODY,package
    body=BODY+'<w:tbl><w:tr><w:tc><w:p><w:r><w:t>供应商另行提供履约保证表格项。</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    world=setup(tmp_path,body=body);index=next(i for i,a in enumerate(world[5].anchors) if a.kind=='table_cell')
    value=approved(world,suggestion(world,anchor_index=index));bundle=package(world,patches=[value])
    assert len(bundle.artifacts)==1
    with world[0].session() as db:raw=api().download_artifact(bundle.artifacts[0].id,world[1],db=db).read()
    with zipfile.ZipFile(BytesIO(raw)) as z:document=etree.fromstring(z.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    anchor=world[5].anchors[index];location=anchor.part_name+':'+anchor.element_id
    rows=[''.join(row.xpath('.//w:t/text()',namespaces=ns)) for row in document.xpath('//w:tr',namespaces=ns)]
    assert any(all(item in row for item in [location,value.old_text,value.new_text,value.reason,'需人工处理']) for row in rows)


def test_approval_rejects_real_anchor_from_other_current_document(tmp_path):
    world=setup(tmp_path,second_document=True);value=suggestion(world)
    wrong=value.model_copy(update={'document_version_id':world[4].document_versions[1].id})
    api('storage').initialize_storage(world[0])
    with world[0].session() as db,pytest.raises(ServiceError):
        api().approve_patch(world[3].id,world[6].id,wrong,world[2],db=db)
