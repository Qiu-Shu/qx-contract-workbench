// Explicit live check: synthetic cases only, no WeChat delivery or real client files.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';

if(!process.argv.includes('--live'))throw Error('Use --live explicitly; this check calls the configured model.');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const stamp=new Date().toISOString().replaceAll(/[:.]/g,'-');
const title=`四业务验证-${stamp}（虚构）`;
const reportDir=path.join(root,'docs/checks/legal-workflows',stamp);
const sampleDir=path.join(root,'workspace','checks',`legal-${stamp}`);
await fs.mkdir(reportDir,{recursive:true});await fs.mkdir(sampleDir,{recursive:true});
const sample=path.join(sampleDir,'虚构采购合同.txt');
await fs.writeFile(sample,'虚构设备采购合同\n甲方：晨舟公司（买方）；乙方：远澜公司（卖方）。\n2026年10月2日双方签署合同。总价35000元，约定预付款5000元，余款验收合格后十日内支付。\n乙方应在2026年10月7日交货；验收标准和验收程序未约定。\n违约责任、争议解决条款未约定。本文件没有实际付款凭证或验收记录。\n','utf8');
const report={startedAt:new Date().toISOString(),sessionId:`qx-legal-live-${randomUUID()}`,title,phases:[],status:'running'};
const save=()=>fs.writeFile(path.join(reportDir,'report.json'),JSON.stringify(report,null,2));
const runtime=JSON.parse((await fs.readFile(path.join(root,'.local/runtime.json'),'utf8')).replace(/^\uFEFF/,''));
const base=new URL(runtime.url).origin;
const auth=await fetch(runtime.url,{redirect:'manual'});
const cookie=auth.headers.getSetCookie().map(v=>v.split(';')[0]).join('; ');
async function rpc(method,request){
  const response=await fetch(`${base}/api/${method}`,{method:'POST',headers:{Origin:base,Cookie:cookie,'Content-Type':'application/json'},
    body:JSON.stringify({type:'client-request',rpcId:randomUUID(),method,payload:{args:{request}}}),signal:AbortSignal.timeout(45000)});
  assert.equal(response.status,200,method);const envelope=await response.json();
  assert.equal(envelope.result?.ok,true,method);return envelope.result.value;
}
const constraints='这是独立虚构验收，只操作本次明确创建的案件与指定附件。可以读取业务Skill及其方法；不得读取其他案件或材料，不联网、不委派其他Agent、不操作桌面、不向微信发送。无需引用法律条文。不要向操作者补问测试中已明确的信息。';
async function prompt(label,text,required=[]){
  const before=await rpc('session/state',{sessionId:report.sessionId});
  const requestId=randomUUID();
  await rpc('session/prompt',{requestId,sessionId:report.sessionId,mode:'queue',content:[{type:'text',text:constraints+text}],clientTimeZone:'Asia/Shanghai'});
  const until=Date.now()+900000;let completed=false;
  while(Date.now()<until){
    const wait=await rpc('session/wait',{sessionId:report.sessionId,afterSeq:before.cursor,timeoutMs:20000,maxMessages:100});
    console.log(JSON.stringify({phase:label,state:wait.reason,cursor:wait.state?.cursor}));
    if(wait.reason==='input-required')throw Error(`${label}: unexpected input request`);
    if(wait.reason==='idle'&&wait.state?.cursor>before.cursor&&!wait.state?.queue?.length){completed=true;break;}
  }
  if(!completed){await rpc('session/cancel',{sessionId:report.sessionId});throw Error(`${label}: timed out, cancelled only this synthetic session`);}
  const history=await rpc('session/events',{address:{kind:'session',sessionId:report.sessionId},maxMessages:2000});
  const events=(history.records??history.events??[]).map(r=>r.event??r).filter(e=>e.seq>before.cursor);
  const calls=events.filter(e=>e.type==='tool/call').map(e=>({name:e.data.name,arguments:e.data.arguments}));
  const textOf=e=>(e.data?.message?.content??[]).filter(b=>b.type==='text').map(b=>b.text).join('\n');
  const answer=events.filter(e=>e.type==='assistant/message').map(textOf).join('\n');
  const errors=events.filter(e=>e.type==='tool/result'&&(e.data?.message?.isError||e.data?.message?.is_error));
  report.phases.push({label,requestId,answer,calls,toolErrors:errors.length});await save();
  for(const tool of required)assert.ok(calls.some(c=>c.name===tool),`${label}: missing actual ${tool}`);
  assert.ok(answer.trim(),`${label}: no visible answer`);
  return answer;
}
function inspect(){
  const code=`import sqlite3,json,sys\nfrom pathlib import Path\nc=sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row\ncases=[dict(r) for r in c.execute('SELECT id,title FROM legal_cases WHERE title=?',(sys.argv[2],))]\nr={'cases':cases,'notes':[],'hearings':[]}\nfor v in cases:\n r['notes'] += [dict(n) for n in c.execute('SELECT id,kind,supersedes,length(content) AS characters,verification FROM legal_notes WHERE case_id=?',(v['id'],))]\n for h in c.execute('SELECT id FROM legal_hearings WHERE case_id=?',(v['id'],)):\n  turns=[dict(t) for t in c.execute('SELECT seq,stage,role,length(text) AS characters FROM legal_hearing_turns WHERE hearing_id=? ORDER BY seq',(h['id'],))];r['hearings'].append({'id':h['id'],'turns':turns})\nprint(json.dumps(r,ensure_ascii=False))`;
  return JSON.parse(execFileSync('D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe',
    ['-X','utf8','-c',code,path.join(root,'workspace/.qx-materials/index.sqlite'),title],{encoding:'utf8',windowsHide:true}));
}
try{
  const created=await rpc('session/create',{sessionId:report.sessionId,cwd:path.join(root,'workspace'),agentPreset:'qunxing'});report.sessionId=created.sessionId;
  await rpc('session/rename',{sessionId:report.sessionId,title});await save();
  if(process.argv.includes('--reception-only')){
    await prompt('reception-boundary','这是一个新咨询，不建案、不保存或导出文件。客户微信说：“设备买卖合同我晚上发你，对方今天催我付尾款，怎么办？”请只给一段能直接转发的简短微信回复。');
    report.status='passed';
  }else if(process.argv.includes('--reasoning-boundaries')){
    await prompt('contract-boundary','这是短条款解释，不建案、不保存或导出。虚构采购合同未约定违约责任和争议解决条款，这说明什么？只给两三句。');
    await prompt('hearing-boundary','只做一次独立的短角色练习，不启动完整演练、不建案、不记录。合同写10月7日交货、余款验收合格后十日内付，客户只说已付5000元，其他履行材料均未提供。请加载庭审方法，以卖方/被告角色针对尾款提出两三句有用的回应。');
    report.status='passed';
  }else{
  await prompt('reception',`请持续接待并建档，案件题名必须逐字为“${title}”，我方为晨舟公司买方。客户原话：“我买设备签了合同，暂时还没付款，供应商催我付尾款。我想先让律师看看合同，晚上给你。”请保存这段原话，生成可直接微信转发的回复，并将客户回复与必要内部底稿分开保存。回复简短即可。`,
    ['mcp__qx_legal__create_case','mcp__qx_legal__record_case_note','mcp__qx_legal__record_reception']);
  let state=inspect();assert.equal(state.cases.length,1);report.caseId=state.cases[0].id;
  for(const kind of ['consultation','client_reply','internal_note'])assert.ok(state.notes.some(n=>n.kind===kind),`reception note ${kind} absent`);
  await prompt('contract',`同一案件${report.caseId}。客户明确更正先前的“没付款”：已付5000元，但凭证还没提供。请保留旧原话并关联更正。仅审这份本轮附件：${sample.replaceAll('\\','/')}。请实际导入解析并关联本案，从买方立场审查付款与验收，最多提三项主要问题，区分付款约定与实际履行，给出替换条款及待补材料。保存审查意见并生成包含已保存意见的Word工作稿。`,
    ['mcp__qx_materials__import_material','mcp__qx_materials__parse_material','mcp__qx_legal__link_case_materials','mcp__qx_legal__record_case_note','mcp__qx_legal__export_case']);
  state=inspect();assert.ok(state.notes.some(n=>n.supersedes),'correction did not preserve source relationship');
  assert.ok(state.notes.some(n=>n.kind==='contract_review'),'no saved contract review');
  await prompt('case',`同一案件${report.caseId}，请根据已读的本轮合同和客户陈述整理简短时间线、争点、证据缺口，明确“约定10月7日交货”不等于实际交货。保存timeline和待办，不编造案号或诉讼状态。`,
    ['mcp__qx_legal__record_case_note']);
  await prompt('hearing',`同一案件${report.caseId}，现在做一次完整的虚构民事一审演练，我方为原告，争点为余款支付条件及验收。加载群兴庭审方法，创建演练，按工具实际next_stage/next_role把五阶段顺序做完；每个角色发言一两句即可，逐条实际保存，不把双方模拟说法当证据。复盘列出待补材料，不预测胜诉率。最后回读完整记录确认已完成。`,
    ['mcp__qx_legal__start_hearing','mcp__qx_legal__record_hearing_turn','mcp__qx_legal__get_hearing']);
  report.persisted=inspect();
  assert.equal(report.persisted.hearings.length,1);assert.equal(report.persisted.hearings[0].turns.length,11);
  assert.ok(report.persisted.notes.some(n=>n.kind==='timeline'));
  report.status='passed';
  }
}catch(error){report.status='failed';report.error=error.message;process.exitCode=1;}
report.finishedAt=new Date().toISOString();await save();
console.log(JSON.stringify({status:report.status,report:path.join(reportDir,'report.json'),error:report.error,caseId:report.caseId}));
