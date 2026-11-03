"""Real local files through the actual MCP stdio transport; no model requests."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def run():
    from PIL import Image,ImageDraw,ImageFont
    from docx import Document
    root=Path(__file__).resolve().parents[1]/'workspace';root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='.bridge-selfcheck-',dir=root) as temporary:
        work=Path(temporary).resolve();assert work.is_relative_to(root.resolve())
        clause='验收合格后十日内付款'
        (work/'sample.txt').write_text('字'*3995+clause+('虚构合同测试。\n'*1000),encoding='utf-8')
        document=Document();document.add_paragraph(clause);document.save(work/'sample.docx')
        image=Image.new('RGB',(1400,300),'white')
        ImageDraw.Draw(image).text((40,80),clause,font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',48),fill='black')
        image.save(work/'sample.png');image.save(work/'sample.pdf',save_all=True,append_images=[image.copy()])
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in work.iterdir() if p.is_file()}
        parameters=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).with_name('server.py')),'--workspace',str(work)],
                                         env={'PYTHONIOENCODING':'utf-8'})
        async with stdio_client(parameters) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                names=[t.name for t in tools.tools]
                assert len(names)==6,names
                async def call(name,**kwargs):
                    result=await session.call_tool(name,kwargs,read_timeout_seconds=120)
                    assert not result.is_error,(name,result)
                    value=result.structured_content
                    if value is None:value=json.loads(next(c.text for c in result.content if c.type=='text'))
                    assert 'error' not in value,(name,value)
                    return value
                listed=await call('list_materials');assert listed['total']==4
                for path in before:
                    await call('import_material',path=path)
                    parsed=await call('parse_material',path=path,page_count=1)
                    if path.endswith('.pdf'):
                        assert parsed['next_page']==2
                        parsed=await call('parse_material',path=path,start_page=2,page_count=1)
                        assert parsed['next_page'] is None
                    assert parsed['status']=='ready',(path,parsed)
                    readback=await call('read_material',path=path,limit=1)
                    assert readback['chunks']
                    found=await call('search_materials',query=clause,path=path)
                    assert found['matches'],(path,found)
                textpage=await call('read_material',path='sample.txt',limit=1)
                assert textpage['next_start']==1
                word=await call('write_word_draft',filename='review.docx',title='合同审查草稿',content='## 付款条款\n'+clause)
                output=Path(word['path']);assert output.is_file()
                assert clause in '\n'.join(p.text for p in Document(output).paragraphs)
                again=await call('write_word_draft',filename='review.docx',title='第二版草稿',content=clause)
                assert again['path']!=word['path']
                denied=await session.call_tool('import_material',{'path':'../outside.txt'})
                assert denied.is_error
                assert any('工作区' in c.text for c in denied.content if c.type=='text')
                after={name:hashlib.sha256((work/name).read_bytes()).hexdigest() for name in before}
                assert before==after
                result={'status':'passed','transport':'MCP stdio','tools':names,
                        'real_formats':['TXT','DOCX','two-page scanned PDF','Chinese PNG'],
                        'checks':['import','parse','resume PDF page batch','read pagination','full-text search',
                                  'actual DOCX output','no overwrite','workspace boundary','original hashes unchanged'],
                        'model_requests':0}
                Path(__file__).with_name('selfcheck-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
