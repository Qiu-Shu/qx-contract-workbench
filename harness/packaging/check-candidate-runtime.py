"""Exercise packaged docxtpl and LangExtract through real MCP, without a model."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from docx import Document
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(sys.argv[1]).resolve()
REPORT = Path(sys.argv[2]).resolve()
WORK = ROOT / '.local' / ('candidate-runtime-' + uuid4().hex)
WORK.mkdir()
# Do not forward model keys, provider settings or the user's Python import path.
ENV = {k: v for k, v in os.environ.items()
       if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'PATH'}}
ENV.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
           PYTHONPATH=str(BUNDLE / 'legacy/src'), QX_LEGACY_ROOT=str(BUNDLE / 'legacy'))
PYTHON = BUNDLE / 'runtime/python/python.exe'


async def main():
    versions = json.loads(subprocess.check_output([
        str(PYTHON), '-c',
        "import json,importlib.metadata as m; print(json.dumps({n:m.version(n) for n in ['docxtpl','langextract']}))"
    ], cwd=WORK, env=ENV, text=True, encoding='utf-8', timeout=60))
    assert versions == {'docxtpl': '0.20.2', 'langextract': '1.7.1'}, versions
    report = {'bundle': str(BUNDLE), 'workspace': str(WORK), 'versions': versions,
              'no_model_request': True, 'calls': []}

    async def call(client, name, args, error=False):
        result = await client.call_tool(name, args)
        report['calls'].append({'tool': name, 'is_error': result.is_error,
                                'expected_error': error})
        assert result.is_error == error, (name, str(result))
        if not error:
            return json.loads(next(x.text for x in result.content if x.type == 'text'))

    template = WORK / '合成空白模板.docx'
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = '仅用于合成包验收'
    doc.add_paragraph('委托人：{{ client }}', style='Title')
    doc.save(template)
    original = hashlib.sha256(template.read_bytes()).hexdigest()
    material = WORK / '合成材料.txt'
    material.write_text('合成材料：价款35000元。重复。重复。', encoding='utf-8')

    params = StdioServerParameters(command=str(PYTHON),
        args=[str(BUNDLE / 'bridge/server.py'), '--workspace', str(WORK)], cwd=str(WORK), env=ENV)
    async with stdio_client(params) as streams:
        async with ClientSession(*streams, read_timeout_seconds=120) as client:
            await client.initialize()
            view = await call(client, 'inspect_custom_word_template', {'path': template.name})
            assert view['variables'] == ['client'] and view['source_sha256'] == original
            arguments = {'path': template.name, 'filename': '合成填充稿.docx',
                         'data': {'client': '甲 <乙> & 丙'}, 'source_sha256': original}
            first = await call(client, 'render_custom_word_template', arguments)
            second = await call(client, 'render_custom_word_template', arguments)
            assert first['path'] != second['path']
            generated = Path(first['path']).resolve()
            assert generated.is_relative_to(WORK)
            result_doc = Document(generated)
            assert result_doc.paragraphs[0].text == '委托人：甲 <乙> & 丙'
            assert result_doc.paragraphs[0].style.name == 'Title'
            assert result_doc.sections[0].header.paragraphs[0].text == '仅用于合成包验收'
            assert hashlib.sha256(template.read_bytes()).hexdigest() == original
            await call(client, 'render_custom_word_template',
                       {**arguments, 'source_sha256': '0' * 64}, error=True)
            for name in ('import_material', 'parse_material'):
                await call(client, name, {'path': material.name})
            report['docxtpl'] = {'passed': True, 'output': str(generated),
                'sha256': hashlib.sha256(generated.read_bytes()).hexdigest(),
                'source_unchanged': True, 'existing_output_preserved': True,
                'style_header_and_xml_characters_preserved': True, 'stale_version_rejected': True}

    params = StdioServerParameters(command=str(PYTHON),
        args=[str(BUNDLE / 'bridge/business_server.py'), '--workspace', str(WORK)], cwd=str(WORK), env=ENV)
    async with stdio_client(params) as streams:
        async with ClientSession(*streams, read_timeout_seconds=120) as client:
            await client.initialize()
            case = await call(client, 'create_case', {'title': '合成包验收甲案'})
            other = await call(client, 'create_case', {'title': '合成包验收乙案'})
            await call(client, 'link_case_materials', {'case_id': case['id'], 'paths': [material.name]})
            view = await call(client, 'read_case_material', {'case_id': case['id'], 'path': material.name})
            arguments = {'case_id': case['id'], 'path': material.name, 'source_sha256': view['sha256'],
                         'chunk': view['chunks'][0]['ordinal'], 'extractions': [
                             {'label': '价款', 'quote': '价款35000元'},
                             {'label': '不存在', 'quote': '价款90000元'},
                             {'label': '重复', 'quote': '重复'}]}
            grounded = await call(client, 'ground_case_extractions', arguments)
            assert [x['status'] for x in grounded['extractions']] == ['matched', 'unmatched', 'ambiguous']
            matched = grounded['extractions'][0]
            assert view['chunks'][0]['text'][matched['start']:matched['end']] == matched['quote']
            assert grounded['engine'] == 'langextract' and not grounded['legal_verified']
            await call(client, 'ground_case_extractions', {**arguments, 'case_id': other['id']}, error=True)
            assert hashlib.sha256(material.read_bytes()).hexdigest() == view['sha256']
            report['langextract'] = {'passed': True, 'mode': grounded['mode'],
                'statuses': [x['status'] for x in grounded['extractions']],
                'cross_case_rejected': True, 'source_unchanged': True,
                'matched_span_checked_against_actual_text': True}
    report['passed'] = True
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'report': str(REPORT), 'versions': versions}, ensure_ascii=False))


asyncio.run(main())
