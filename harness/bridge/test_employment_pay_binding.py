"""Wage operands must belong to one supported record, not merely one chunk."""
import pytest

from employment_review import save_employment_review
from test_employment_decisions import source_case


def findings(ref):
    parameters = {}
    for key, label, amount in (
        ('contract_pay', '合同工资', '6000元'),
        ('grade_pay', '同岗最低档工资', '5000元'),
        ('minimum_pay', '适用最低工资', '2200元'),
        ('probation_pay', '试用工资', '3500元'),
    ):
        parameters[key] = dict(amount=amount, citation={**ref, 'quote': label + amount})
    return [dict(
        topic='试用工资', fact='拟稿不能代替原文', basis='待核', source='合成材料',
        risk='待核', action='待核', rule='probation_pay', parameters=parameters), dict(
        topic='附件覆盖', fact='目前仅审阅已读片段', basis='完整性核对', source='本次读取范围',
        risk='其他附件未审阅', action='补充后另行审查')]


def review(cases, cid, ref):
    return save_employment_review(cases, cid, 'hiring', findings(ref))


@pytest.mark.parametrize('text', [
    '甲合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，乙试用工资3500元。',
    '甲合同工资6000元。乙同岗最低档工资5000元。适用最低工资2200元。甲试用工资3500元。',
    '2025年合同工资6000元，2026年同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。',
    '合同工资6000元/年，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。',
])
def test_same_chunk_different_owner_or_period_does_not_create_wage_proposal(tmp_path, text):
    cases, cid, ref = source_case(tmp_path, text)
    result = review(cases, cid, ref)
    rule = result['rule_reviews'][0]
    assert rule['comparison'] is None
    assert rule['pending_reason']
    assert '拟约定为4800.00元' not in result['user_summary']
    assert '附件覆盖' in cases.read_note(cid, result['id'])['content']
    for amount in ('6000', '5000', '2200', '3500'):
        assert amount in result['user_summary']
    assert result['citations']


@pytest.mark.parametrize('prefix,suffix', [('', ''),
    ('劳动者：张三；合同编号：C1\n岗位：工程师\n', ''),
    ('', '试用期尚未约定。')])
def test_supported_single_record_still_saves_exact_conditional_proposal(tmp_path, prefix, suffix):
    cases, cid, ref = source_case(tmp_path, prefix + '合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。' + suffix)
    result = review(cases, cid, ref)
    assert result['rule_reviews'][0]['comparison']['contract_floor'] == '4800.00'
    assert result['rule_reviews'][0]['comparison']['grade_floor'] == '4000.00'
    assert '拟约定为4800.00元' in result['user_summary']
    assert result['review_status'] == 'unverified'
    assert cases.read_note(cid, result['id'])['content'] in result['user_summary']


@pytest.mark.parametrize('prefix,suffix', [
    ('以下四项均为年薪。', ''), ('', '上述四项均为年薪。'),
    ('以下四个金额分别属于不同劳动者。', ''), ('', '上述金额并非同一劳动者。'),
    ('下列金额分别来自2025年和2026年。', ''), ('', '上述金额分别适用于2025年与2026年。'),
    ('以下四项均为年薪。\n', ''), ('', '\n上述金额并非同一劳动者。'),
])
def test_context_sentences_keep_wage_unit_owner_and_period_qualifications(tmp_path, prefix, suffix):
    cases, cid, ref = source_case(tmp_path, prefix + '合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。' + suffix)
    result = review(cases, cid, ref)
    assert result['rule_reviews'][0]['comparison'] is None
    assert '拟约定为4800.00元' not in result['user_summary']
    assert '6000元' in result['user_summary']


@pytest.mark.parametrize('header', [
    '劳动者：张三；合同编号：C-1',
    '劳动者：张三；劳动者编号：W-1；合同编号：C-2026-001',
    '劳动者：张三\n劳动者编号：W-1\n合同编号：C-2026-001',
])
def test_recognized_identity_hyphens_are_not_negative_wages(tmp_path, header):
    cases, cid, ref = source_case(tmp_path, header + '\n合同工资6000元\n同岗最低档工资5000元\n适用最低工资2200元\n试用工资3500元')
    result = review(cases, cid, ref)
    assert result['rule_reviews'][0]['comparison']['contract_floor'] == '4800.00'
    for line in header.splitlines():
        assert line in result['user_summary']


def test_real_mcp_keeps_blocked_wage_and_other_findings_in_the_same_word(tmp_path):
    import asyncio
    import json
    import os
    from pathlib import Path
    import subprocess
    from docx import Document
    from check_business_mcp import client, call

    async def run():
        cases, cid, ref = source_case(tmp_path,
            '甲合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，乙试用工资3500元。')
        async with client('business_server.py', tmp_path) as legal:
            args = dict(case_id=cid, stage='hiring', findings=findings(ref), request_id='binding-check')
            result = await call(legal, 'save_employment_review', **args)
            retry = await call(legal, 'save_employment_review', **args)
            assert retry['id'] == result['id']
            assert result['rule_reviews'][0]['comparison'] is None
            doc_args = dict(case_id=cid, note_ids=[result['id']], audience='internal', filename='劳动审查.docx')
            doc = await call(legal, 'export_case', **doc_args)
            note = cases.read_note(cid, result['id'], limit=20000)['content']
            word = '\n'.join(p.text for p in Document(doc['path']).paragraphs)
            for line in note.splitlines():
                if line.strip(): assert line in word
            assert '附件覆盖' in word and '拟约定为4800.00元' not in word
            for amount in ('6000', '5000', '2200', '3500'):
                assert amount in word
            messages = [{'role':'user','content':'审查劳动合同并导出Word'}]
            for number, name, arguments, value in [('review','save_employment_review',args,result),('export','export_case',doc_args,doc)]:
                messages.extend([
                    {'role':'assistant','tool_calls':[{'id':number,'type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]},
                    {'role':'tool','tool_call_id':number,'content':json.dumps({'executed':True,'is_error':False,'result':value})}])
            root = Path(__file__).resolve().parents[1]
            checked = subprocess.run([os.environ.get('QX_TEST_NODE','node'), str(root/'scripts/check_verified_delivery.mjs')],
                cwd=root, input=json.dumps({'workspace':str(tmp_path),'messages':messages,'result':{'choices':[{'message':{'content':'甲的工资必须改成4800元，附件全部审查完毕。'},'finish_reason':'stop'}]}}),
                capture_output=True,text=True,encoding='utf-8',check=True)
            delivered = json.loads(checked.stdout)['text']
            assert '甲的工资必须改成4800' not in delivered
            assert '附件全部审查完毕' not in delivered
            assert '附件覆盖' in delivered and '同一可核算记录' in delivered
    asyncio.run(run())


@pytest.mark.parametrize('prefix,suffix', [
    ('', '\n奖金按员工手册支付，员工手册本次未提供。'),
    ('', '上述四项均为税前月工资标准。'),
    ('独立虚构测试，均为同一员工同一工资期间的数据。劳动者：测试甲；合同编号：C-1\n', ''),
])
def test_supported_wages_survive_unrelated_missing_material_and_explicit_monthly_context(tmp_path, prefix, suffix):
    cases, cid, ref = source_case(tmp_path, prefix + '合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。' + suffix)
    result = review(cases, cid, ref)
    assert result['rule_reviews'][0]['comparison']['contract_floor'] == '4800.00'
    assert suffix.strip() in result['user_summary']


@pytest.mark.parametrize('stage', ['hiring', 'change', 'termination', 'dispute'])
@pytest.mark.parametrize('explicit_rule', [False, True])
def test_probation_wage_cannot_bypass_binding_by_stage_or_generic_topic(tmp_path, stage, explicit_rule):
    cases, cid, ref = source_case(tmp_path, '乙试用工资3500元，周期未说明。甲合同工资6000元。')
    item = dict(topic='报酬问题', fact='乙试用期月工资3500元。', basis='待核', source='合成材料',
                risk='试用工资应调高', action='试用工资拟约定为4800元/月。', citations=[ref])
    if explicit_rule:item['rule']='probation_pay'
    result = save_employment_review(cases, cid, stage, [item])
    assert result['rule_reviews'][0]['comparison'] is None
    body = cases.read_note(cid, result['id'])['content']
    assert '试用期月工资3500' not in body
    assert '拟约定为4800' not in body
    assert '周期未说明' in body


def test_coverage_mentions_do_not_replace_scope_or_duplicate_wage_rules(tmp_path):
    original='合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。'
    cases,cid,ref=source_case(tmp_path,original)
    items=findings(ref)
    items.insert(0,dict(topic='材料覆盖与审查范围',fact='已读工资片段，其中试用工资3500元。',
        source='合成材料',basis='覆盖核对',risk='其他附件本次未审',action='补充附件后继续',citations=[ref]))
    result=save_employment_review(cases,cid,'hiring',items)
    assert len(result['rule_reviews'])==1
    body=cases.read_note(cid,result['id'])['content']
    assert '材料覆盖与审查范围' in body and '补充附件后继续' in body
    assert original in body
