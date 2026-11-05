"""New source-bound methods must be usable through actual MCP, not only direct imports."""
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from docx import Document
from check_business_mcp import client, call


def test_mcp_describes_nested_brief_and_tracking_before_generation(tmp_path):
    async def run():
        async with client('business_server.py', tmp_path) as legal:
            tools = {t.name: t.input_schema for t in (await legal.list_tools()).tools}
            schema = tools['build_source_bound_litigation']
            assert 'LitigationBrief' in schema.get('$defs', {}), 'brief is an opaque dict; callers cannot locate calculation_index'
            assert 'calculation_index' in schema['$defs']['LitigationBrief']['properties']
            assert 'calculation_index' not in schema['$defs']['Money']['properties']
            denied = await legal.call_tool('build_source_bound_litigation', {
                'case_id': 'unused', 'document_type': 'civil_complaint', 'filename': 'bad.docx',
                'excerpts': [], 'brief': {'claim_amount': {'calculation_index': 0}}})
            assert denied.is_error
            assert not list(tmp_path.rglob('*.docx'))
            assert 'ComplianceTracking' in tools['save_source_bound_register'].get('$defs', {})
            employment_schema = tools['assess_employment_termination']['$defs']['MaterialCitation']
            assert employment_schema['additionalProperties'] is False
            assert set(employment_schema['required']) == {'path', 'quote', 'sha256', 'chunk'}
    asyncio.run(run())


def test_source_bound_tools_are_registered_and_case_scoped(tmp_path):
    async def run():
        text = '合同价款96000元，已收31000元。员工2024年入职，工资及解除日未提供。议题一三票赞成；议题二没有计票记录。参考日2026-11-05。意见截止2026-11-10。已发送，未提供受理回执。'
        source = tmp_path / '合成材料.txt'
        source.write_text(text, encoding='utf-8')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        async with client('server.py', tmp_path) as materials:
            await call(materials, 'import_material', path=source.name)
            await call(materials, 'parse_material', path=source.name)
        async with client('business_server.py', tmp_path) as legal:
            names = {t.name for t in (await legal.list_tools()).tools}
            assert {'build_source_bound_litigation', 'assess_employment_termination', 'save_source_bound_register'} <= names
            case = await call(legal, 'create_case', title='来源约束合成案')
            cid = case['id']
            await call(legal, 'link_case_materials', case_id=cid, paths=[source.name])
            ref = {'path': source.name, 'sha256': digest, 'chunk': 0, 'quote': text}
            draft = await call(legal, 'build_source_bound_litigation', case_id=cid,
                document_type='civil_complaint', filename='来源草稿.docx',
                excerpts=[{'section':'facts', 'citation':ref}], calculations=[{
                    'minuend': {'citation':ref, 'amount':'96000元'},
                    'subtrahends':[{'citation':ref, 'amount':'31000元'}]}],
                brief={'claim_kind':'payment','calculation_index':0})
            body = '\n'.join(p.text for p in Document(draft['path']).paragraphs)
            assert '65000' in body and '68000' not in body and text in body
            assert draft['ready_to_submit'] is False
            assert draft['completion_status']=='conditional_draft' and '拟请求' in body
            employment = await call(legal, 'assess_employment_termination', case_id=cid, citations=[ref])
            assert employment['id'] and employment['kind']=='employment_review'
            assert employment['user_summary'] and employment['source_contexts']
            assert employment['delivery']['case_id'] == cid
            assert employment['delivery']['notes'][0]['id'] == employment['id']
            assert len(employment['delivery']['notes'][0]['sha256']) == 64
            employment_doc = await call(legal, 'export_case', case_id=cid,
                note_ids=[employment['id']], filename='劳动一致性.docx')
            messages=[{'role':'user','content':'保存劳动初审并导出'}]
            for identifier, name, args, value in (
                ('review','assess_employment_termination',{'case_id':cid,'citations':[ref]},employment),
                ('export','export_case',{'case_id':cid,'note_ids':[employment['id']]},employment_doc)):
                messages.extend([{'role':'assistant','content':None,'tool_calls':[{'id':identifier,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},
                    {'role':'tool','tool_call_id':identifier,'content':json.dumps({'executed':True,'is_error':False,'result':value})}])
            root=Path(__file__).resolve().parents[1]
            checked=subprocess.run([
                'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe',
                str(root/'scripts/check_verified_delivery.mjs')],cwd=root,input=json.dumps({
                    'workspace':str(tmp_path),'messages':messages,
                    'result':{'choices':[{'message':{'content':'按2028年前后计算赔偿。'},'finish_reason':'stop'}]}}),
                text=True,encoding='utf-8',capture_output=True,check=True)
            delivered=json.loads(checked.stdout)
            assert '2028' not in json.dumps(delivered,ensure_ascii=False)
            assert employment['user_summary'] in delivered['text']
            assert '未能确认' not in delivered['text']
            assert '%E5%8A%B3%E5%8A%A8' in delivered['text']
            assert delivered['events'][0]['data']['message']['content'][0]['text']==delivered['text']
            register = await call(legal, 'save_source_bound_register', case_id=cid, domain='corporate',
                entries=[{'field':'votes', 'citation':ref}], document_type='minutes', filename='会议纪要正文.docx')
            assert register['id'] and register['kind']=='corporate_record_draft'
            assert register['user_summary'] and '会议纪要' in register['body_text']
            assert Path(register['path']).is_file()
            assert text in '\n'.join(p.text for p in Document(register['path']).paragraphs)
            doc = await call(legal, 'export_case', case_id=cid, note_ids=[register['id']], filename='台账.docx')
            assert text in '\n'.join(p.text for p in Document(doc['path']).paragraphs)
            assert doc['sha256'] == hashlib.sha256(Path(doc['path']).read_bytes()).hexdigest()
            assert doc['note_versions'][0]['id'] == register['id']
            tracked = await call(legal, 'save_source_bound_register', case_id=cid, domain='compliance',
                entries=[{'field':'feedback_deadline', 'citation':ref}],
                tracking={'as_of':'2026-11-05', 'as_of_entry':0,
                          'deadlines':[{'entry':0, 'date':'2026-11-10', 'year_basis':'explicit'}]})
            assert tracked['entries'][0]['field'] == 'source_excerpt'
            assert tracked['classification_audit'][0]['is_fact_field'] is False
            assert tracked['tracking']['deadlines'][0]['days_from_reference'] == 5
            tracking_doc = await call(legal, 'export_case', case_id=cid, note_ids=[tracked['id']], filename='合规跟踪.docx')
            tracking_text = '\n'.join(p.text for p in Document(tracking_doc['path']).paragraphs)
            assert '相差5个自然日' in tracking_text and '已发送，未提供受理回执' in tracking_text
            combined = await call(legal,'export_case',case_id=cid,
                                  note_ids=[register['id'],tracked['id']],filename='公司合规合并.docx')
            for identifier,name,args,value in (
                ('company','save_source_bound_register',{'case_id':cid,'domain':'corporate'},register),
                ('compliance','save_source_bound_register',{'case_id':cid,'domain':'compliance'},tracked),
                ('combined','export_case',{'case_id':cid,'note_ids':[register['id'],tracked['id']]},combined)):
                messages.extend([{'role':'assistant','tool_calls':[{'id':identifier,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},
                    {'role':'tool','tool_call_id':identifier,'content':json.dumps({'executed':True,'is_error':False,'result':value})}])
            checked=subprocess.run([
                'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe',str(root/'scripts/check_verified_delivery.mjs')],
                cwd=root,input=json.dumps({'workspace':str(tmp_path),'messages':messages,
                    'result':{'choices':[{'message':{'content':'只完成最后一份。'},'finish_reason':'stop'}]}}),
                text=True,encoding='utf-8',capture_output=True,check=True)
            delivered=json.loads(checked.stdout)
            for saved in [employment,register,tracked]:
                assert saved['user_summary'] in delivered['text']
            assert '%E5%85%AC%E5%8F%B8%E5%90%88%E8%A7%84%E5%90%88%E5%B9%B6.docx' in delivered['text']
            assert '%E5%8A%B3%E5%8A%A8' in delivered['text']
            assert '只完成最后一份' not in delivered['text']
            other = await call(legal, 'create_case', title='其他合成案')
            denied = await legal.call_tool('assess_employment_termination', {'case_id':other['id'], 'citations':[ref]})
            assert denied.is_error
            assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    asyncio.run(run())
