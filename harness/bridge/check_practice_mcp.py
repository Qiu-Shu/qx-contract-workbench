"""Synthetic real MCP roundtrip for the practice replacements."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from docx import Document
from check_business_mcp import client, call


async def run():
    with TemporaryDirectory(prefix='qx-practice-') as folder:
        root=Path(folder)
        source=root/'合成材料.txt'
        source.write_text('甲称已转款50000元。乙称用于代付运费，法律关系待核。员工解除日期未确定。',encoding='utf-8')
        async with client('server.py',root) as material:
            await call(material,'import_material',path=source.name)
            await call(material,'parse_material',path=source.name)
        async with client('business_server.py',root) as legal:
            for name in ('reception','contract','case','hearing','evidence'):
                method=await call(legal,'get_workflow',name=name)
                assert method['method'] and method['output_protocol']=='natural_language'
            for name in ('litigation','employment','corporate','compliance','ip'):
                denied_method=await legal.call_tool('get_workflow',{'name':name})
                assert denied_method.is_error
            case=await call(legal,'create_case',title='合成证据与劳动案')
            other=await call(legal,'create_case',title='隔离案')
            cid=case['id']
            await call(legal,'link_case_materials',case_id=cid,paths=[source.name])
            read=await call(legal,'read_case_material',case_id=cid,path=source.name)
            ref={'path':source.name,'quote':'甲称已转款50000元','sha256':read['sha256'],'chunk':0}
            issue={'proposition':'甲是否履行付款','finding_kind':'material_statement','assessment':'目前只有陈述，款项性质待核',
                   'supporting':[{'statement':'甲称已转款','speaker':'甲','carrier':'合成文本','citations':[ref]}],
                   'opposing':[],'unknown':['缺少流水'],'admissibility':{'authenticity':['核原始流水'],'legality':[],'relevance':['核款项性质']},'supplement':['补银行流水']}
            note=await call(legal,'save_evidence_analysis',case_id=cid,issues=[issue],request_id='evidence-1')
            assert note['id'] and note['citations'][0]['status']=='matched' and not note['legal_verified']
            denied=await legal.call_tool('save_evidence_analysis',{'case_id':other['id'],'issues':[issue]})
            assert denied.is_error
            labour=await call(legal,'save_employment_review',case_id=cid,stage='termination',findings=[{
                'fact':'解除日未确定','basis':'实际解除事件须核实','source':'合成材料',
                'risk':'不能用其他事件日期算工龄','action':'核送达与实际解除日','citations':[]}])
            assert labour['review_status']=='unverified'
            amount=await call(legal,'calculate_employment_amount',base='12345.67',years='3.5',multiplier='2',assumptions='仅按给定基数和年限作情景算术，不认定2N适用')
            assert amount['amount']=='86419.69' and not amount['legal_entitlement_verified']
            draft=await call(legal,'generate_litigation_document',case_id=cid,document_type='civil_complaint',filename='合成起诉草稿.docx',data={
                'facts':[{'text':'甲陈述已转款50000元，法律关系及用途待核。','citations':[ref]}]})
            assert Path(draft['path']).exists() and Path(draft['internal_path']).exists() and not draft['ready_to_submit']
            assert '法律关系及用途待核' in '\n'.join(p.text for p in Document(draft['path']).paragraphs)
            saved=await call(legal,'read_case_note',case_id=cid,note_id=note['id'])
            assert saved['content']==note['content']
    print(json.dumps({'passed':True,'transport':'real MCP stdio','model_requests':0,
        'checks':['four existing methods and released evidence method','five withheld methods rejected','source-bound evidence saved/read','cross-case refusal',
                  'employment review saved','Decimal scenario','actual Word + internal audit']},ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
