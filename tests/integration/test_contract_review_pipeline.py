"""One synthetic task, combined contract methods, immutable history and export."""
import asyncio
import json
from io import BytesIO
from pathlib import Path
import pytest
from docx import Document
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.assistant import attachments, material_attempts, material_codec, material_preparation
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from tests.helpers.case_evidence import add_document
from tests.helpers.contract_review import draft_for, response
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_material_generation import material_world, grant
from tests.integration.test_assistant_material_routes import boot
from tests.integration.test_material_followup_history import followup
from tests.integration.test_assistant_main_provider import config, KEY, server


def selection(w, task=None):
    return followup(w,task,'我们是供应方，请审查合同与全部附件。',new_task=task is None,workflow='contract')


def execute(w, chosen, value=None):
    basis=material_preparation.preview(w[1],chosen,w[0],config())
    with server(response(basis,value)) as (url,received,_):
        async def scenario():
            _,lease,approved=grant(w,chosen,DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url))
            with w[0].session() as db:
                queued=material_attempts.enqueue(w[1],chosen,approved,db,lease)
            result=await execute_attempt(w[1],queued.id,w[0],lease)
            assert await execute_attempt(w[1],queued.id,w[0],lease)==result
            with w[0].session() as db:
                assert attempts.read_attempt(w[1],queued.id,db)==result
                validate_model_records(db)
            return result
        result=asyncio.run(scenario())
        assert len(received)==1
        wire=json.loads(received[0]['body'])
        assert json.loads(wire['messages'][1]['content'])==basis.manifest.model_dump(mode='json')
    return result,basis


def test_msa_nda_one_task_followup_export_and_restore(material_world,tmp_path):
    w=material_world
    add_document(w,['虚构主服务协议：供应商提供软件服务，交付后验收付款。数据处理协议DPA位于 https://example.invalid/dpa 。'])
    add_document(w,['虚构NDA：保密信息仅用于评估，不得向第三方披露。知识产权全部转让给接收方。'])
    chosen=selection(w)
    basis=material_preparation.preview(w[1],chosen,w[0],config())
    assert [r.methods for r in basis.manifest.contract_review.routes]==[('general',),('vendor',),('nda',)]
    value=draft_for(basis.manifest)
    s=basis.manifest.sources[0];q=s.reference.quote
    value['quotes'].append(dict(id='stance',source_id=s.source_id,start=0,end=len(q),exact_quote=q))
    value.update(stance='supplier',stance_quote_ids=['stance'])
    first,basis=execute(w,chosen,value)
    assert first.output is not None and first.output.review_status=='unverified'
    assert len(first.output.candidate.contract_review.reviews)==3
    assert '我方角色：供应方' in first.output.candidate.text
    assert '红色' in first.output.candidate.text and '绿色关闭' in first.output.candidate.text
    assert 'URL' in first.output.candidate.text and '未覆盖专项：DPA' in first.output.candidate.text
    with w[0].session() as db:
        old_json=db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),{'id':str(first.id)})
    add_document(w,['虚构补充协议：供应方交付后采购方付款，验收期改为15日。'])
    second,new_basis=execute(w,selection(w,basis.manifest.stable_task_id))
    assert second.output is not None
    assert new_basis.manifest.stable_task_id==basis.manifest.stable_task_id
    assert len(second.output.manifest.materials)==4
    assert new_basis.expected_scope.materials_revision>basis.expected_scope.materials_revision
    with w[0].session() as db:
        assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),{'id':str(first.id)})==old_json
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))==2
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs'))==2
    with boot(w,tmp_path) as http:
        out=http.client.get(http.url+'/material-generations/'+str(second.id)+'/document')
        assert out.status_code==200,out.text
        assert second.output.candidate.text in '\n'.join(p.text for p in Document(BytesIO(out.content)).paragraphs)
    root=Path(w[0].engine.url.database).parent
    archive=tmp_path/'contract.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    target=Path(workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)['restored_root'])
    restored=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',w[0].settings,initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token,_=login('lawyer','fixture123',db);actor=authenticate(token,db)
            assert attempts.read_attempt(actor,first.id,db)==first
            assert attempts.read_attempt(actor,second.id,db)==second
            validate_model_records(db)
    finally:restored.engine.dispose()


@pytest.mark.parametrize('boundary',['decode','settle'])
def test_contract_downgrade_keeps_cost_and_never_resends(material_world,monkeypatch,boundary):
    w=material_world;chosen=selection(w)
    basis=material_preparation.preview(w[1],chosen,w[0],config())
    old=dict(text='旧协议无专项条目',citations=[basis.manifest.sources[0].source_id])
    if boundary=='settle':
        decode=material_codec.decode
        def downgrade(*args,**kwargs):
            reply=decode(*args,**kwargs)
            assert reply.output is not None
            return reply.model_copy(update={'output':d.MainMaterialCandidate.model_validate(old)})
        monkeypatch.setattr(material_codec,'decode',downgrade)
    result,_=execute(w,chosen,old if boundary=='decode' else None)
    assert result.output is None and result.receipt.error_code=='MODEL_OUTPUT_INVALID'
    assert result.receipt.usage.total_tokens==42 and result.receipt.cost_status=='estimated'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts'))==1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs'))==0


def test_queued_c4_preserves_original_wire_after_upgrade(material_world,monkeypatch):
    w=material_world;chosen=selection(w)
    with monkeypatch.context() as old:
        old.setattr(material_preparation,'contract_review_for',lambda *args:None)
        basis=material_preparation.preview(w[1],chosen,w[0],config())
    value=dict(text='旧C4草稿保持原样',citations=[basis.manifest.sources[0].source_id])
    with server(response(basis,value)) as (url,received,_):
        async def scenario():
            with monkeypatch.context() as old:
                old.setattr(material_preparation,'contract_review_for',lambda *args:None)
                _,lease,approved=grant(w,chosen,DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url))
                with w[0].session() as db:
                    queued=material_attempts.enqueue(w[1],chosen,approved,db,lease)
                    stored=db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'),{'id':str(queued.id)})
            result=await execute_attempt(w[1],queued.id,w[0],lease)
            assert result.output.candidate.text==value['text']
            assert result.output.candidate.contract_review is None
            with w[0].session() as db:
                assert db.scalar(text('SELECT input_json FROM assistant_model_attempts WHERE id=:id'),{'id':str(queued.id)})==stored
                validate_model_records(db)
            return result
        result=asyncio.run(scenario());assert len(received)==1
    updated=material_preparation.preview(w[1],selection(w,basis.manifest.stable_task_id),w[0],config())
    assert updated.manifest.contract_review is not None
    assert updated.manifest.conversation_history[1].content==result.output.candidate.text


def test_empty_attachment_is_a_coverage_gap_and_all_empty_blocks_before_send(material_world):
    from uuid import uuid4
    w=material_world
    add_document(w,[])
    chosen=selection(w)
    result,basis=execute(w,chosen)
    assert basis.manifest.contract_review.routes[-1].methods==()
    assert result.output is not None and '无可读正文，未执行审查' in result.output.candidate.text
    current=attachments.read_materials(w[1],w[2],database=w[0])
    attachments.select_materials(w[1],w[2],d.AssistantMaterialSelectionInput(
        request_id=uuid4(),expected_scope=current.scope,items=(current.items[-1],)),database=w[0])
    chosen=selection(w,basis.manifest.stable_task_id)
    with pytest.raises(ServiceError) as error:
        material_preparation.preview(w[1],chosen,w[0],config())
    assert error.value.code=='MATERIAL_NOT_READABLE'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))==1


@pytest.mark.parametrize('damage',['derived_text','quote'])
def test_saved_contract_tamper_is_rejected_on_read_and_archive(material_world,damage):
    w=material_world;result,_=execute(w,selection(w))
    with w[0].session() as db:
        raw=json.loads(db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),{'id':str(result.id)}))
        if damage=='derived_text':raw['candidate']['text']='篡改后的绿色签署结论'
        else:raw['candidate']['contract_review']['quotes'][0]['exact_quote']='伪造原文'
        triggers=db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_model_outputs'")).all()
        for name,_ in triggers:db.execute(text('DROP TRIGGER "'+name.replace('"','""')+'"'))
        db.execute(text('UPDATE assistant_model_outputs SET output_json=:v WHERE attempt_id=:id'),
            {'v':encoded(d.MainMaterialOutputView.model_validate(raw)),'id':str(result.id)})
        for _,sql in triggers:db.execute(text(sql))
    with w[0].session() as db:
        with pytest.raises(ValueError):attempts.read_attempt(w[1],result.id,db)
        with pytest.raises(ValueError):validate_model_records(db)
