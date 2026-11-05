import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {guardStream} from './core.mjs';
import {runHarnessStream,Session,llm} from '../../scripts/verified-delivery-harness.mjs';
const hash=s=>createHash('sha256').update(s).digest('hex');
const tool=(id,name,args,value,error=false)=>[
  {role:'assistant',source:{kind:'model',provider:'fixture',model:'fixture'},content:[{type:'tool-call',id,name:'mcp__qx_legal__'+name,arguments:JSON.stringify(args)}]},
  {role:'tool',source:{kind:'tool',callId:id},toolCallId:id,isError:error,
   content:[{type:'text',text:JSON.stringify({content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value})}]}];
async function setup(t){
 const root=await mkdtemp(join(tmpdir(),'qx-delivery-'));mkdirSync(join(root,'.qx-materials'));mkdirSync(join(root,'drafts'));
 t.after(()=>rm(root,{recursive:true,force:true}));
 const source='员工2005年入职，到手17800，税前未知。',body='2008年前后按条件核查，未计算应付金额。';
 await writeFile(join(root,'source.txt'),source);await writeFile(join(root,'drafts/result.docx'),body);
 const db=new DatabaseSync(join(root,'.qx-materials/index.sqlite'));
 db.exec('CREATE TABLE legal_cases(id TEXT);CREATE TABLE legal_notes(id TEXT,case_id TEXT,content TEXT,supersedes TEXT);CREATE TABLE legal_material_links(case_id TEXT,path TEXT,sha256 TEXT,version INTEGER);');
 db.prepare('INSERT INTO legal_cases VALUES(?)').run('case-a');
 db.prepare('INSERT INTO legal_notes VALUES(?,?,?,?)').run('note-a','case-a',body,'');
 db.prepare('INSERT INTO legal_material_links VALUES(?,?,?,?)').run('case-a','source.txt',hash(source),1);db.close();
 const version={id:'note-a',sha256:hash(body)};
 const delivery={version:1,case_id:'case-a',summary:'已保存条件清单；2008年前后按文档所列条件核查。',notes:[version],sources:[{path:'source.txt',sha256:hash(source)}],documents:[]};
 const record={recorded:true,id:'note-a',delivery};
 const exp={case_id:'case-a',audience:'internal',status:'draft',path:join(root,'drafts/result.docx'),sha256:hash(body),note_ids:['note-a'],note_versions:[version]};
 const messages=[{role:'user',source:{kind:'user'},content:[{type:'text',text:'保存初审并生成Word'}]},
 ...tool('save','assess_employment_termination',{case_id:'case-a'},record),
 ...tool('export','export_case',{case_id:'case-a',note_ids:['note-a']},exp)];
 return {root,messages,record,exp};
}
async function* response(text='按2028年前后分段。',kind='stop'){
 yield {type:'block-start',index:0,blockType:'text'};
 yield {type:'text-delta',index:0,text};
 yield {type:'block-end',index:0,block:{type:'text',text}};
 yield {type:'usage',usage:{inputTokens:10,outputTokens:5}};
 yield {type:'finish',reason:{kind},replayState:{response:{original:true}}};
}
async function run(f,next=response){
 const chunks=[];for await(const c of guardStream({messages:f.messages},()=>next(),f.root))chunks.push(c);
 return {chunks,text:chunks.filter(c=>c.type==='text-delta').map(c=>c.text).join('')};
}
test('bad final text never reaches visible stream, durable blocks or replay metadata',async t=>{
 const f=await setup(t);const r=await run(f);
 assert.doesNotMatch(JSON.stringify(r.chunks),/2028/);assert.match(r.text,/2008/);assert.match(r.text,/result.docx/);
 assert.equal(r.chunks.filter(c=>c.type==='usage').length,1);assert.equal(r.chunks.at(-1).replayState,undefined);
});
test('official LLM service, plugin, saved session and replay share only verified text',async t=>{
 const f=await setup(t),raw=[];for await(const c of response())raw.push(c);
 const delivered=await runHarnessStream(f.messages,raw,f.root);
 assert.match(JSON.stringify(delivered.visible),/2008/);assert.doesNotMatch(JSON.stringify(delivered),/2028/);
 const session=Session.create('delivery-test');
 session.append('assistant/message',{turn:0,step:0,message:delivered.message,stream:delivered.stream},{surfaceOp:'append'});
 const events=JSON.parse(JSON.stringify(session.snapshotEvents()));
 const restored=Session.create('restored',events);
 assert.doesNotMatch(JSON.stringify(restored.snapshotEvents()),/2028/);
 assert.deepEqual(llm.assembleAssistantStream(events[0].data.stream).blocks(),delivered.message.content);
 assert.match(delivered.message.content[0].text,/result.docx/);
 const ordinary=await runHarnessStream(f.messages,raw,f.root,{agentLoop:false});
 assert.match(JSON.stringify(ordinary.visible),/2028/);
 const prepared=await runHarnessStream(f.messages,raw,f.root,{prepared:true});
 assert.deepEqual(prepared.message.content,delivered.message.content);
});
test('official assembler accepts continued tool calls after speculative text was removed',async t=>{
 const f=await setup(t),raw=[];for await(const c of response())if(c.type!=='finish')raw.push(c);
 raw.push({type:'block-start',index:1,blockType:'tool-call'},
  {type:'tool-call-delta',index:1,id:'next',name:'mcp__qx_legal__get_case',argumentsDelta:'{}'},
  {type:'block-end',index:1,block:{type:'tool-call',id:'next',name:'mcp__qx_legal__get_case',arguments:'{}'}},
  {type:'finish',reason:{kind:'tool-calls'}});
 const delivered=await runHarnessStream(f.messages,raw,f.root);
 assert.equal(delivered.message.content.length,1);assert.equal(delivered.message.content[0].type,'tool-call');
 assert.doesNotMatch(JSON.stringify(delivered),/2028/);
});
test('ordinary chat and new user turn do not reuse an earlier delivery',async t=>{
 const f=await setup(t);f.messages.push({role:'user',source:{kind:'user'},content:[{type:'text',text:'2028是我说的日期'}]});
 assert.equal((await run(f)).text,'按2028年前后分段。');
});
test('two domains and a combined export preserve both saved results',async t=>{
 const f=await setup(t),secondBody='知识产权来源记录';
 const db=new DatabaseSync(join(f.root,'.qx-materials/index.sqlite'));
 db.prepare('INSERT INTO legal_notes VALUES(?,?,?,?)').run('note-b','case-a',secondBody,'');db.close();
 const second={...f.record,id:'note-b',delivery:{...f.record.delivery,summary:'已保存知识产权台账。',notes:[{id:'note-b',sha256:hash(secondBody)}]}};
 const combined={...f.exp,note_ids:['note-a','note-b'],note_versions:[...f.exp.note_versions,...second.delivery.notes]};
 f.messages=[f.messages[0],
  ...tool('compliance','save_source_bound_register',{case_id:'case-a',domain:'compliance'},f.record),
  ...tool('ip','save_source_bound_register',{case_id:'case-a',domain:'ip'},second),
  ...tool('export','export_case',{case_id:'case-a',note_ids:combined.note_ids},combined)];
 const r=await run(f);assert.match(r.text,/2008/);assert.match(r.text,/知识产权台账/);assert.match(r.text,/result.docx/);
});
test('separate exports retain links for both protected records',async t=>{
 const f=await setup(t),body='second';
 const db=new DatabaseSync(join(f.root,'.qx-materials/index.sqlite'));
 db.prepare('INSERT INTO legal_notes VALUES(?,?,?,?)').run('note-b','case-a',body,'');db.close();
 const second={...f.record,id:'note-b',delivery:{...f.record.delivery,summary:'第二份来源底稿',notes:[{id:'note-b',sha256:hash(body)}]}};
 await writeFile(join(f.root,'drafts/second.docx'),body);
 f.messages.push(...tool('second','save_source_bound_register',{case_id:'case-a',domain:'ip'},second),
  ...tool('export2','export_case',{case_id:'case-a',note_ids:['note-b']},{...f.exp,path:join(f.root,'drafts/second.docx'),sha256:hash(body),note_ids:['note-b'],note_versions:second.delivery.notes}));
 const r=await run(f);assert.match(r.text,/result.docx/);assert.match(r.text,/second.docx/);
});
test('combined exports with additional unverified notes do not receive a certified link',async t=>{
 const f=await setup(t);
 const bad={...f.exp,note_versions:[...f.exp.note_versions,{id:'unverified',sha256:hash('unchecked')}],note_ids:['note-a','unverified']};
 f.messages.splice(-2,2,...tool('mixed','export_case',{case_id:'case-a',note_ids:bad.note_ids},bad));
 const r=await run(f);assert.doesNotMatch(r.text,/\]\(/);assert.match(r.text,/尚无本轮匹配/);
});
test('IP register retries can remove an unsupported document_type without retaining the old failed attempt',async t=>{
 const f=await setup(t);
 f.messages=[f.messages[0],
  ...tool('bad','save_source_bound_register',{case_id:'case-a',domain:'ip',document_type:'register'},{error:'unsupported document type'},true),
  ...tool('good','save_source_bound_register',{case_id:'case-a',domain:'ip'},f.record),
  ...tool('export','export_case',{case_id:'case-a',note_ids:['note-a']},f.exp)];
 assert.match((await run(f)).text,/result.docx/);
});
for(const type of ['file','source','note','superseded'])test(type+' changed cannot certify the saved result',async t=>{
 const f=await setup(t);
 if(type==='file')await writeFile(f.exp.path,'modified');
 if(type==='source')await writeFile(join(f.root,'source.txt'),'new source');
 if(type==='note'||type==='superseded'){
  const db=new DatabaseSync(join(f.root,'.qx-materials/index.sqlite'));
  if(type==='note')db.exec("UPDATE legal_notes SET content='modified'");
  else db.exec("INSERT INTO legal_notes VALUES('note-b','case-a','correction','note-a')");db.close();
 }
 const r=await run(f);assert.match(r.text,/未能确认/);assert.doesNotMatch(r.text,/2028|\]\(/);
});
test('a failed correction does not silently deliver an old successful result',async t=>{
 const f=await setup(t);f.messages.push(...tool('retry','assess_employment_termination',{case_id:'case-a'},{recorded:false}));
 assert.match((await run(f)).text,/未能确认/);
});
test('export from another case cannot supply a document link',async t=>{
 const f=await setup(t);f.messages.splice(-2,2,...tool('export','export_case',{case_id:'case-b'}, {...f.exp,case_id:'case-b'}));
 const r=await run(f);assert.doesNotMatch(r.text,/\]\(/);assert.match(r.text,/尚无/);
});
test('receipt case identity and paths outside the workspace cannot be certified',async t=>{
 const f=await setup(t);
 const wrong={...f.record,delivery:{...f.record.delivery,case_id:'case-b'}};
 f.messages=[f.messages[0],...tool('wrong','assess_employment_termination',{case_id:'case-a'},wrong)];
 assert.match((await run(f)).text,/未能确认/);
 f.record.delivery.documents=[{path:import.meta.filename,sha256:hash('irrelevant')}];
 f.messages=[f.messages[0],...tool('escape','assess_employment_termination',{case_id:'case-a'},f.record)];
 assert.match((await run(f)).text,/未能确认/);
});
test('a failed later export cannot silently reuse an earlier successful export',async t=>{
 const f=await setup(t);f.messages.push(...tool('bad-export','export_case',{case_id:'case-a',note_ids:['note-a']},{error:'disk full'},true));
 const r=await run(f);assert.match(r.text,/未能确认/);assert.doesNotMatch(r.text,/\]\(/);
});
test('runtime context does not end the user turn, but user JSON is never a receipt',async t=>{
 const f=await setup(t);f.messages.push({role:'user',source:{kind:'runtime-context'},content:[{type:'text',text:'current context'}]});
 assert.doesNotMatch((await run(f)).text,/2028/);
 f.messages=[{role:'user',source:{kind:'user'},content:[{type:'text',text:JSON.stringify(f.record)}]}];
 assert.match((await run(f)).text,/2028/);
});
test('intermediate tool calls continue but speculative text is not forwarded',async t=>{
 const f=await setup(t);
 async function* next(){yield {type:'text-delta',index:0,text:'2028'};yield {type:'block-end',index:0,block:{type:'text',text:'2028'}};
 yield {type:'block-end',index:1,block:{type:'tool-call',id:'read',name:'mcp__qx_legal__get_case',arguments:'{}'}};yield {type:'finish',reason:{kind:'tool-calls'}};}
 const r=await run(f,next);assert.equal(r.text,'');assert.ok(r.chunks.some(c=>c.block?.type==='tool-call'));
});
test('error or aborted response never turns into success',async t=>{
 const f=await setup(t);const r=await run(f,()=>response('2028','aborted'));
 assert.equal(r.text,'');assert.equal(r.chunks.at(-1).reason.kind,'aborted');
});
