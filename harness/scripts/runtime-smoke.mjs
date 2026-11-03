// Real local Harness RPC smoke. Synthetic materials only; never logs credentials.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const python='D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe';
const uploadOnly=process.argv.includes('--upload-only');
const resume=process.argv.slice(2).find(a=>!a.startsWith('--'));
const out=resume?path.dirname(path.resolve(resume)):path.join(root,'.local','smoke',new Date().toISOString().replaceAll(/[:.]/g,'-'));
const stamp=path.basename(out);
await fs.mkdir(out,{recursive:true});
const report=resume?JSON.parse(await fs.readFile(path.resolve(resume),'utf8')):{startedAt:new Date().toISOString(),sessionId:`qx-smoke-${randomUUID()}`,phases:[],uploads:[],status:'preparing'};
const cookie=new Map();let base;let authUrl;
const store=async()=>fs.writeFile(path.join(out,'result.json'),JSON.stringify(report,null,2));
function log(value){console.log(JSON.stringify(value));}
function captureCookies(response){for(const value of response.headers.getSetCookie()){const pair=value.split(';',1)[0];const at=pair.indexOf('=');cookie.set(pair.slice(0,at),pair.slice(at+1));}}
async function request(route,options={}){
  const url=new URL(route,base);if(url.origin!==base.origin)throw Error('cross-origin request refused');
  const headers={Origin:base.origin,Cookie:[...cookie].map(([k,v])=>`${k}=${v}`).join('; '),...options.headers};
  const response=await fetch(url,{...options,headers,redirect:'manual',signal:AbortSignal.timeout(options.timeout??650000)});
  captureCookies(response);return response;
}
async function rpc(method,args={},timeout=45000){
  const id=randomUUID();const response=await request(`/api/${method}`,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({type:'client-request',rpcId:id,method,payload:{args}}),timeout});
  if(!response.ok)throw Error(`RPC ${method} HTTP ${response.status}`);
  const envelope=await response.json();
  if(!envelope.result?.ok)throw Error(`RPC ${method}: ${envelope.result?.error?.code??'invalid response'}`);
  return envelope.result.value;
}
async function events(){const value=await rpc('session/events',{request:{address:{kind:'session',sessionId:report.sessionId},maxMessages:1000}});return (value.records??value.entries??value.events??[]).map(row=>row.event??row);}
function textOf(event){return (event.data?.message?.content??[]).filter(block=>block.type==='text').map(block=>block.text).join('\n');}
function describe(all){return all.map(event=>({seq:event.seq,type:event.type,
  ...(event.type==='tool/call'?{tool:event.data?.name}:{}),
  ...(event.type==='turn/end'?{reason:event.data?.reason}:{}),
  ...(event.data?.usage?{usage:event.data.usage}:{}),
  ...(event.type==='tool/result'?{isError:event.data?.message?.isError??event.data?.message?.is_error??!!event.data?.error}:{}),
  ...(event.type==='command/done'?{outcome:event.data?.outcome}:{}),
}));}
async function prompt(label,text,extra=[]){
  const before=await rpc('session/state',{request:{sessionId:report.sessionId}});
  const requestId=randomUUID();await rpc('session/prompt',{request:{requestId,sessionId:report.sessionId,mode:'queue',
    content:[{type:'text',text},...extra],clientTimeZone:'Asia/Shanghai'}});
  const start=Date.now();let wait;
  while(Date.now()-start<600000){
    wait=await rpc('session/wait',{request:{sessionId:report.sessionId,afterSeq:before.cursor,timeoutMs:20000,maxMessages:50}},30000);
    log({phase:label,state:wait.reason,cursor:wait.state?.cursor});
    if(wait.reason==='input-required')throw Error(`${label}: input-required`);
    if(wait.reason==='idle'&&wait.state?.cursor>before.cursor&&!wait.state?.queue?.length)break;
  }
  if(wait?.reason!=='idle'){await rpc('session/cancel',{request:{sessionId:report.sessionId}});throw Error(`${label}: cancelled after timeout`);}
  const all=await events();const current=all.filter(e=>e.seq>before.cursor);
  const phase={name:label,requestId,status:'completed',events:describe(current)};
  report.phases.push(phase);await store();
  const ended=current.filter(e=>e.type==='turn/end').at(-1);
  if(ended&&['error','failed','blocked'].includes(ended.data?.reason?.kind??ended.data?.reason))throw Error(`${label}: turn ${ended.data.reason}`);
  return {current,text:current.filter(e=>e.type==='assistant/message').map(textOf).join('\n')};
}
function verifiedUploadReads(current){
  const calls=current.filter(e=>e.type==='tool/call'&&e.data?.name==='mcp__qx_materials__read_material');
  return report.uploads.map(upload=>{
    const call=calls.find(e=>{try{return path.resolve(JSON.parse(e.data.arguments).path)===upload.path;}catch{return false;}});
    const result=call&&current.find(e=>e.type==='tool/result'&&e.data?.message?.toolCallId===call.data.callId);
    const blocks=result?.data?.message?.content??[];
    const text=blocks.filter(b=>b.type==='text').map(b=>b.text).join('\n');
    return {filename:upload.filename,path:upload.path,readVerified:!!result&&!result.data.message.isError&&text.includes('35000')};
  });
}
async function upload(filename,bytes){
  const response=await request('/api/session/uploadFileBinary?'+new URLSearchParams({sessionId:report.sessionId,name:filename}),
    {method:'POST',headers:{'Content-Type':'application/octet-stream'},body:bytes,timeout:60000});
  if(!response.ok)throw Error(`upload ${filename}: HTTP ${response.status}`);
  const body=await response.json();const value=body.value??body.result?.value;
  if(!body.ok||!value?.receiptId||!/^sha256:[a-f0-9]{64}$/.test(value.file?.attachmentId??''))throw Error(`upload ${filename}: ${body.error?.code??'no file receipt'}`);
  const digest=value.file.attachmentId.slice(7);
  const resolved=path.join(root,'workspace','inbox','.harness','attachments','v1','files',digest.slice(0,2),digest,value.file.name);
  if((await fs.stat(resolved)).size!==bytes.length)throw Error(`upload ${filename}: stored byte count mismatch`);
  if(!resolved.startsWith(path.join(root,'workspace')+path.sep))throw Error(`upload ${filename}: outside MCP workspace`);
  report.uploads.push({filename,receiptId:value.receiptId,path:resolved,bytes:bytes.length});return value;
}

try{
  const runtime=JSON.parse(await fs.readFile(path.join(root,'.local/runtime.json'),'utf8'));authUrl=new URL(runtime.url);base=new URL(authUrl.origin);
  let response=await request(authUrl.href);
  for(let count=0;count<3&&response.status>=300&&response.status<400;count++)response=await request(response.headers.get('location')??'/');
  if(response.status!==200)throw Error(`bootstrap HTTP ${response.status}`);
  if(!resume){
  const created=await rpc('session/create',{request:{sessionId:report.sessionId,cwd:path.join(root,'workspace'),agentPreset:'qunxing'}});
  report.sessionId=created.sessionId;await rpc('session/rename',{request:{sessionId:report.sessionId,title:`群兴合成运行验证 ${stamp}`}});
  }
  report.status='running';delete report.error;report.uploads=[];await store();log({sessionId:report.sessionId,status:'created'});
  if(!uploadOnly&&!report.phases.some(p=>p.name==='chat'&&p.status==='completed')){
  const chat=await prompt('chat','这是虚构材料的本机运行验证。请只回答：群兴运行正常。不要调用工具。');
  if(!chat.text.includes('群兴运行正常'))throw Error('chat: expected reply absent');
  }

  const fixtures=path.join(out,'fixtures');await fs.mkdir(fixtures,{recursive:true});
  const code=`from pathlib import Path\nfrom docx import Document\nfrom PIL import Image,ImageDraw,ImageFont\np=Path(${JSON.stringify(fixtures)})\ntext='虚构测试合同：甲方为买方，乙方为卖方。货款35000元，验收合格后十日内付款。违约责任未约定。'\n(p/'fixture.txt').write_text(text,encoding='utf-8')\nd=Document();d.add_paragraph(text);d.save(p/'fixture.docx')\nim=Image.new('RGB',(1400,300),'white');ImageDraw.Draw(im).text((40,80),'付款金额：35000元',font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',48),fill='black');im.save(p/'fixture.png')\n`;
  execFileSync(python,['-c',code],{windowsHide:true,stdio:'pipe'});
  const txt=await upload('qx-fixture.txt',await fs.readFile(path.join(fixtures,'fixture.txt')));
  const docx=await upload('qx-fixture.docx',await fs.readFile(path.join(fixtures,'fixture.docx')));
  // Upload PNG as a file for local OCR, not as multimodal input to a text-only model.
  const png=await upload('qx-fixture.png',await fs.readFile(path.join(fixtures,'fixture.png')));
  await store();
  const paths=report.uploads.map(x=>x.path.replaceAll('\\','/'));
  if(uploadOnly){
    const result=await prompt('official-upload-read',`只处理以下三份本轮正式上传的虚构附件。请分别使用qx_materials的import_material、parse_material、read_material读取每份，PNG使用本机OCR。只能访问以下精确路径，不使用list_materials、不搜索工作区、不读取其他路径、不联网、不委派Agent。不得根据提示猜内容，完成后用80字以内分别报告实际读到的金额。路径：\n${paths.join('\n')}`,[txt,docx,png].map(v=>({type:'file',receiptId:v.receiptId})));
    report.uploadReadEvidence=verifiedUploadReads(result.current);
    if(!report.uploadReadEvidence.every(v=>v.readVerified))throw Error('actual uploaded path read not verified');
    report.status='passed';report.finishedAt=new Date().toISOString();await store();log({status:'passed',sessionId:report.sessionId,report:path.join(out,'result.json'),officialUploads:3});
  }else{
  const filename=`qx-smoke-review-${stamp}.docx`;
  const legal=await prompt('legal-materials-word',`只处理本轮明确指定的三份虚构附件，不读取其他用户材料。请先选择并读取最匹配的中文合同审查Skill，再用qx_materials工具分别导入、解析并按需读取TXT、DOCX、PNG（PNG用本机OCR）。路径：\n${paths.join('\n')}\n从买方立场提出最多三条简短修改建议，核对金额为35000元、付款期限验收合格后十日。请用write_word_draft生成${filename}，标题“虚构合同审查草稿”，内容不超过500字；返回真实文件路径。不要联网，不要微信发送，不要扫描工作区其他文件，不要委派子Agent。尽量合并读取，完成后立即结束。`,[txt,docx,png].map(v=>({type:'file',receiptId:v.receiptId})));
  report.uploadReadEvidence=verifiedUploadReads(legal.current);
  if(!report.uploadReadEvidence.every(v=>v.readVerified))throw Error('actual uploaded path read not verified');
  const all=await events();const tools=all.filter(e=>e.type==='tool/call').map(e=>e.data?.name??'');
  report.observedTools=[...new Set(tools)];
  const drafts=await fs.readdir(path.join(root,'workspace','drafts'));
  const generated=drafts.find(name=>name===filename||name.startsWith(filename.slice(0,-5)+'-'));
  if(!generated)throw Error('legal: Word output missing');
  const wordPath=path.join(root,'workspace','drafts',generated);
  const wordText=execFileSync(python,['-c','from docx import Document; import sys; print("\\n".join(p.text for p in Document(sys.argv[1]).paragraphs))',wordPath],{encoding:'utf8',windowsHide:true});
  if(!wordText.includes('35000'))throw Error('legal: generated Word amount missing');
  report.word={path:wordPath,bytes:(await fs.stat(wordPath)).size,amountVerified:true};
  if(!tools.some(name=>/skill/i.test(name))||!tools.some(name=>/qx_materials|parse_material|read_material/i.test(name)))throw Error('legal: Skill or MCP calls absent');
  const compact=await rpc('commands/execute',{agentId:report.sessionId,line:'/compact',submittedAttachments:[]},650000);
  report.compaction={result:compact,events:describe((await events()).filter(e=>/compact|command\//.test(e.type)))};
  await store();
  if(!JSON.stringify(report.compaction).includes('Compacted'))throw Error('compact: no successful compaction outcome');
  const recalled=await prompt('post-compaction','只依据刚才已读取的虚构合同内容，回答金额和付款期限；不要重新读文件或调用工具。');
  report.recall={amount:recalled.text.includes('35000'),deadline:/十日|10\s*日|十天|10\s*天/.test(recalled.text)};
  if(!report.recall.amount||!report.recall.deadline)throw Error('post-compaction: key facts not recalled');
  report.status='passed';report.finishedAt=new Date().toISOString();await store();log({status:'passed',sessionId:report.sessionId,report:path.join(out,'result.json'),word:wordPath});
  }
}catch(error){
  report.status='failed';report.error=String(error.message).replaceAll(/(?:sk-|Bearer\s+)[A-Za-z0-9_-]+/g,'[redacted]');
  if(base){try{await rpc('session/cancel',{request:{sessionId:report.sessionId}});}catch{}}
  report.finishedAt=new Date().toISOString();await store();log({status:'failed',sessionId:report.sessionId,error:report.error,report:path.join(out,'result.json')});process.exitCode=1;
}
