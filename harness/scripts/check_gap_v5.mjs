// Read-only replay of the new paid case and previous six delivery fixtures.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {deliverProviderResponse} from './verified-delivery-harness.mjs';
const root=resolve(import.meta.dirname,'..'),out=join(root,'docs/checks/skill-resume-20261105');
const previous=JSON.parse(await readFile(join(out,'verified-delivery-audit.json'),'utf8'));
const paths=[...previous.rows.map(r=>r.input),join(root,'docs/checks/practice-gaps/e2e/gap-v5-thinking/employment-combined-scenarios.json')];
const hash=x=>createHash('sha256').update(x).digest('hex'),rows=[];
for(const path of paths){
 const bytes=await readFile(path),record=JSON.parse(bytes);
 assert.equal(record.functionalPassed,true);assert.equal(record.status,'completed');
 const messages=[{role:'user',content:record.scenario.prompt}];
 for(const round of record.rounds.slice(0,-1)){
  messages.push({role:'assistant',...round.message});
  for(const t of round.toolResults||[])messages.push({role:'tool',tool_call_id:t.callId,content:JSON.stringify(t.result)});
 }
 const last=record.rounds.at(-1),workspace=join(root,'docs/checks/practice-gaps/e2e',record.run,record.id,'workspace');
 const replay=await deliverProviderResponse(messages,{choices:[{message:last.message,finish_reason:last.finishReason}],usage:last.usage},workspace);
 assert.equal(replay.text,record.response);assert.equal(replay.protectedTurn,true);
 assert.equal(replay.events[0].data.message.content[0].text,replay.text);
 for(const file of record.actual.drafts)assert.equal(hash(await readFile(file.path)),file.sha256);
 if(record.id==='employment-combined-scenarios'){
  assert.equal(record.actual.case.notes.length,1);assert.equal(record.actual.drafts.length,1);
  for(const text of [record.response,record.actual.case.notes[0].content,record.actual.drafts[0].text]){
   for(const term of ['12345.67 × 3.5 × 2 = 86419.69','12345.67 × 3.5 × 1 = 43209.85','不相加'])assert.ok(text.includes(term),term);
  }
 }
 rows.push({id:record.id,report:path,reportSha256:hash(bytes),responseMatchesStoredSession:true,artifactsMatch:true,
  scope:record.id==='employment-combined-scenarios'?'new paid combined-scenario case':'offline replay of previous paid evidence; not a new model request'});
}
await writeFile(join(out,'gap-v5-runtime-audit.json'),JSON.stringify({rows},null,2)+'\n');
console.log(JSON.stringify({cases:rows.length,newPaidCases:1,previousOfflineReplays:6,passed:true}));
