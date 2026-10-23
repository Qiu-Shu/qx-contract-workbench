import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';

const copy=structuredClone,sha=value=>createHash('sha256').update(value).digest('hex');
const id=number=>`00000000-0000-4000-8000-${String(number).padStart(12,'0')}`;
const failure=(code='NETWORK_UNKNOWN',status=0)=>Object.assign(Error(code),{code,status});
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const scope=(conversation=id(1))=>({workspace_id:id(2),conversation_id:conversation,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:0});
function fixture({bridge=true,apis=true,readonly=false,capability='unapproved',approval={ok:true,status:'authorized'}}={}) {
  let remote={scope:scope(),composer_revision:1,draft_input:'合成客户自述：尚待核对',messages:[],next_before:null,latest_run:null};
  let materials={items:[],attachments:[]},sequence=100;
  const calls=[],requests=new Map(),history=new Map();
  const native=async choice=>{calls.push(['approve',copy(choice)]);return typeof approval==='function'?approval(choice):copy(approval);};
  const register=(kind,body)=>{
    calls.push([kind,copy(body)]);
    const nextScope={...remote.scope,input_revision:remote.scope.input_revision+1};
    const attempt={id:id(10),run_id:id(11),scope:nextScope,state:'sending',receipt:null,output:null,
      ...(kind==='profile'?{input_format:'profile-text-v1'}:{})};
    remote={...remote,scope:nextScope,composer_revision:remote.composer_revision+1,draft_input:'',
      messages:[...remote.messages,{id:id(12),role:'user',content:body.content}],
      latest_run:{id:id(11),state:'generating',scope:nextScope}};
    requests.set(body.request_id,attempt);history.set(id(12),attempt);return copy(attempt);
  };
  const api={
    async getConversation(){return copy(remote);},
    async getMaterials(){return copy({...materials,scope:remote.scope});},
    async saveDraft(_id,body){calls.push(['save',copy(body)]);remote={...remote,draft_input:body.content,composer_revision:remote.composer_revision+1};return copy(remote);},
    async getGenerationCapability(){calls.push(['cap']);return {scope:copy(remote.scope),composer_revision:remote.composer_revision,
      basis:'saved_draft',content_sha256:remote.draft_input.trim()?sha(remote.draft_input):null,state:capability};},
    async submitGeneration(_id,body){return register('plain',body);},
    async submitProfilePreview(_id,body){calls.push(['preview',copy(body)]);return {...copy(body),
      input_format:'profile-text-v1',template_version:'profile-text-system-v1',purpose:'reply_and_profile_draft',
      handler_id:'profile.save',handler_version:'1',content_sha256:sha(remote.draft_input),base_profile_revision:0,
      expected_intake_id:null,expected_intake_revision:null,system_sha256:'a'.repeat(64),config_sha256:'b'.repeat(64),
      wire_sha256:'c'.repeat(64),wire_bytes:128};},
    async submitProfileGeneration(_id,body){return register('profile',body);},
    async findGenerationRequest(_id,request){calls.push(['find',request]);return copy(requests.get(request)||null);},
    async getGenerationHistory(_id,ids){return {scope:copy(remote.scope),items:ids.filter(key=>history.has(key)).map(key=>({message_id:key,attempt:copy(history.get(key))}))};},
  };
  if(!apis){delete api.submitProfilePreview;delete api.submitProfileGeneration;}
  const c=createDraftController(api,{uuid:()=>id(++sequence),readonly,nativeAuthorization:async()=>{calls.push(['plain-approve']);return {ok:true};},
    nativeProfileAuthorization:bridge?native:null});
  return {c,api,calls,requests,history,register,get remote(){return remote;},set remote(value){remote=copy(value);},
    get materials(){return materials;},set materials(value){materials=value;}};
}
const calls=(f,kind)=>f.calls.filter(call=>call[0]===kind);
const mutations=f=>f.calls.filter(call=>['plain','profile'].includes(call[0]));
async function opened(options){const f=fixture(options);await f.c.open(id(1));return f;}
async function pendingApproval(){
  const gate=deferred(),entered=deferred();
  const f=await opened({approval:()=>{entered.resolve();return gate.promise;}});
  const sending=f.c.send();
  await Promise.race([entered.promise,sending.then(()=>{throw Error('profile native approval was not requested');})]);
  return {f,gate,sending};
}

test('desktop ordinary text previews the saved source and submits one flat profile DTO',async()=>{
  const f=await opened();f.c.edit('合成新陈述');const first=f.c.send(),second=f.c.send();
  assert.equal(await first,true);assert.equal(await second,true);
  assert.equal(calls(f,'plain').length,0);assert.equal(calls(f,'plain-approve').length,0);
  assert.equal(calls(f,'preview').length,1);assert.equal(calls(f,'approve').length,1);assert.equal(calls(f,'profile').length,1);
  const preview=calls(f,'preview')[0][1],choice=calls(f,'approve')[0][1],body=calls(f,'profile')[0][1];
  assert.deepEqual(Object.keys(preview).sort(),['expected_composer_revision','expected_scope','project_intake','request_id']);
  assert.equal(preview.project_intake,true);assert.equal(preview.expected_composer_revision,2);
  assert.deepEqual(choice,{conversation_id:id(1),...preview});
  assert.deepEqual(body,{request_id:preview.request_id,expected_scope:preview.expected_scope,expected_composer_revision:2,
    content:'合成新陈述',requested_skill:null,attachment_ids:[],project_intake:true});
  assert.equal(f.c.state.text,'');assert.equal(f.c.state.generation.items[0].attempt.input_format,'profile-text-v1');
  assert.equal(Object.hasOwn(f.c.state.generation,'profileSaved'),false,'registration is not a save receipt');
});

for(const options of [{bridge:false},{apis:false}])test(`older client keeps plain send: ${JSON.stringify(options)}`,async()=>{
  const f=await opened(options);assert.equal(await f.c.send(),true);
  assert.equal(calls(f,'plain').length,1);assert.equal(calls(f,'profile').length,0);assert.equal(calls(f,'approve').length,0);
});

test('refresh reads capability and history without previewing or opening native approval',async()=>{
  const f=await opened();await f.c.refreshGeneration();assert.equal(f.c.state.generation.canSend,true);
  assert.equal(calls(f,'preview').length,0);assert.equal(calls(f,'approve').length,0);assert.equal(mutations(f).length,0);
});

for(const field of ['request_id','expected_scope','expected_composer_revision','content_sha256','project_intake','purpose','input_format',
  'handler_id','base_profile_revision','expected_intake_revision','wire_bytes','wire_sha256']) {
  test(`invalid profile preview ${field} rejects without native approval or plain fallback`,async()=>{
    const f=await opened(),preview=f.api.submitProfilePreview;
    f.api.submitProfilePreview=async(...args)=>{const result=await preview(...args);result[field]=field==='expected_intake_revision'?0:null;return result;};
    assert.equal(await f.c.send(),false);assert.equal(f.c.state.generation.error?.code,'INVALID_RESPONSE');
    assert.equal(calls(f,'approve').length,0);assert.equal(mutations(f).length,0);
  });
}

for(const approval of [{ok:true},{ok:true,status:'ready'},{ok:'true',status:'authorized'},
  {ok:true,status:'authorized',extra:'untrusted'},{ok:true,status:'authorized',canceled:true},{ok:false,status:'authorized'}]) {
  test(`native profile acknowledgement is strict: ${JSON.stringify(approval)}`,async()=>{
    const f=await opened({approval});assert.equal(await f.c.send(),false);
    assert.equal(f.c.state.generation.error?.code,'NATIVE_CONFIRMATION_FAILED');assert.equal(mutations(f).length,0);
  });
}

test('cancelled profile approval preserves text without registration',async()=>{
  const f=await opened({approval:{ok:false,canceled:true}});assert.equal(await f.c.send(),false);
  assert.equal(f.c.state.generation.phase,'idle');assert.equal(f.c.state.text,'合成客户自述：尚待核对');assert.equal(mutations(f).length,0);
});

for(const change of ['edit','retype','skill','skill-reset','scope','composer','materials','attachments','context','context-reset']) {
  test(`pending profile approval is invalidated by ${change}`,async()=>{
    const {f,gate,sending}=await pendingApproval();
    if(change==='edit'||change==='retype'){f.c.edit('新输入');if(change==='retype')f.c.edit('合成客户自述：尚待核对');}
    if(change.startsWith('skill')){f.c.selectSkill('client_reply');if(change==='skill-reset')f.c.selectSkill(null);}
    if(['scope','composer','materials','attachments'].includes(change)){
      if(change==='scope')f.remote={...f.remote,scope:{...f.remote.scope,binding_revision:2}};
      if(change==='composer')f.remote={...f.remote,composer_revision:2};
      if(change==='materials')f.materials.items=[{attachment_id:id(20)}];
      if(change==='attachments')f.materials.attachments=[{id:id(20)}];
      await f.c.refresh();
    }
    if(change.startsWith('context')){
      f.c.state.research.items=[{research:{receipts:[{result:{result:{page:{citations:[{title:'合成引用'}]}},citation_ids:[id(21)]}}]}}];
      f.c.toggleContextCitation(id(21));if(change==='context-reset')f.c.toggleContextCitation(id(21));
    }
    gate.resolve({ok:true,status:'authorized'});assert.equal(await sending,false);assert.equal(mutations(f).length,0);
  });
}

for(const action of ['switch','close','revoke'])test(`late profile approval after ${action} is ignored`,async()=>{
  const {f,gate,sending}=await pendingApproval();
  if(action==='switch'){f.remote={...f.remote,scope:scope(id(30)),draft_input:'另一对话'};await f.c.open(id(30));}
  if(action==='close')f.c.close();
  if(action==='revoke')f.c.revoke(failure('AUTHORIZATION_REQUIRED',401));
  gate.resolve({ok:true,status:'authorized'});assert.equal(await sending,false);assert.equal(mutations(f).length,0);
  assert.equal(f.c.state.text,action==='switch'?'另一对话':'');assert.deepEqual(f.c.state.generation.items,[]);
});

for(const guard of ['readonly','unconfigured','busy','restored_read_only','skill','materials','attachments','awaiting_input']) {
  test(`profile send cannot bypass ${guard}`,async()=>{
    const f=await opened({readonly:guard==='readonly',capability:['unconfigured','busy','restored_read_only'].includes(guard)?guard:'unapproved'});
    if(guard==='skill')f.c.selectSkill('client_reply');
    if(guard==='materials'){f.materials.items=[{attachment_id:id(20)}];await f.c.refresh();}
    if(guard==='attachments'){f.materials.attachments=[{id:id(20)}];await f.c.refresh();}
    if(guard==='awaiting_input'){f.remote={...f.remote,latest_run:{id:id(11),state:'awaiting_input'}};await f.c.refresh();}
    await f.c.refreshGeneration();assert.equal(f.c.state.generation.canSend,false);assert.equal(await f.c.send(),false);
    assert.equal(mutations(f).length,0);assert.equal(calls(f,'approve').length,0);
  });
}

test('existing native acknowledgement only reads the original request, including when not yet found',async()=>{
  const f=await opened({approval:{ok:true,status:'existing'}});
  assert.equal(await f.c.send(),false);assert.equal(f.c.state.generation.phase,'unknown');
  await f.c.send();await f.c.refreshGeneration();
  assert.equal(mutations(f).length,0);assert.equal(calls(f,'approve').length,1);assert.equal(calls(f,'preview').length,1);
  const request=calls(f,'approve')[0][1].request_id;
  assert.ok(calls(f,'find').length>=3);assert.ok(calls(f,'find').every(call=>call[1]===request));
});

test('profile transport loss reconciles by request without repost or new approval and preserves later edits',async()=>{
  const f=await opened(),submit=f.api.submitProfileGeneration;
  f.api.submitProfileGeneration=async(...args)=>{await submit(...args);throw failure();};
  assert.equal(await f.c.send(),false);assert.equal(f.c.state.generation.phase,'unknown');f.c.edit('下一条草稿');
  assert.equal(await f.c.save(),false);assert.equal(await f.c.send(),true);assert.equal(f.c.state.text,'下一条草稿');
  assert.equal(calls(f,'profile').length,1);assert.equal(calls(f,'approve').length,1);assert.equal(calls(f,'plain').length,0);
  assert.equal(calls(f,'find')[0][1],calls(f,'profile')[0][1].request_id);
});

test('existing native acknowledgement recovers a profile attempt without submitting again',async()=>{
  const f=await opened({approval:choice=>{
    const nextScope={...choice.expected_scope,input_revision:choice.expected_scope.input_revision+1};
    const attempt={id:id(10),run_id:id(11),scope:nextScope,input_format:'profile-text-v1',state:'received',receipt:null,output:null};
    f.requests.set(choice.request_id,attempt);f.history.set(id(12),attempt);
    f.remote={...f.remote,scope:nextScope,composer_revision:choice.expected_composer_revision+1,draft_input:'',
      messages:[{id:id(12),role:'user',content:'合成客户自述：尚待核对'}],latest_run:{id:id(11),state:'completed',scope:nextScope}};
    return {ok:true,status:'existing'};
  }});
  assert.equal(await f.c.send(),true);assert.equal(mutations(f).length,0);assert.equal(calls(f,'find').length,1);
  assert.equal(f.c.state.text,'');assert.equal(f.c.state.generation.items[0].attempt.input_format,'profile-text-v1');
});

test('plain attempt under a profile request is not accepted as a profile registration',async()=>{
  const f=await opened(),submit=f.api.submitProfileGeneration;
  f.api.submitProfileGeneration=async(...args)=>{const result=await submit(...args);delete result.input_format;return result;};
  assert.equal(await f.c.send(),false);assert.equal(f.c.state.generation.phase,'unknown');
  assert.equal(f.c.state.generation.error.code,'INVALID_RESPONSE');assert.equal(f.c.state.text,'合成客户自述：尚待核对');
  assert.equal(calls(f,'plain').length,0);
});

test('profile preview transport failure never opens native confirmation or falls back to plain',async()=>{
  const f=await opened();f.api.submitProfilePreview=async()=>{throw failure();};
  assert.equal(await f.c.send(),false);assert.equal(f.c.state.generation.phase,'error');
  assert.equal(calls(f,'approve').length,0);assert.equal(mutations(f).length,0);
  assert.equal(f.c.state.text,'合成客户自述：尚待核对');
});

test('definite profile rejection permits only a fresh explicit profile approval',async()=>{
  const f=await opened();f.api.submitProfileGeneration=async(_id,body)=>{f.calls.push(['profile',copy(body)]);throw failure('STATE_CONFLICT',422);};
  assert.equal(await f.c.send(),false);assert.equal(f.c.state.generation.phase,'error');
  await f.c.refreshGeneration();assert.equal(calls(f,'approve').length,1);
  assert.equal(await f.c.send(),false);assert.equal(calls(f,'approve').length,2);assert.equal(calls(f,'plain').length,0);
  assert.notEqual(calls(f,'profile')[0][1].request_id,calls(f,'profile')[1][1].request_id);
});
