// Explicit live validation. Synthetic materials only; never sends to WeChat.
import fs from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,join} from 'node:path';
import assert from 'node:assert/strict';

if(!process.argv.includes('--live'))throw Error('Use --live explicitly; calls the configured model.');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const runtime=JSON.parse(await fs.readFile(join(root,'.local/runtime.json'),'utf8'));
const origin=new URL(runtime.url).origin;
const auth=await fetch(runtime.url,{redirect:'manual'});
const cookie=auth.headers.getSetCookie().map(x=>x.split(';')[0]).join('; ');
async function rpc(method,request){
  const res=await fetch(origin+'/api/'+method,{method:'POST',headers:{Cookie:cookie,Origin:origin,'Content-Type':'application/json'},
    body:JSON.stringify({type:'client-request',rpcId:randomUUID(),method,payload:{args:{request}}}),signal:AbortSignal.timeout(30000)});
  assert.equal(res.status,200,method);const envelope=await res.json();assert.equal(envelope.result?.ok,true,method+': '+(envelope.result?.error?.code||''));return envelope.result.value;
}
const report={startedAt:new Date().toISOString(),sessions:[],status:'running'};
const out=join(root,'docs/checks/session-title',report.startedAt.replaceAll(/[:.]/g,'-'));
await fs.mkdir(out,{recursive:true});
const save=()=>fs.writeFile(join(out,'result.json'),JSON.stringify(report,null,2));
try{
  for(const topic of ['设备采购合同','拖欠工资劳动争议','商铺租赁合同']){
    const sessionId='qx-title-test-'+randomUUID();
    await rpc('session/create',{sessionId,cwd:join(root,'workspace'),agentPreset:'qunxing'});
    const row={sessionId,topic};report.sessions.push(row);await save();
    const uploaded=await fetch(origin+'/api/session/uploadFileBinary?'+new URLSearchParams({sessionId,name:'虚构材料.txt'}),{
      method:'POST',headers:{Cookie:cookie,Origin:origin,'Content-Type':'application/octet-stream'},body:Buffer.from('仅供功能验收的虚构材料：'+topic+'。不涉及真实当事人。')});
    assert.equal(uploaded.status,200);const upload=await uploaded.json();assert.ok(upload.value?.receiptId);
    await rpc('session/prompt',{sessionId,requestId:randomUUID(),mode:'queue',clientTimeZone:'Asia/Shanghai',
      content:[{type:'text',text:'虚构功能验收。请只回复“收到”。不调用任何工具，不读取其他文件，不联网，不委派，不发送微信。'},
        {type:'file',receiptId:upload.value.receiptId}]});
  }
  const deadline=Date.now()+150000;
  while(Date.now()<deadline){
    for(const row of report.sessions){
      const result=await rpc('session/events',{address:{kind:'session',sessionId:row.sessionId},maxMessages:100});
      const events=(result.records??result.events??[]).map(x=>x.event??x);
      const titles=events.filter(e=>e.type==='session/title');const last=titles.at(-1);
      row.title=last?.data.title;row.provider=last?.data.source.provider;
      row.titleRequests=events.filter(e=>e.type==='session/title-llm-request').length;
      row.done=events.some(e=>e.type==='turn/end');
    }
    await save();
    if(report.sessions.every(row=>row.provider==='qx-first-content-title'&&row.done))break;
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
  assert.ok(report.sessions.every(row=>row.provider==='qx-first-content-title'&&row.done),'all synthetic sessions must receive the new title provider');
  assert.equal(new Set(report.sessions.map(row=>row.title)).size,3);
  const expected=[/采购/,/工资|劳动/,/租赁/];
  report.sessions.forEach((row,index)=>assert.match(row.title,expected[index],row.topic));
  assert.ok(report.sessions.every(row=>row.titleRequests===1));
  report.status='passed';
}catch(error){report.status='failed';report.error=error.message;process.exitCode=1}
finally{
  for(const row of report.sessions){
    try{await rpc('workspace/archiveSession',{sessionId:row.sessionId,stopActivity:true});row.archived=true}
    catch{row.archived=false}
  }
  report.finishedAt=new Date().toISOString();await save();
  console.log(JSON.stringify({status:report.status,sessions:report.sessions,error:report.error,report:join(out,'result.json')}));
}
