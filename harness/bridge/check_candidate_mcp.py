"""Real stdio adapter roundtrip with synthetic files; no cloud/model requests."""
import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from docx import Document
from check_business_mcp import client, call


async def run():
    with TemporaryDirectory(prefix='qx-candidates-') as temporary:
        root = Path(temporary)
        template = root / '律所空白模板.docx'
        doc = Document()
        doc.sections[0].header.paragraphs[0].text = '虚构律所'
        doc.add_paragraph('委托人：{{ client_name }}')
        doc.add_paragraph('本次请求：{{ request }}')
        doc.save(template)
        original = hashlib.sha256(template.read_bytes()).hexdigest()
        material = root / '合成材料.txt'
        material.write_text('虚构合同：付款金额35000元，验收后支付。', encoding='utf-8')
        async with client('server.py', root) as materials:
            view = await call(materials, 'inspect_custom_word_template', path=template.name)
            assert set(view['variables']) == {'client_name', 'request'}
            result = await call(materials, 'render_custom_word_template', path=template.name,
                filename='模板生成稿.docx', source_sha256=view['source_sha256'],
                data={'client_name': '合成甲公司', 'request': '核对金额 <35000> & 来源'})
            generated = Document(result['path'])
            assert generated.sections[0].header.paragraphs[0].text == '虚构律所'
            assert '核对金额 <35000> & 来源' in '\n'.join(p.text for p in generated.paragraphs)
            missing = await materials.call_tool('render_custom_word_template', {'path':template.name,
                'filename':'缺字段.docx','source_sha256':view['source_sha256'],'data':{}})
            assert missing.is_error and not (root/'drafts/缺字段.docx').exists()
            assert hashlib.sha256(template.read_bytes()).hexdigest() == original
            await call(materials, 'import_material', path=material.name)
            await call(materials, 'parse_material', path=material.name)
        async with client('business_server.py', root) as legal:
            case = await call(legal, 'create_case', title='合成甲案')
            await call(legal, 'link_case_materials', case_id=case['id'], paths=[material.name])
            source = await call(legal, 'read_case_material', case_id=case['id'], path=material.name)
            grounded = await call(legal, 'ground_case_extractions', case_id=case['id'],
                path=material.name, source_sha256=source['sha256'], chunk=0,
                extractions=[{'label':'付款金额','quote':'付款金额35000元'},
                             {'label':'错误改写','quote':'付款金额36000元'}])
            assert [r['status'] for r in grounded['extractions']] == ['matched','unmatched']
            other = await call(legal, 'create_case', title='合成乙案')
            denied = await legal.call_tool('ground_case_extractions', {'case_id':other['id'],
                'path':material.name,'source_sha256':source['sha256'],'chunk':0,
                'extractions':[{'label':'金额','quote':'付款金额35000元'}]})
            assert denied.is_error
    print(json.dumps({'passed':True,'model_requests':0,'checks':[
        'real MCP tool registration and calls','docxtpl header/style and literal XML characters',
        'required template fields and original protection','LangExtract exact Chinese quote',
        'rejected changed amount','cross-case access denied']},ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(run())
