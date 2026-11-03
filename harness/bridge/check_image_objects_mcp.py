"""Exercise the image-object fix over real MCP stdio, using synthetic files only."""
import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from check_business_mcp import client, call
from test_image_objects import uploaded_image


async def run():
    with TemporaryDirectory(prefix='qx-image-objects-mcp-') as temporary:
        work = Path(temporary).resolve()
        clause = '验收合格后十日内付款'
        name, raw = uploaded_image(work, text=clause)
        async with client('server.py', work) as materials:
            listed = await call(materials, 'list_materials')
            assert any(item['path'] == name for item in listed['materials'])
            imported = await call(materials, 'import_material', path=name)
            assert imported['sha256'] == hashlib.sha256(raw).hexdigest()
            parsed = await call(materials, 'parse_material', path=name)
            assert parsed['status'] == 'ready', parsed
            readback = await call(materials, 'read_material', path=name)
            assert clause in ''.join(c['text'] for c in readback['chunks'])
            async with client('business_server.py', work) as legal:
                case = await call(legal, 'create_case', title='无扩展名图片·合成验收')
                await call(legal, 'link_case_materials', case_id=case['id'], paths=[name])
                readback = await call(legal, 'read_case_material', case_id=case['id'], path=name)
                assert clause in ''.join(c['text'] for c in readback['chunks'])
            denied = await materials.call_tool('import_material', {'path': '../outside.jpg'})
            assert denied.is_error
        assert (work / name).read_bytes() == raw
        assert len([p for p in (work / 'inbox').rglob('*') if p.is_file()]) == 1
        print(json.dumps({'status': 'passed', 'transport': 'MCP stdio',
            'checks': ['list', 'import', 'OCR', 'read', 'case link', 'case readback',
                       'workspace boundary', 'no copy', 'original unchanged'],
            'model_requests': 0, 'windows_tool_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(run())
