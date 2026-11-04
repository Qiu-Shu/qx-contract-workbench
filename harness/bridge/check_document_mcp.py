"""Real stdio integration for document delivery tools, synthetic material only."""
import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from docx import Document
from zipfile import ZipFile
from lxml import etree as ET
from check_business_mcp import client, call

async def main():
    with TemporaryDirectory(prefix='qx-docx-mcp-') as directory:
        workspace=Path(directory);source=workspace/'虚构合同.docx'
        doc=Document();doc.add_paragraph('合同总价10000元。');p=doc.add_paragraph();p.add_run('买方应在');p.add_run('交货当天');p.add_run('支付全部价款。');doc.save(source)
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        async with client('server.py',workspace) as session:
            names=[t.name for t in (await session.list_tools()).tools]
            assert {'inspect_word_document','write_review_word','write_contract_opinion',
                    'generate_document_from_template','inspect_custom_word_template',
                    'render_custom_word_template'} <= set(names),names
            view=await call(session,'inspect_word_document',path=source.name)
            paragraph=next(p for p in view['paragraphs'] if '交货当天' in p['text'])
            edits=[{'paragraph_id':paragraph['paragraph_id'],'old':'交货当天','new':'验收合格后十日内','comment':'将付款与验收结果关联。'}]
            result=await call(session,'write_review_word',path=source.name,filename='合同批注稿.docx',source_sha256=view['source_sha256'],edits=edits)
            assert result['applied']==1 and result['failed']==0 and Path(result['path']).exists(),result
            with ZipFile(result['path']) as package:
                ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                body=ET.fromstring(package.read('word/document.xml'))
                assert not body.xpath('.//w:ins|.//w:del',namespaces=ns)
                assert '交货当天' in ''.join(body.xpath('.//w:t/text()',namespaces=ns))
                assert '验收合格后十日内' in ''.join(ET.fromstring(package.read('word/comments.xml')).itertext())
            tracked=await call(session,'write_review_word',path=source.name,filename='明确要求的修订稿.docx',source_sha256=view['source_sha256'],edits=edits,mode='tracked_changes')
            assert tracked['mode']=='tracked_changes' and tracked['applied']==1
            opinion=await call(session,'write_contract_opinion',filename='合成审查意见',title='合成合同审查意见',subtitle='虚构验收 · 买方立场',sections=[{'heading':'审查结论','paragraphs':['先明确验收条件，再协商付款节点。']},{'heading':'逐条意见','table':{'headers':['优先级','位置及原文','问题与影响','我方建议'],'rows':[['优先协商','付款条款：交货当天','验收完成前支付全部价款。','建议验收合格后付款，期限由双方确认。']]}}])
            assert Path(opinion['html_path']).exists() and Path(opinion['word_path']).exists()
            catalog=await call(session,'list_document_templates')
            result=await call(session,'generate_document_from_template',template_id='evidence-table',filename='证据目录.docx',data={'title':'虚构案件证据目录','evidence':[{'name':'合同','content':'价款与付款条件','purpose':'证明双方付款约定','page_range':'待编页','source':'本次合成附件'}]})
            assert Path(result['path']).exists(),result
            assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    print(json.dumps({'passed':True,'tools':names,'checks':['real stdio schemas','paragraph readback','default comments preserve body','explicit tracked revision','HTML + Word opinion','template catalog','evidence Word','original unchanged']},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
