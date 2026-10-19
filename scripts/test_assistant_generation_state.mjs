import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';

const copy = value => structuredClone(value);
const sha = value => createHash('sha256').update(value).digest('hex');
const tick = () => new Promise(resolve => setImmediate(resolve));
const failure = (status=0, code='NETWORK_UNKNOWN') => Object.assign(new Error(code), {status,code});
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes,no) => {resolve=yes;reject=no;});
  return {promise,resolve,reject};
}
function snapshot(id='one',text='',revision=0) {
  return {scope:{workspace_id:'workspace',conversation_id:id,scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0},composer_revision:revision,
  draft_input:text,messages:[],next_before:null,latest_run:null};
}
function fixture({initial=snapshot(),readonly=false,capability='ready'}={}) {
  let remote=copy(initial), sequence=0, mode=capability;
  const calls=[], attempts=new Map(), byRequest=new Map(), messages=new Map();
  let materials={items:[],attachments:[]};
  const api={
    async createConversation(body) {calls.push(['create',copy(body)]);return copy(remote);},
    async getConversation(id,before) {calls.push(['get',id,before]);return copy(remote);},
    async getMaterials() {return copy({...materials,scope:remote.scope});},
    async saveDraft(id,body) {
      calls.push(['save',id,copy(body)]);
      assert.deepEqual(body.expected_scope,remote.scope);
      assert.equal(body.expected_composer_revision,remote.composer_revision);
      remote={...remote,draft_input:body.content,composer_revision:remote.composer_revision+1};
      return copy(remote);
    },
    async getGenerationCapability(id) {
      calls.push(['capability',id]);
      return {scope:copy(remote.scope),composer_revision:remote.composer_revision,basis:'saved_draft',
        content_sha256:remote.draft_input.trim()?sha(remote.draft_input):null,
        state:materials.items.length?'unsupported':mode};
    },
    async submitGeneration(id,body) {
      calls.push(['submit',id,copy(body)]);
      assert.deepEqual(Object.keys(body).sort(),['attachment_ids','content','expected_composer_revision','expected_scope','request_id','requested_skill']);
      assert.deepEqual(body.expected_scope,remote.scope);
      assert.equal(body.expected_composer_revision,remote.composer_revision);
      assert.equal(body.requested_skill,null);assert.deepEqual(body.attachment_ids,[]);
      const number=attempts.size+1, messageId=`message-${number}`;
      remote={...remote,scope:{...remote.scope,input_revision:remote.scope.input_revision+1},
        composer_revision:remote.composer_revision+1,draft_input:''};
      const attempt={id:`attempt-${number}`,run_id:`run-${number}`,scope:copy(remote.scope),
        state:'sending',reserved_usd:'0.1',unit:'USD',receipt:null,output:null};
      remote.messages.push({id:messageId,role:'user',content:body.content,source_revision:remote.scope.input_revision});
      remote.latest_run={id:attempt.run_id,message_id:messageId,request_id:body.request_id,
        state:'generating',scope:copy(remote.scope),cancel_requested:false};
      attempts.set(attempt.id,attempt);byRequest.set(body.request_id,attempt.id);messages.set(messageId,attempt.id);
      return copy(attempt);
    },
    async findGenerationRequest(id,key) {
      calls.push(['find',id,key]);return copy(attempts.get(byRequest.get(key))||null);
    },
    async getGenerationAttempt(id) {calls.push(['attempt',id]);return copy(attempts.get(id));},
    async getGenerationHistory(id,ids) {
      calls.push(['history',id,copy(ids)]);
      assert.ok(ids.length<=50);assert.equal(new Set(ids).size,ids.length);
      return {scope:copy(remote.scope),items:ids.filter(key=>messages.has(key)).map(key=>({
        message_id:key,attempt:copy(attempts.get(messages.get(key)))}))};
    },
    async cancelRun(id,body) {
      calls.push(['cancel',id,copy(body)]);remote.latest_run.state='cancelled';remote.latest_run.cancel_requested=true;
      const attempt=attempts.get(messages.get(remote.latest_run.message_id));
      attempt.state='sent_unknown';attempt.receipt={state:'sent_unknown',cost_status:'unknown',estimated_cost_usd:null,unit:'USD'};
    },
  };
  const controller=createDraftController(api,{uuid:()=>`request-${++sequence}`,readonly});
  return {api,controller,calls,attempts,messages,byRequest,
    get remote(){return remote;},set remote(value){remote=copy(value);},
    set capability(value){mode=value;},get materials(){return materials;},set materials(value){materials=value;}};
}
let passed=0;
async function check(name,run) {await run();passed++;console.log('PASS '+name);}
const sends=f=>f.calls.filter(call=>call[0]==='submit');

await check('default, read-only, selected skill and local materials never dispatch',async()=>{
  for(const options of [{capability:'unconfigured'},{capability:'unapproved'},{readonly:true}]) {
    const f=fixture({...options,initial:snapshot('one','合成文字',1)}),c=f.controller;
    await c.open('one');await c.refreshGeneration();assert.equal(c.state.generation.canSend,false);
    assert.equal(await c.send(),false);assert.equal(sends(f).length,0);assert.equal(c.state.text,'合成文字');
  }
  const f=fixture(),c=f.controller;c.edit('本机合成草稿');c.selectSkill('contract_review');
  assert.equal(await c.send(),false);assert.equal(sends(f).length,0);
  c.selectSkill(null);await c.save();f.materials={items:[{attachment_id:'file'}],attachments:[{id:'file',original_name:'合成.docx'}]};
  await c.refresh();await c.refreshGeneration();assert.equal(await c.send(),false);
  assert.equal(c.state.text,'本机合成草稿');assert.equal(c.state.materials.attachments.length,1);
});

await check('one click snapshots input, saves first and double click dispatches one fixed request',async()=>{
  const f=fixture(),c=f.controller;c.edit('点击时合成文字');
  const first=c.send(),second=c.send();assert.equal(await first,true);assert.equal(await second,true);
  assert.equal(sends(f).length,1);assert.equal(sends(f)[0][2].content,'点击时合成文字');
  assert.equal(sends(f)[0][2].expected_composer_revision,1);assert.equal(c.state.text,'');
  assert.equal(c.state.view.composer_revision,2);assert.equal(c.state.generation.items[0].message_id,'message-1');
});

await check('editing while initial save waits aborts send instead of sending the newer text',async()=>{
  const f=fixture(),c=f.controller,gate=deferred(),save=f.api.saveDraft;await c.open('one');c.edit('点击原文');
  let count=0;f.api.saveDraft=async(...args)=>{if(++count===1)await gate.promise;return save(...args);};
  const sending=c.send();await tick();c.edit('等待时的新文字');gate.resolve();
  assert.equal(await sending,false);assert.equal(sends(f).length,0);assert.equal(c.state.text,'等待时的新文字');
  assert.equal(c.state.savedText,'等待时的新文字');
});

await check('editing while capability waits invalidates ready and requires a fresh click',async()=>{
  const f=fixture({initial:snapshot('one','点击原文',1)}),c=f.controller,gate=deferred(),read=f.api.getGenerationCapability;
  await c.open('one');f.api.getGenerationCapability=async(...args)=>{const value=await read(...args);await gate.promise;return value;};
  const sending=c.send();await tick();c.edit('尚未发送的新文字');gate.resolve();
  assert.equal(await sending,false);assert.equal(sends(f).length,0);assert.equal(c.state.generation.canSend,false);
  assert.equal(c.state.text,'尚未发送的新文字');
});

await check('acknowledgement preserves new input and queued saves use the accepted composer revision',async()=>{
  const f=fixture({initial:snapshot('one','发送原文',1)}),c=f.controller,gate=deferred(),submit=f.api.submitGeneration;
  await c.open('one');f.api.submitGeneration=async(...args)=>{const value=await submit(...args);await gate.promise;return value;};
  const sending=c.send();while(!sends(f).length)await tick();c.edit('下一条草稿');const saving=c.save();
  await tick();assert.equal(f.calls.filter(x=>x[0]==='save').length,0);gate.resolve();
  assert.equal(await sending,true);assert.equal(await saving,true);assert.equal(c.state.text,'下一条草稿');
  assert.equal(c.state.savedText,'下一条草稿');assert.equal(c.state.view.composer_revision,3);assert.equal(sends(f).length,1);
});

await check('lost registration reply is recovered by original request only and preserves later edits',async()=>{
  const f=fixture({initial:snapshot('one','发送原文',1)}),c=f.controller,submit=f.api.submitGeneration;
  await c.open('one');f.api.submitGeneration=async(...args)=>{await submit(...args);throw failure();};
  assert.equal(await c.send(),false);assert.equal(c.state.generation.phase,'unknown');assert.equal(c.state.text,'发送原文');
  c.edit('稍后的草稿');assert.equal(await c.save(),false);
  assert.equal(await c.refreshGeneration(),true);assert.equal(sends(f).length,1);
  assert.equal(f.calls.find(x=>x[0]==='find')[2],sends(f)[0][2].request_id);
  assert.equal(c.state.text,'稍后的草稿');assert.equal(await c.save(),true);assert.equal(c.state.savedText,'稍后的草稿');
});

await check('unknown not found stays unknown across send and refresh without replacing its key',async()=>{
  const f=fixture({initial:snapshot('one','未确认原文',1)}),c=f.controller;await c.open('one');
  f.api.submitGeneration=async(id,body)=>{f.calls.push(['submit',id,copy(body)]);throw failure();};
  assert.equal(await c.send(),false);assert.equal(await c.send(),false);assert.equal(await c.refreshGeneration(),false);
  assert.equal(sends(f).length,1);assert.equal(c.state.generation.phase,'unknown');assert.equal(c.state.text,'未确认原文');
  assert.ok(f.calls.filter(x=>x[0]==='find').every(x=>x[2]===sends(f)[0][2].request_id));
});

await check('unknown draft and material writes cannot be crossed by sending',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');f.api.saveDraft=async()=>{throw failure();};c.edit('待核保存');
  assert.equal(await c.save(),false);assert.equal(await c.send(),false);assert.equal(sends(f).length,0);
  const g=fixture(),d=g.controller;await d.open('one');d.edit('材料待核');
  g.api.uploadAttachment=async()=>{throw failure();};
  assert.equal(await d.upload({name:'合成.docx',type:'x'},{}),false);assert.equal(await d.send(),false);
  assert.equal(sends(g).length,0);assert.equal(d.state.materialAction,'upload');assert.equal(d.state.text,'材料待核');
});

await check('registration conflict retains local and remote drafts for explicit resolution',async()=>{
  const f=fixture({initial:snapshot('one','本机原文',1)}),c=f.controller;await c.open('one');
  f.api.submitGeneration=async()=>{f.remote={...f.remote,draft_input:'别处的新版本',composer_revision:5};throw failure(409,'VERSION_CONFLICT');};
  assert.equal(await c.send(),false);assert.equal(c.state.status,'conflict');assert.equal(c.state.text,'本机原文');
  assert.equal(c.state.conflict.server,'别处的新版本');assert.equal(c.state.generation.canSend,false);
});

for(const field of ['scope','revision','digest','basis'])await check(`old ready ${field} cannot authorize current text`,async()=>{
  const f=fixture({initial:snapshot('one','现存草稿',2)}),c=f.controller,normal=f.api.getGenerationCapability;await c.open('one');
  f.api.getGenerationCapability=async(...args)=>{const cap=await normal(...args);
    if(field==='scope')cap.scope.input_revision++;
    if(field==='revision')cap.composer_revision--;
    if(field==='digest')cap.content_sha256=sha('旧文');
    if(field==='basis')cap.basis='unknown';return cap;};
  await c.refreshGeneration();assert.equal(c.state.generation.canSend,false);assert.equal(await c.send(),false);
  assert.equal(sends(f).length,0);assert.equal(c.state.text,'现存草稿');
});

await check('edit invalidates a previously ready capability synchronously',async()=>{
  const f=fixture({initial:snapshot('one','旧草稿',1)}),c=f.controller;await c.open('one');await c.refreshGeneration();
  assert.equal(c.state.generation.canSend,true);c.edit('新草稿');assert.equal(c.state.generation.canSend,false);
  c.edit('旧草稿');assert.equal(c.state.generation.canSend,false);
});

for(const code of ['BLOCKED_LIVE','BUDGET_EXCEEDED','CALL_LIMIT_EXCEEDED'])await check(`ordinary ${code} 403 retains draft and current identity`,async()=>{
  const f=fixture({initial:snapshot('one','保留草稿',1)}),c=f.controller;await c.open('one');
  f.api.submitGeneration=async()=>{throw failure(403,code);};assert.equal(await c.send(),false);
  assert.equal(c.state.id,'one');assert.equal(c.state.text,'保留草稿');assert.notEqual(c.state.status,'revoked');
  assert.equal(c.state.generation.error.code,code);assert.equal(c.revoke(failure(403,code)),false);
});

await check('revocation discards delayed registration and clears current results',async()=>{
  const f=fixture({initial:snapshot('one','原文',1)}),c=f.controller,gate=deferred(),submit=f.api.submitGeneration;await c.open('one');
  f.api.submitGeneration=async(...args)=>{const value=await submit(...args);await gate.promise;return value;};
  const sending=c.send();while(!sends(f).length)await tick();c.revoke(failure(403,'CROSS_MATTER_DENIED'));gate.resolve();
  assert.equal(await sending,false);assert.equal(c.state.id,null);assert.equal(c.state.text,'');
  assert.deepEqual(c.state.generation.items,[]);assert.equal(c.state.generation.capability,null);
});

await check('switch and close discard late history success and late authorization failure',async()=>{
  for(const action of ['switch','close']) {
    const f=fixture({initial:snapshot('one','',1)}),c=f.controller,gate=deferred(),started=deferred();await c.open('one');
    f.remote={...f.remote,messages:[{id:'old-message',content:'旧消息'}]};await c.refresh();
    f.api.getGenerationHistory=()=>{started.resolve();return gate.promise;};const reading=c.refreshGeneration();await started.promise;
    if(action==='switch'){f.remote=snapshot('two');assert.equal(await c.open('two'),true);}else c.close();
    gate.reject(failure(403,'CROSS_MATTER_DENIED'));assert.equal(await reading,false);
    assert.equal(c.state.id,action==='switch'?'two':null);assert.notEqual(c.state.status,'revoked');
    assert.deepEqual(c.state.generation.items,[]);
  }
});

await check('history batches visible messages, retains older attempts and has no provider action on reopen',async()=>{
  const f=fixture(),c=f.controller;f.remote.scope.input_revision=130;
  for(let index=1;index<=121;index++) {
    const messageId=`old-${index}`,attemptId=`old-attempt-${index}`;
    f.remote.messages.push({id:messageId,content:`合成历史 ${index}`});f.messages.set(messageId,attemptId);
    f.attempts.set(attemptId,{id:attemptId,run_id:`run-${index}`,scope:{...f.remote.scope,input_revision:index},
      state:'received',receipt:null,output:null,reserved_usd:'0.1',unit:'USD'});
  }
  f.remote.messages.push({id:'legacy-no-attempt',content:'旧队列'});
  await c.open('one');assert.equal(await c.refreshGeneration(),true);
  assert.equal(c.state.generation.items.length,121);
  assert.deepEqual(f.calls.filter(x=>x[0]==='history').map(x=>x[2].length),[50,50,22]);
  assert.equal(sends(f).length,0);assert.equal(c.state.generation.items[0].attempt.scope.input_revision,1);
});

await check('cancelling reads receipt and candidates without a second generation POST',async()=>{
  const f=fixture({initial:snapshot('one','待取消文字',1)}),c=f.controller;await c.open('one');assert.equal(await c.send(),true);
  assert.equal(await c.cancel(),true);assert.equal(sends(f).length,1);
  assert.equal(c.state.generation.items[0].attempt.receipt.cost_status,'unknown');
  assert.equal(c.state.view.latest_run.cancel_requested,true);assert.equal(await c.cancel(),false);
});

await check('historical scope change clears results and rejects late capability',async()=>{
  const f=fixture({initial:snapshot('one','旧案草稿',1)}),c=f.controller,gate=deferred(),cap=f.api.getGenerationCapability;
  await c.open('one');f.api.getGenerationCapability=async(...args)=>{const value=await cap(...args);await gate.promise;return value;};
  const reading=c.refreshGeneration();await tick();f.remote.scope={...f.remote.scope,scope_kind:'matter',scope_ref:'other',binding_revision:2};
  await c.refresh();gate.resolve();assert.equal(await reading,false);assert.equal(c.state.generation.canSend,false);
  assert.deepEqual(c.state.generation.items,[]);
});

await check('known registration survives readback failure and newer draft can be saved after reconciliation',async()=>{
  const f=fixture({initial:snapshot('one','已登记原文',1)}),c=f.controller,read=f.api.getConversation;
  await c.open('one');let failed=false;
  f.api.getConversation=async(...args)=>{if(sends(f).length && !failed){failed=true;throw failure();}return read(...args);};
  assert.equal(await c.send(),false);assert.equal(c.state.text,'');assert.equal(c.state.view.composer_revision,2);
  c.edit('登记后的新草稿');assert.equal(await c.refresh(),true);assert.equal(await c.retry(),true);
  assert.equal(c.state.savedText,'登记后的新草稿');assert.equal(await c.refreshGeneration(),true);
  assert.equal(c.state.generation.items.length,1);assert.equal(sends(f).length,1);
});

await check('known registration and independent remote edit leave a resolvable composer conflict',async()=>{
  const f=fixture({initial:snapshot('one','已登记原文',1)}),c=f.controller,submit=f.api.submitGeneration,gate=deferred();
  await c.open('one');f.api.submitGeneration=async(...args)=>{
    const result=await submit(...args);await gate.promise;
    f.remote={...f.remote,draft_input:'另一窗口草稿',composer_revision:3};return result;
  };
  const sending=c.send();while(!sends(f).length)await tick();c.edit('我正在写的草稿');gate.resolve();
  assert.equal(await sending,false);assert.equal(c.state.status,'conflict');assert.equal(c.state.text,'我正在写的草稿');
  assert.equal(await c.resolveConflict('local'),true);assert.equal(c.state.savedText,'我正在写的草稿');
  assert.equal(sends(f).length,1);
});

await check('completed older messages and attempts survive pagination and a later send',async()=>{
  const f=fixture(),c=f.controller;
  const all=[];
  for(let index=1;index<=80;index++) {
    const message={id:`old-${index}`,content:`历史 ${index}`,role:'user',source_revision:index};all.push(message);
    const attempt={id:`old-attempt-${index}`,run_id:`old-run-${index}`,scope:{...f.remote.scope,input_revision:index},
      state:'received',receipt:null,output:null,reserved_usd:'0.01',unit:'USD'};
    f.messages.set(message.id,attempt.id);f.attempts.set(attempt.id,attempt);
  }
  f.remote={...f.remote,scope:{...f.remote.scope,input_revision:80},messages:all.slice(30),next_before:'older'};
  const get=f.api.getConversation;
  f.api.getConversation=async(id,before)=>before?{...copy(f.remote),messages:all.slice(0,30),next_before:null}:get(id,before);
  await c.open('one');await c.loadEarlier();assert.equal(c.state.view.messages.length,80);
  await c.refreshGeneration();assert.equal(c.state.generation.items.length,80);
  c.edit('下一条合成输入');assert.equal(await c.send(),true);
  assert.equal(c.state.view.messages.length,81);assert.equal(c.state.generation.items.length,81);
  assert.equal(c.state.generation.items[0].message_id,'old-1');assert.equal(sends(f).length,1);
});

await check('same text retyped during submission is preserved as new input',async()=>{
  const f=fixture({initial:snapshot('one','重复文字',1)}),c=f.controller,gate=deferred(),submit=f.api.submitGeneration;
  await c.open('one');f.api.submitGeneration=async(...args)=>{const result=await submit(...args);await gate.promise;return result;};
  const sending=c.send();while(!sends(f).length)await tick();c.edit('');c.edit('重复文字');gate.resolve();
  assert.equal(await sending,true);assert.equal(c.state.text,'重复文字');assert.equal(c.state.dirty,true);
  assert.equal(await c.save(),true);assert.equal(c.state.view.composer_revision,3);
});

await check('send during a background capability read waits then registers exactly the clicked input',async()=>{
  const f=fixture({initial:snapshot('one','原文',1)}),c=f.controller,gate=deferred(),started=deferred(),cap=f.api.getGenerationCapability;
  await c.open('one');let reads=0;
  f.api.getGenerationCapability=async(...args)=>{const result=await cap(...args);if(++reads===1){started.resolve();await gate.promise;}return result;};
  const reading=c.refreshGeneration();await started.promise;const sending=c.send(),double=c.send();gate.resolve();
  await reading;assert.equal(await sending,true);assert.equal(await double,true);assert.equal(sends(f).length,1);
});

console.log(`${passed} generation state groups passed`);
