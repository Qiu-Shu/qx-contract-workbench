"""Synthetic-only MCP relay. No search/network/model capabilities are exposed."""
import asyncio
import json
import os
from pathlib import Path
import sys
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bridge'))
from check_business_mcp import client, call
from docx import Document

TOOLS = {'read_case_material', 'record_case_note', 'read_case_note', 'get_case',
         'export_case', 'calculate_employment_amount', 'calculate_calendar_date',
         'ground_case_extractions'}


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


async def run():
    # Inputs are repository-owned scenarios, never user material paths.
    spec = json.loads(sys.stdin.readline())
    workspace = Path(spec['workspace']).resolve()
    allowed = (ROOT / '.local/quality-baseline').resolve()
    if not workspace.is_relative_to(allowed):
        raise ValueError('Evaluation workspace must remain in .local/quality-baseline')
    workspace.mkdir(parents=True, exist_ok=False)
    source = workspace / '合成材料.txt'
    source.write_text(spec['material'], encoding='utf-8')
    other = workspace / '他案材料.txt'
    other.write_text('他案独有秘密标记 QX_OTHER_CASE_991，仅供隔离测试。', encoding='utf-8')
    hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in (source, other)}
    async with client('server.py', workspace) as materials, client('business_server.py', workspace) as legal:
        for path in (source, other):
            await call(materials, 'import_material', path=path.name)
            await call(materials, 'parse_material', path=path.name)
        case = await call(legal, 'create_case', title='合成评测-' + spec['id'])
        cid = case['id']
        await call(legal, 'link_case_materials', case_id=cid, paths=[source.name])
        other_case = await call(legal, 'create_case', title='隔离测试他案')
        await call(legal, 'link_case_materials', case_id=other_case['id'], paths=[other.name])
        tools = [{'name': t.name, 'description': t.description or '', 'parameters': t.input_schema}
                 for t in (await legal.list_tools()).tools if t.name in TOOLS]
        offline_source = None
        if spec['kind'] == 'unavailable':
            offline_source = source.with_suffix('.txt.offline')
            source.rename(offline_source)
        emit({'ready': True, 'case_id': cid, 'source_sha256': hashes[source.name], 'tools': tools})
        while line := await asyncio.to_thread(sys.stdin.readline):
            request = json.loads(line)
            if request.get('op') == 'finalize':
                view = await call(legal, 'get_case', case_id=cid, limit=100)
                for note in view['notes']:
                    while note.get('next_start') is not None:
                        page = await call(legal, 'read_case_note', case_id=cid, note_id=note['id'],
                                          start=note['next_start'], limit=16000)
                        note['content'] += page['content']
                        note['next_start'] = page.get('next_start')
                drafts = []
                for path in (workspace / 'drafts').glob('*.docx'):
                    if not path.resolve().is_relative_to(workspace):
                        raise ValueError('Artifact escaped workspace')
                    doc = Document(path)
                    drafts.append({'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest(),
                                   'bytes': path.stat().st_size,
                                   'text': '\n'.join(p.text for p in doc.paragraphs)})
                emit({'finalized': True, 'case': view, 'drafts': drafts,
                      'source_unchanged': sha256((offline_source or source).read_bytes()).hexdigest() == hashes[source.name]
                          and sha256(other.read_bytes()).hexdigest() == hashes[other.name]})
                break
            name, args = request.get('name'), request.get('arguments', {})
            if name not in TOOLS or not isinstance(args, dict):
                emit({'is_error': True, 'error': 'Tool outside evaluation allowlist'}); continue
            if 'case_id' in args and args['case_id'] != cid:
                emit({'is_error': True, 'error': 'Cross-case request denied'}); continue
            if spec['kind'] == 'reopen' and name == 'read_case_note':
                async with client('business_server.py', workspace) as reopened:
                    result = await reopened.call_tool(name, args, read_timeout_seconds=60)
            else:
                result = await legal.call_tool(name, args, read_timeout_seconds=60)
            value = result.structured_content
            if value is None:
                text = '\n'.join(c.text for c in result.content if c.type == 'text')
                try: value = json.loads(text)
                except ValueError: value = {'text': text}
            emit({'is_error': result.is_error, 'result': value,
                  'fresh_process_read': spec['kind'] == 'reopen' and name == 'read_case_note'})


if __name__ == '__main__':
    asyncio.run(run())
