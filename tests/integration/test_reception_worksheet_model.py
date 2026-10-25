"""Actual synthetic HTTP model roundtrip through the existing profile purpose."""
import asyncio
import json
from uuid import uuid4

from cn_contract import domain as d
from cn_contract.assistant import reception_worksheet as worksheet, service, profile_store, outputs
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import authorize
from tests.integration.test_assistant_main_provider import config, server, KEY
from tests.unit.test_assistant_profile_codec import fixture, response


def test_prepared_reception_task_sends_once_saves_candidates_and_keeps_manual_notes(world):
    database,actor,conversation,_,_ = world
    cid = conversation.scope.conversation_id
    source = '甲称借出10万元，乙称部分已还，目前没有完整还款凭证。'
    notes = '客户诉求：核清款项\n我方立场：未定\n已知陈述（待核）：部分已还\n待核问题：还款金额\n下一步：补凭证'
    profile_store.save_profile(actor,d.ProfileCommitInput(request_id=uuid4(),patch=d.ProfilePatch(
        scope=conversation.scope,base_profile_revision=0,changes=()),manual_edits=(
        d.ProfileEdit(field='consultation',value={'kind':'text','value':source}),
        d.ProfileEdit(field='internal_notes',value={'kind':'text','value':notes}))),database=database)
    with database.session() as db:
        prepared = worksheet.prepare(actor,cid,d.ReceptionWorksheetPrepareInput(expected_scope=conversation.scope,
            base_profile_revision=1,expected_composer_revision=0),db)
        current = service.save_draft(actor,cid,d.AssistantDraftInput(expected_scope=conversation.scope,
            expected_composer_revision=0,content=prepared.content),db)
    request = d.AssistantMessageInput(request_id=uuid4(),expected_scope=current.scope,
        expected_composer_revision=current.composer_revision,content=prepared.content)
    start = prepared.content.index(source)
    quote = {'start':start,'end':start+len(source),'quote':source}
    candidate = {'text':'请核对还款时间、金额、方式和凭证，尚欠金额待核。','citations':[],
        'profile_changes':[
            {'field':'questions','value':{'kind':'list','value':['请核对还款金额和凭证（余额仍待核）。']},'origin':'model_inference','quotes':[quote]},
            {'field':'client_reply','value':{'kind':'text','value':'您好，请补充完整还款记录。'},'origin':'model_inference','quotes':[quote]},
            {'field':'internal_notes','value':{'kind':'text','value':'模型候选不能覆盖律师底稿'},'origin':'model_inference','quotes':[quote]}]}
    raw = response(fixture()[1],candidate)
    with server(raw) as (url,received,_):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)
            _,runtime,_,_ = authorize((database,actor,current,request),provider)
            with database.session() as db:first = attempts.enqueue_profile(actor,cid,request,db,runtime)
            result = await execute_attempt(actor,first.id,database,runtime)
            assert result.state == 'received' and result.output is not None
            assert await execute_attempt(actor,first.id,database,runtime) == result
            return result
        result = asyncio.run(scenario())
    assert len(received) == 1
    wire = json.loads(received[0]['body'])
    sent_content = json.loads(wire['messages'][-1]['content'])['content']
    assert source in sent_content and notes in sent_content
    with database.session() as db:
        view = worksheet.view(actor,cid,db)
        fields = {f.field:f for f in view.fields}
        assert fields['internal_notes'].protected_value.value == notes
        assert fields['questions'].candidates[0].verification == 'unverified'
        assert fields['questions'].candidates[0].source_refs[0].quote == source
        public = outputs.preview(actor,cid,d.AssistantOutputSelection(
            source=d.AssistantOutputSource(kind='profile',profile_revision=view.profile_revision),audience='client'),db)
        assert public.text == '您好，请补充完整还款记录。'
        assert notes not in public.text and '模型候选不能覆盖' not in public.text
        from cn_contract.assistant.model_integrity import validate_model_records
        validate_model_records(db)
