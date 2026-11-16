"""Candidate prose is compiled from intent, never from caller-authored facts."""
import pytest
from docx import Document
from test_employment_decisions import source_case
from employment_review import save_employment_review


@pytest.mark.parametrize('intent,source,bad,required', [
    ('probation_clause', '双方既往试用记录未提供，合同类型及期限未说明。',
     '双方此前未就同一岗位约定过试用期。', '同一用人单位与同一劳动者'),
    ('attendance_inquiry', '员工邮件称主管口头同意产检假；考勤条目未展示。',
     '人力资源部查明考勤系统无出勤记录。', '请核对'),
    ('noncompete_inquiry', '员工称公司通知解除，员工是否同意未说明；原通知未提供。',
     '员工从未同意解除。', '解除通知'),
])
def test_compiled_candidate_excludes_unsupported_history_and_keeps_original(tmp_path,intent,source,bad,required):
    cases,cid,ref=source_case(tmp_path,source)
    result=save_employment_review(cases,cid,'hiring',[dict(
        topic='事项',fact='模型概述',basis='适用条件待核',source='合成材料',
        risk='独立意见：确认通知发送及接收方式。',action=bad,citations=[ref],
        drafts=[intent])])
    body=cases.read_note(cid,result['id'])['content']
    assert source in body and required in body and bad not in body
    assert '独立意见：确认通知发送及接收方式。' in body
    audit='\n'.join(p.text for p in Document(result['internal_path']).paragraphs)
    assert bad in audit
    assert result['candidate_drafts'][0]['intents']==[intent]
    assert result['content_assurance']['semantic_verified'] is False


@pytest.mark.parametrize('state', ['员工明确表示同意。','员工明确表示不同意。','员工态度未说明。'])
def test_agreement_states_remain_source_statements_not_generated_history(tmp_path,state):
    source='虚构来源：'+state
    cases,cid,ref=source_case(tmp_path,source)
    result=save_employment_review(cases,cid,'dispute',[dict(
        fact='来源',source='原件',basis='条件',risk='意见',action='自动编写的历史确认',
        citations=[ref],drafts=['noncompete_inquiry'])])
    assert source in result['content']
    text=result['candidate_drafts'][0]['text']
    assert state not in text and '自动编写的历史确认' not in text
    assert '各方对解除的意思表示' in text


def test_multiple_intents_do_not_turn_free_analysis_into_compiled_candidates(tmp_path):
    cases,cid,ref=source_case(tmp_path,'试用记录及出勤情况尚待核实。')
    result=save_employment_review(cases,cid,'hiring',[dict(
        fact='来源',source='原件',basis='模型法律分析',risk='模型风险意见',action='自由行动原稿',
        citations=[ref],drafts=['probation_clause','attendance_inquiry'])])
    assert len(result['candidate_drafts'])==1
    candidate=result['candidate_drafts'][0]['text']
    assert '试用期' in candidate and '请核对' in candidate
    assert not any(s in candidate for s in ['模型法律分析','模型风险意见','自由行动原稿'])
    assert 'AI分析' in result['content']


@pytest.mark.parametrize('drafts', [[],['unknown'],['probation_clause','probation_clause'],
    [{'intent':'probation_clause','text':'此前从未试用'}], 'attendance_inquiry'])
def test_invalid_intent_never_silently_falls_back_to_free_candidate(tmp_path,drafts):
    cases,cid,ref=source_case(tmp_path,'合成原文。')
    with pytest.raises(ValueError,match='drafts'):
        save_employment_review(cases,cid,'hiring',[dict(
            fact='来源',source='原件',basis='条件',risk='意见',action='假事实',citations=[ref],drafts=drafts)])
    assert not cases.get(cid)['notes']


def test_legacy_free_analysis_is_explicitly_not_semantically_verified(tmp_path):
    cases,cid,ref=source_case(tmp_path,'合成原文。')
    result=save_employment_review(cases,cid,'hiring',[dict(
        fact='来源',source='原件',basis='条件',risk='意见',action='自由行动意见',citations=[ref])])
    assert result['content_assurance']['semantic_verified'] is False
    assert result['content_assurance']['free_text_findings']==[0]


def test_actual_mcp_schema_saved_note_and_word_use_same_compiled_candidate(tmp_path):
    import asyncio
    import hashlib
    from check_business_mcp import client, call
    async def run():
        source=tmp_path/'合成.txt'
        text='员工邮件称已请假，考勤具体内容未展示。'
        source.write_text(text,encoding='utf-8')
        async with client('server.py',tmp_path) as materials:
            await call(materials,'import_material',path=source.name)
            await call(materials,'parse_material',path=source.name)
        async with client('business_server.py',tmp_path) as legal:
            schemas={t.name:t.input_schema for t in (await legal.list_tools()).tools}
            assert 'drafts' in schemas['save_employment_review']['$defs']['EmploymentFinding']['properties']
            case=await call(legal,'create_case',title='候选边界测试')
            cid=case['id']
            await call(legal,'link_case_materials',case_id=cid,paths=[source.name])
            ref=dict(path=source.name,quote=text,chunk=0,sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            saved=await call(legal,'save_employment_review',case_id=cid,stage='termination',findings=[dict(
                fact='模型概述',source='来源',basis='适用条件',risk='核实后判断',
                action='人事部已查清该员工故意旷工。',citations=[ref],drafts=['attendance_inquiry'])])
            note=await call(legal,'read_case_note',case_id=cid,note_id=saved['id'])
            doc=await call(legal,'export_case',case_id=cid,note_ids=[saved['id']],filename='核实通知.docx',audience='internal')
            body='\n'.join(p.text for p in Document(doc['path']).paragraphs)
            candidate=saved['candidate_drafts'][0]['text']
            assert candidate in note['content'] and candidate in body and candidate in saved['user_summary']
            assert '已查清该员工故意旷工' not in body
            assert text in body
            assert saved['delivery']['notes'][0]['id']==saved['id']
            assert doc['note_versions'][0]['id']==saved['id']
    asyncio.run(run())
