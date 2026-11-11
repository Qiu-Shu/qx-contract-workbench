import os
"""Explicit source-bound hypothetical arithmetic stays in the saved review."""
import pytest
from test_employment_decisions import source_case, api


def test_checklist_and_two_alternatives_share_one_saved_record(tmp_path):
    one='情景假设：基数10000元，折算年限8.5年，倍数2。'
    two='情景假设：基数10000元，折算年限8.5年，倍数1。'
    cases,cid,ref=source_case(tmp_path,'员工2003年入职，实际解除及工资基数未知。\n'+one+'\n'+two)
    chunks=cases.read_material(cid,ref['path'])['chunks']
    def cite(quote):
        return {**ref,'quote':quote,'chunk':next(c['ordinal'] for c in chunks if quote in c['text'])}
    result=api().assess_employment_termination(cases,cid,[cite('员工2003年入职，实际解除及工资基数未知。')],scenario_citations=[cite(one),cite(two)])
    assert result['calculation']['performed'] is True
    assert result['calculation']['amount'] is None
    assert [s['amount'] for s in result['calculation']['scenarios']]==['170000.00','85000.00']
    note=cases.read_note(cid,result['id'])
    for value in ['10000 × 8.5 × 2 = 170000.00','10000 × 8.5 × 1 = 85000.00','不相加','2008','实际解除及工资基数未知']:
        assert value in note['content']
    assert '170000.00' in result['user_summary'] and '85000.00' in result['user_summary']
    assert len(cases.get(cid)['notes'])==1


@pytest.mark.parametrize('quote',[
    '员工每月到手10000元，2003年入职，想算2N。',
    '基数10000元，折算年限8.5年，倍数2。',
    '情景假设：基数10000元，折算年限8.5年，倍数0。',
    '情景假设：基数10000元，折算年限8.5年，倍数2。应付170000元。',
    '情景假设：基数1e4元，折算年限8.5年，倍数2。',
])
def test_rejects_inference_invalid_arithmetic_and_extra_assertions_without_saving(tmp_path,quote):
    cases,cid,ref=source_case(tmp_path,quote)
    with pytest.raises(ValueError):api().assess_employment_termination(cases,cid,[ref],scenario_citations=[ref])
    assert cases.get(cid)['notes']==[]


def test_unmatched_assumption_cannot_be_saved_or_silently_dropped(tmp_path):
    cases,cid,ref=source_case(tmp_path,'未提供计算假设。')
    fabricated={**ref,'quote':'情景假设：基数10000元，折算年限8.5年，倍数2。'}
    with pytest.raises(ValueError):api().assess_employment_termination(cases,cid,[ref],scenario_citations=[fabricated])
    assert cases.get(cid)['notes']==[]


def test_negation_cannot_be_removed_by_selecting_only_formula(tmp_path):
    quote='情景假设：基数10000元，折算年限8.5年，倍数2。'
    cases,cid,ref=source_case(tmp_path,'不采用以下'+quote)
    with pytest.raises(ValueError,match='独立完整一行'):
        api().assess_employment_termination(cases,cid,[ref],scenario_citations=[{**ref,'quote':quote}])
    assert cases.get(cid)['notes']==[]


def test_real_mcp_exports_calculation_and_verified_chat_together(tmp_path):
    import asyncio, json, subprocess
    from pathlib import Path
    from docx import Document
    from check_business_mcp import client, call
    async def run():
        quote='情景假设：基数12345.67元，折算年限3.5年，倍数2。'
        cases,cid,ref=source_case(tmp_path,quote)
        async with client('business_server.py',tmp_path) as legal:
            result=await call(legal,'assess_employment_termination',case_id=cid,citations=[ref],scenario_citations=[ref])
            doc=await call(legal,'export_case',case_id=cid,note_ids=[result['id']],filename='同记录计算.docx')
            assert '86419.69' in '\n'.join(p.text for p in Document(doc['path']).paragraphs)
            messages=[{'role':'user','content':'保存清单和假设计算并导出Word'}]
            for number,name,args,value in [('review','assess_employment_termination',{'case_id':cid},result),('export','export_case',{'case_id':cid,'note_ids':[result['id']]},doc)]:
                messages.extend([{'role':'assistant','tool_calls':[{'id':number,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},
                    {'role':'tool','tool_call_id':number,'content':json.dumps({'executed':True,'is_error':False,'result':value})}])
            root=Path(__file__).resolve().parents[1]
            audit=subprocess.run([os.environ.get('QX_TEST_NODE', 'node'),str(root/'scripts/check_verified_delivery.mjs')],
                cwd=root,input=json.dumps({'workspace':str(tmp_path),'messages':messages,'result':{'choices':[{'message':{'content':'实际应付100000元。'},'finish_reason':'stop'}]}}),
                capture_output=True,text=True,encoding='utf-8',check=True)
            delivered=json.loads(audit.stdout)
            assert '86419.69' in delivered['text'] and '不认定实际应付款' in delivered['text']
            assert '实际应付100000' not in json.dumps(delivered,ensure_ascii=False)
            assert delivered['events'][0]['data']['message']['content'][0]['text']==delivered['text']
    asyncio.run(run())
