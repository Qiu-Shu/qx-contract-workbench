"""Portable MCP processes with synthetic files; no model or private account use."""
import asyncio,json,os,sys,hashlib
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=Path(sys.argv[1]).resolve()
WORK=ROOT/'.local/installer-check-文档'
WORK.mkdir(parents=True,exist_ok=True)
document=Document();document.add_paragraph('虚构安装验收：合同金额35000元，验收后十日内付款。');document.save(WORK/'虚构验收.docx')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(BUNDLE/'legacy/src'),QX_LEGACY_ROOT=str(BUNDLE/'legacy'),PYTHONIOENCODING='utf-8',BB_BROWSER_NODE=str(BUNDLE/'runtime/node.exe'),BB_BROWSER_CLI=str(BUNDLE/'browser/node_modules/bb-browser/dist/cli.js'))
async def main():
    report={}
    specs={
        'documents':('python',[str(BUNDLE/'bridge/server.py'),'--workspace',str(WORK)]),
        'legal':('python',[str(BUNDLE/'bridge/business_server.py'),'--workspace',str(WORK)]),
        'browser':('python',[str(BUNDLE/'bridge/browser.py')]),
        'scrapling':('scrapling',[str(BUNDLE/'python-tool.py'),'scrapling','mcp']),
        'windows':('windows',[str(BUNDLE/'python-tool.py'),'windows','serve','--transport','stdio']),
    }
    for name,(runtime,args) in specs.items():
        async with stdio_client(StdioServerParameters(command=str(BUNDLE/f'runtime/{runtime}/python.exe'),args=args,cwd=str(WORK),env=env)) as streams:
            async with ClientSession(*streams,read_timeout_seconds=120) as client:
                await client.initialize();tools=await client.list_tools()
                result={'tools':len(tools.tools)}
                if name=='documents':
                    def value(response):
                        assert not response.is_error,str(response)
                        return json.loads(next(block.text for block in response.content if block.type=='text'))
                    for tool,args in [('import_material',{'path':'虚构验收.docx'}),('parse_material',{'path':'虚构验收.docx'}),('read_material',{'path':'虚构验收.docx'})]:
                        response=await client.call_tool(tool,args)
                        assert not response.is_error,(tool,str(response))
                    assert '35000' in str(response)
                    saved=await client.call_tool('write_word_draft',{'filename':'虚构成果.docx','title':'安装验收','content':'虚构金额35000元，验收后十日内付款。'})
                    assert not saved.is_error,str(saved)
                    templates=await client.call_tool('list_document_templates',{})
                    assert not templates.is_error and 'complaint-loan' in str(templates),str(templates)
                    generated=await client.call_tool('generate_document_from_template',{'template_id':'complaint-loan','filename':'虚构模板验收.docx','data':{'parties':['虚构甲方与乙方'],'claims':['核对虚构款项'],'facts':['仅用于安装包测试。']}})
                    assert not generated.is_error,str(generated)
                    source=WORK/'虚构验收.docx';digest=hashlib.sha256(source.read_bytes()).hexdigest()
                    view=value(await client.call_tool('inspect_word_document',{'path':source.name}))
                    reviewed=value(await client.call_tool('write_review_word',{'path':source.name,'filename':'虚构批注验收.docx','source_sha256':view['source_sha256'],'edits':[{'paragraph_id':view['paragraphs'][0]['paragraph_id'],'old':'35000','new':'40000','comment':'纯虚构批注验证。'}]}))
                    assert reviewed['mode']=='comments' and reviewed['applied']==1 and reviewed['failed']==0
                    with ZipFile(reviewed['path']) as package:
                        body=ET.fromstring(package.read('word/document.xml'));namespace='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                        assert not list(body.iter(namespace+'ins')) and not list(body.iter(namespace+'del'))
                        assert '35000' in ''.join(body.itertext()) and '40000' in package.read('word/comments.xml').decode('utf-8')
                    opinion=value(await client.call_tool('write_contract_opinion',{'filename':'虚构意见验收','title':'纯虚构安装验收意见','sections':[{'heading':'结论','paragraphs':['仅用于验证文件生成。']},{'heading':'风险表','table':{'headers':['优先级','位置','影响','建议'],'rows':[['验收','虚构条款','测试','人工核对']]}}]}))
                    assert Path(opinion['html_path']).is_file() and Path(opinion['word_path']).is_file()
                    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
                    result.update(docxRead=True,wordDraft=True,templates=True,templateWord=True,defaultComments=True,originalUnchanged=True,htmlWordOpinion=True)
                elif name=='scrapling':
                    response=await client.call_tool('make_request',{'url':'https://example.com','extraction_type':'text','main_content_only':False,'timeout':25})
                    assert not response.is_error and 'Example Domain' in str(response)
                    result['publicFetch']=True
                elif name=='windows':
                    response=await client.call_tool('ControlStatus',{});assert not response.is_error
                    result['controlStatus']=True
                report[name]=result;print(json.dumps({name:result}),flush=True)
    report['noModelRequest']=True
    (ROOT/'docs/checks/installer/portable-tools.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
asyncio.run(main())
