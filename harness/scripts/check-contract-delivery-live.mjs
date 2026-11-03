// Synthetic end-to-end contract delivery. Never reads client files or sends WeChat messages.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
if(!process.argv.includes('--live'))throw Error('Use --live explicitly; the configured model is called.');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const python='D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe';
const stamp=new Date().toISOString().replaceAll(/[:.]/g,'-');
const out=path.join(root,'docs/checks/contract-delivery',stamp),materialDir=path.join(root,'workspace/checks/contract-delivery',stamp);
await fs.mkdir(out,{recursive:true});await fs.mkdir(materialDir,{recursive:true});
const source=path.join(materialDir,'合成采购合同.docx');
execFileSync(python,['-X','utf8','-c',`from docx import Document
import sys
d=Document()
for s in ['合成设备采购合同（仅用于软件验收）','甲方为合成买方，乙方为合成卖方，价款人民币10000元。','乙方应自合同签订日起30日内交付约定设备。','甲方应在收货当日支付全部价款。','设备规格、检验方法及验收标准由双方另行确认。','合同未记载双方实际付款或交货情况。']: d.add_paragraph(s)
d.save(sys.argv[1])`,source],{windowsHide:true});
const report={status:'running',scope:'file delivery; substantive content is reviewed separately',startedAt:new Date().toISOString(),source,sessionId:'qx-contract-delivery-'+randomUUID(),calls:[]};
const save=()=>fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
const runtime=JSON.parse((await fs.readFile(path.join(root,'.local/runtime.json'),'utf8')).replace(/^\uFEFF/,''));
const base=new URL(runtime.url).origin,auth=await fetch(runtime.url,{redirect:'manual'});
const cookie=auth.headers.getSetCookie().map(s=>s.split(';')[0]).join('; ');
async function rpc(method,request){
 const response=await fetch(base+'/api/'+method,{method:'POST',headers:{Origin:base,Cookie:cookie,'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:randomUUID(),method,payload:{args:{request}}}),signal:AbortSignal.timeout(45000)});
 assert.equal(response.status,200,method);const data=await response.json();assert.equal(data.result?.ok,true,method);return data.result.value;
}
try{
 report.sessionId=(await rpc('session/create',{sessionId:report.sessionId,cwd:path.join(root,'workspace'),agentPreset:'qunxing'})).sessionId;
 await rpc('session/rename',{sessionId:report.sessionId,title:'默认合同交付验收（虚构）'+stamp});await save();
 const before=await rpc('session/state',{sessionId:report.sessionId});
 await rpc('session/prompt',{sessionId:report.sessionId,requestId:randomUUID(),mode:'queue',clientTimeZone:'Asia/Shanghai',content:[{type:'text',text:`这是独立合成验收，只操作本次附件${source.replaceAll('\\','/')}以及本轮新建案件，题名为“默认合同交付验收（虚构）${stamp}”。我方是买方。请审查并修改这份合同，再形成可以阅读和编辑的正式意见书，重点只看付款与验收两个问题。请按工作台当前方法实际交付文件并保存意见。不要读取其他案件或真实资料，不联网，不委派其他Agent，不操作桌面或微信；无需引法条或判断效力。不要把约定当实际履行，不要自行补写尚未确认的设备规格。`} ]});
 let waited;
 for(let n=0;n<30;n++){
  waited=await rpc('session/wait',{sessionId:report.sessionId,afterSeq:before.cursor,timeoutMs:20000,maxMessages:50});
  console.log(JSON.stringify({state:waited.reason,cursor:waited.state?.cursor}));
  if(waited.reason==='input-required')throw Error('Unexpected request for input');
  if(waited.reason==='idle'&&waited.state.cursor>before.cursor)break;
 }
 assert.equal(waited?.reason,'idle');
 const page=await rpc('session/events',{address:{kind:'session',sessionId:report.sessionId},maxMessages:1000});
 const events=(page.records??page.entries??page.events??[]).map(row=>row.event??row);
 report.calls=events.filter(e=>e.type==='tool/call').map(e=>({callId:e.data.callId,name:e.data.name,arguments:e.data.arguments}));
 const toolValue=call=>{
  const message=events.find(e=>e.type==='tool/result'&&e.data.message?.toolCallId===call.callId)?.data.message;
  assert.ok(message&&!message.isError&&!message.is_error,'Tool did not succeed: '+call.name);
  return JSON.parse(message.content.filter(b=>b.type==='text').map(b=>b.text).join('\n'));
 };
 report.answer=events.filter(e=>e.type==='assistant/message').flatMap(e=>(e.data.message?.content??[]).filter(b=>b.type==='text').map(b=>b.text)).join('\n');
 for(const name of ['mcp__qx_materials__inspect_word_document','mcp__qx_materials__write_review_word','mcp__qx_materials__write_contract_opinion','mcp__qx_legal__record_case_note'])assert.ok(report.calls.some(c=>c.name===name),'Missing actual '+name);
 const reviews=report.calls.filter(c=>c.name==='mcp__qx_materials__write_review_word').map(c=>JSON.parse(c.arguments));
 assert.ok(reviews.every(c=>!c.mode||c.mode==='comments'),'Model selected tracked mode without a request');
 const writtenReviews=report.calls.filter(c=>c.name==='mcp__qx_materials__write_review_word').map(toolValue);
 assert.ok(writtenReviews.every(r=>r.applied>0&&r.failed===0));
 const evidence=execFileSync(python,['-X','utf8','-c',`import json,sys
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
source=Path(sys.argv[1]);root=Path(sys.argv[2]);calls=json.loads(sys.argv[3]);result=[]
with ZipFile(source) as z: original=''.join(E.fromstring(z.read('word/document.xml')).xpath('.//w:t/text()',namespaces=ns))
for c in calls:
 p=Path(c['path'])
 with ZipFile(p) as z:
  d=E.fromstring(z.read('word/document.xml'));comments=E.fromstring(z.read('word/comments.xml'))
  assert ''.join(d.xpath('.//w:t/text()',namespaces=ns))==original
  assert not d.xpath('.//w:ins|.//w:del',namespaces=ns)
  count=len(comments.xpath('./w:comment',namespaces=ns));assert count>0
 result.append({'path':str(p),'comments':count,'body_unchanged':True})
print(json.dumps(result,ensure_ascii=False))`,source,path.join(root,'workspace'),JSON.stringify(writtenReviews)],{encoding:'utf8',windowsHide:true});
 report.comments=JSON.parse(evidence);
 const opinion=toolValue(report.calls.findLast(c=>c.name==='mcp__qx_materials__write_contract_opinion'));
 report.opinion={html:opinion.html_path,word:opinion.word_path};
 for(const file of Object.values(report.opinion))assert.ok((await fs.stat(file)).size>0);
 report.status='passed';
}catch(error){report.status='failed';report.error=error.message;process.exitCode=1;}
report.finishedAt=new Date().toISOString();await save();console.log(JSON.stringify({status:report.status,error:report.error,report:path.join(out,'report.json')}));
