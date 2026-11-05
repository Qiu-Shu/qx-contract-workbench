// Offline replay of all paid delivery cases, plus the original observed 2028 failure.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {deliverProviderResponse} from './verified-delivery-harness.mjs';
const root=resolve(import.meta.dirname,'..');
const reportRoot=join(root,'docs/checks/skill-resume-20261105');
const files=[['delivery-v1-thinking','employment-final-known-net'],
 ...['employment-final-pre2008-repeat','lit-final-risk-repeat','corp-final-two-agendas-repeat','compliance-program-known-sent','ip-program-internal-vs-official-date'].map(id=>['delivery-v2-thinking',id])];
const hash=x=>createHash('sha256').update(x).digest('hex');
const rows=[];
let known;
for(const [run,id] of files){
 const path=join(root,'docs/checks/practice-gaps/e2e',run,id+'.json');
 const raw=await readFile(path),record=JSON.parse(raw);
 assert.equal(record.status,'completed');assert.equal(record.functionalPassed,true);assert.equal(record.verifiedDelivery,true);
 const messages=[{role:'user',content:record.scenario.prompt}];
 const workspace=join(root,'docs/checks/practice-gaps/e2e',run,id,'workspace');
 for(const round of record.rounds){
  if(!round.message.tool_calls?.length)break;
  messages.push({role:'assistant',...round.message});
  for(const t of round.toolResults||[])messages.push({role:'tool',tool_call_id:t.callId,content:JSON.stringify(t.result)});
 }
 const last=record.rounds.at(-1),result={choices:[{message:last.message,finish_reason:last.finishReason}],usage:last.usage};
 const replay=await deliverProviderResponse(messages,result,workspace);
 assert.equal(replay.protectedTurn,true);assert.equal(replay.text,record.response);
 assert.match(replay.text,/^以下说明由已保存成果生成/);assert.doesNotMatch(replay.text,/未能确认本轮/);
 assert.deepEqual(replay.message.content,last.delivery.message.content);
 assert.equal(replay.events[0].data.message.content[0].text,replay.text);
 const artifacts=[];
 for(const file of record.actual.drafts){
  assert.equal(hash(await readFile(file.path)),file.sha256);
  artifacts.push({path:file.path,sha256:file.sha256});
 }
 const links=[...replay.text.matchAll(/\]\(<([^>]+)>\)/g)].map(m=>decodeURI(m[1]));
 assert.ok(links.length>0);assert.ok(links.every(p=>artifacts.some(a=>a.path.replaceAll('\\','/')===p)));
 rows.push({id,run,input:path,sha256:hash(raw),protectedTurn:true,streamMatchesSavedSession:true,replayedResponseMatchesLive:true,
  artifactHashesMatch:true,linksMatchActualFiles:true,artifacts});
 if(id==='employment-final-known-net')known={messages,workspace};
}
const originalPath=join(root,'docs/checks/practice-gaps/e2e/program-v8-thinking/employment-final-known-net.json');
const originalRaw=await readFile(originalPath),original=JSON.parse(originalRaw);
assert.match(original.response,/2028/);
const repaired=await deliverProviderResponse(known.messages,{choices:[{message:{content:original.response},finish_reason:'stop'}]},known.workspace);
assert.doesNotMatch(JSON.stringify(repaired),/2028/);
assert.match(repaired.text,/已保存劳动解除条件清单/);
const report={scope:'Six paid synthetic cases; official LLM service and production stream plugin. Offline replay is not another paid model test or desktop UI acceptance.',
 rows,originalFailureReplay:{input:originalPath,sha256:hash(originalRaw),rawContains2028:true,visibleAndSavedExclude2028:true,output:repaired.text}};
await writeFile(join(reportRoot,'verified-delivery-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({paidCasesAudited:rows.length,originalFailureReplay:'pass'}));
