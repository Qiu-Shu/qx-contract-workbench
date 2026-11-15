import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const source=await readFile(new URL('./business-client.js',import.meta.url),'utf8');
function fixture(){
  const window={};vm.runInNewContext(source,{window});
  assert.equal(typeof window.qxCreateComparisonAnalysis,'function');
  const sent=[],context={activeId:'s',epoch:1,party:'乙方',running:false,input:{phase:'plain',draft:'',attachmentIds:[]},actions:{setDraft:text=>sent.push(['draft',text]),persistDraft:()=>sent.push(['persist']),submit:()=>sent.push(['submit'])}};
  return {sent,context,run:window.qxCreateComparisonAnalysis(()=>context)};
}
test('one explicit AI action reuses the saved party and submits once through the original input',async()=>{
  const f=fixture();let seen;
  await f.run('s',async party=>{seen=party;return '分析这两份版本'});
  assert.equal(seen,'乙方');assert.deepEqual(f.sent,[['draft','分析这两份版本'],['persist'],['submit']]);
});
for(const change of ['draft','attachment','navigation','party','running'])test('AI request preserves current work when '+change+' changes during version verification',async()=>{
  const f=fixture();let finish;const pending=f.run('s',()=>new Promise(resolve=>finish=resolve));
  if(change==='draft')f.context.input.draft='保留';
  if(change==='attachment')f.context.input.attachmentIds=['receipt'];
  if(change==='navigation')f.context.epoch++;
  if(change==='party')f.context.party='甲方';
  if(change==='running')f.context.running=true;
  finish('must not send');await assert.rejects(pending);assert.deepEqual(f.sent,[]);
});
test('existing drafts block preparation before reading files; simultaneous AI actions never send twice',async()=>{
  const f=fixture();f.context.input.draft='保留';await assert.rejects(f.run('s',()=>assert.fail('should not prepare')));f.context.input.draft='';
  let finish;const pending=f.run('s',()=>new Promise(resolve=>finish=resolve));
  await assert.rejects(f.run('s',()=>assert.fail('should not prepare twice')));finish('single');await pending;
  assert.equal(f.sent.filter(([kind])=>kind==='submit').length,1);
});
test('unknown party stays unknown and is resolved from the original conversation, without a new form',async()=>{
  const f=fixture();f.context.party='';let seen;await f.run('s',async party=>{seen=party;return '先核对原对话已确认立场'});assert.equal(seen,'');
});
