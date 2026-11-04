import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {WorkflowStore,instructionsFor,installWorkflows} from './business-workflows.mjs';

function fixture(t){const dir=mkdtempSync(join(tmpdir(),'qx-flow-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));return {dir,store:new WorkflowStore(dir)};}
test('mode persists across restart and cannot silently change an existing conversation',t=>{
  const {dir,store}=fixture(t);const a=store.update('session-a',{mode:'contract',revision:0});
  assert.equal(a.revision,1);assert.equal(new WorkflowStore(dir).get('session-a').mode,'contract');
  assert.throws(()=>store.update('session-a',{mode:'reception',revision:1}),/业务/);
  assert.equal(store.get('session-b'),null);assert.throws(()=>store.get('../outside'),/编号/);
});
test('contract waits for role and explicit review confirmation; focused review requires focus',t=>{
  const {store}=fixture(t);let a=store.update('contract',{mode:'contract',revision:0});
  assert.match(instructionsFor(a),/不得开始正式审查/);
  a=store.update('contract',{revision:a.revision,party:'乙方'});
  assert.match(instructionsFor(a),/不得开始正式审查/);
  assert.throws(()=>store.update('contract',{revision:a.revision,review:'focused',confirmed:true}),/重点/);
  a=store.update('contract',{revision:a.revision,review:'full',confirmed:true});
  assert.match(instructionsFor(a),/乙方/);assert.match(instructionsFor(a),/全面/);
  assert.doesNotMatch(instructionsFor(a),/不得开始正式审查/);
});
test('stale edits fail, signed engagement requires lawyer confirmation and survives restart',t=>{
  const {store}=fixture(t);store.update('reception',{mode:'reception',revision:0});
  assert.throws(()=>store.update('reception',{revision:0,stage:'quoted'}),/刷新/);
  assert.throws(()=>store.update('reception',{revision:1,stage:'engaged'}),/确认/);
  const state=store.update('reception',{revision:1,stage:'engaged',confirmEngagement:true});
  assert.equal(state.stage,'engaged');assert.ok(state.engagementConfirmedAt);
});
test('case handoff only accepts explicitly confirmed summary from a reception conversation',t=>{
  const {store}=fixture(t);store.update('source',{mode:'reception',revision:0});
  assert.throws(()=>store.update('case',{mode:'case',revision:0,sourceSessionId:'source',summary:'已确认的合同款争议'}),/确认/);
  const state=store.update('case',{mode:'case',revision:0,sourceSessionId:'source',summary:'已确认的合同款争议',confirmHandoff:true});
  assert.equal(state.summary,'已确认的合同款争议');assert.match(instructionsFor(state),/已确认的合同款争议/);
  assert.equal(store.get('source').summary,undefined);
  assert.throws(()=>store.update('other',{mode:'case',revision:0,sourceSessionId:'absent',summary:'摘要',confirmHandoff:true}),/来源/);
});
test('reception contains conversion goal and reply format; arbitrary input is rejected',t=>{
  const {store}=fixture(t);const state=store.update('reception',{mode:'reception',revision:0});
  const prompt=instructionsFor(state);assert.match(prompt,/推进咨询和委托/);assert.match(prompt,/【可发送回复】/);assert.match(prompt,/【律师参考】/);assert.match(prompt,/不得自动发送/);
  assert.throws(()=>store.update('reception',{revision:1,admin:true}),/字段/);
  assert.throws(()=>store.update('reception',{revision:1,party:'甲方'}),/合同/);
});
test('HTTP route accepts the advertised Chinese handoff length and rejects stale or untrusted writes',async t=>{
  const {dir}=fixture(t);let route,section;
  installWorkflows({effect:fn=>fn(),systemPrompt:{context:value=>{section=value;return()=>{}}},sessions:{get:id=>id==='missing'?undefined:{id}},connection:{fetch:{register:value=>route=value}}},{directory:dir});
  const send=(id,input,headers={'content-type':'application/json','x-qx-workflow':'1'})=>route.fetch(new Request('http://localhost/api/qx-business/state?sessionId='+id,{method:'POST',headers,body:JSON.stringify(input)}));
  assert.equal((await send('source',{mode:'reception',revision:0})).status,200);
  assert.equal((await send('case',{mode:'case',revision:0,sourceSessionId:'source',summary:'中'.repeat(12000),confirmHandoff:true})).status,200);
  assert.equal((await send('source',{revision:0,stage:'quoted'})).status,409);
  assert.equal((await send('source',{revision:1,stage:'quoted'},{'content-type':'application/json'})).status,415);
  assert.equal((await send('missing',{mode:'case',revision:0})).status,409);
  assert.match(section.text({agent:{session:{id:'source'}}}),/推进咨询和委托/);
  assert.equal(section.text({agent:{session:{id:'other'}}}),'');
  assert.equal(section.interpolate,false);
});
