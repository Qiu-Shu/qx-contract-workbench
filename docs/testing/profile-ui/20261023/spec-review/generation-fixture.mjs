import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {createDraftController} from '../../../src/cn_contract/web/static/assistant-state.mjs';

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


export {opened,calls,mutations,failure};
