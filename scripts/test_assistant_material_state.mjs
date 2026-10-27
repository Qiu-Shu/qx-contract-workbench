import assert from 'node:assert/strict';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';

const copy=value=>structuredClone(value);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const failure=(status=0,code='NETWORK_UNKNOWN')=>Object.assign(new Error(code),{status,code});
function fixture(options={}) {
  let remote={scope:{workspace_id:'w',conversation_id:'one',scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0},composer_revision:0,draft_input:'',messages:[]};
  let material={scope:remote.scope,items:[],attachments:[]},sequence=0;
  const calls=[],receipts=new Map();
  const api={
    async createConversation(body){calls.push(['create',body]);return copy(remote);},
    async getConversation(){return copy(remote);},
    async getMaterials(){return copy({...material,scope:remote.scope});},
    async saveDraft(id,body){calls.push(['draft',copy(body)]);
      assert.deepEqual(body.expected_scope,remote.scope);assert.equal(body.expected_composer_revision,remote.composer_revision);
      remote={...remote,composer_revision:remote.composer_revision+1,draft_input:body.content};return copy(remote);},
    async uploadAttachment(id,body,file){calls.push(['upload',copy(body),file]);
      const attachment={id:'attachment',conversation_id:id,request_id:body.request_id,original_name:file.name,mime:file.type};
      remote.scope={...remote.scope,materials_revision:remote.scope.materials_revision+1};
      material={scope:remote.scope,items:[{attachment_id:'attachment',parse_revision:null}],attachments:[attachment]};
      const result={attachment,materials_revision:remote.scope.materials_revision};receipts.set(body.request_id,result);return copy(result);},
    async findAttachmentRequest(id,key){calls.push(['lookup',key]);return copy(receipts.get(key)||null);},
  };
  const controller=createDraftController(api,{uuid:()=>`request-${++sequence}`,...options});
  return {controller,api,calls,get remote(){return remote;},set remote(value){remote=value;}};
}
const file={name:'合成资料.docx',type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',size:50};
const policy={policy_id:'assistant-local-docx-v1',material_mode:'synthetic',local_processing_accepted:true,external_processing:false};
let passed=0;
async function check(name,run){await run();passed++;console.log('PASS '+name);}

await check('attachment-only action creates one conversation and never clears text typed during upload',async()=>{
  const f=fixture(),c=f.controller;let resume;
  const normal=f.api.uploadAttachment;
  f.api.uploadAttachment=async(...args)=>{await new Promise(resolve=>resume=resolve);return normal(...args);};
  const upload=c.upload(file,policy);await tick();
  assert.equal(c.canLeave(),false);c.edit('上传期间的新文字');assert.equal(c.state.text,'上传期间的新文字');
  resume();assert.equal(await upload,true);
  assert.equal(c.state.savedText,'上传期间的新文字');assert.equal(c.state.materials.items.length,1);
  assert.equal(f.calls.filter(x=>x[0]==='create').length,1);
  assert.equal(f.calls.find(x=>x[0]==='draft')[1].expected_scope.materials_revision,1);
});
await check('unknown upload checks receipt before retry, retains chosen file and never duplicates',async()=>{
  const f=fixture(),c=f.controller,normal=f.api.uploadAttachment;
  f.api.uploadAttachment=async(...args)=>{await normal(...args);throw failure();};
  assert.equal(await c.upload(file,policy),false);assert.equal(c.canLeave(),false);
  c.edit('响应丢失后继续输入');assert.equal(await c.save(),false);
  assert.equal(await c.retry(),true);
  assert.equal(f.calls.filter(x=>x[0]==='upload').length,1);assert.equal(f.calls.filter(x=>x[0]==='lookup').length,1);
  assert.equal(c.state.savedText,'响应丢失后继续输入');
});
await check('revocation clears pending attachment and late response cannot repopulate another view',async()=>{
  const f=fixture(),c=f.controller;let resume;
  const normal=f.api.uploadAttachment;
  f.api.uploadAttachment=async(...args)=>{await new Promise(resolve=>resume=resolve);return normal(...args);};
  const upload=c.upload(file,policy);await tick();c.revoke(failure(403,'CROSS_MATTER_DENIED'));resume();
  assert.equal(await upload,false);assert.equal(c.state.materials,null);assert.equal(c.state.id,null);
  assert.equal(c.state.text,'');assert.equal(c.state.status,'revoked');
});
await check('material scope conflict preserves text and file until explicit resolution',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');c.edit('本机原话');
  const normal=f.api.uploadAttachment;let conflict=true;
  f.api.uploadAttachment=async(...args)=>{
    if(conflict){conflict=false;f.remote={...f.remote,scope:{...f.remote.scope,materials_revision:2}};throw failure(409,'VERSION_CONFLICT');}
    return normal(...args);
  };
  assert.equal(await c.upload(file,policy),false);assert.equal(c.state.text,'本机原话');assert.ok(c.state.conflict);
  assert.equal(await c.resolveConflict('local'),true);assert.equal(c.state.materials.attachments[0].original_name,file.name);
  assert.equal(c.state.savedText,'本机原话');
});
await check('shared composer automatically parses supported upload against its saved scope',async()=>{
  const f=fixture({autoReadMaterials:true});
  f.api.parseAttachment=async(id,attachment,body)=>{
    f.calls.push(['parse',attachment,body]);assert.equal(body.expected_scope.materials_revision,1);
    assert.equal(body.baseline_view,null);return {parse:{revision:1}};
  };
  assert.equal(await f.controller.upload(file,policy),true);
  assert.equal(f.calls.filter(call=>call[0]==='parse').length,1);
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
});
await check('unknown automatic parse recovers its receipt without reuploading',async()=>{
  const f=fixture({autoReadMaterials:true});let parses=0,reads=0;
  f.api.parseAttachment=async()=>{parses++;throw failure();};
  f.api.findParseRequest=async()=>{reads++;return {parse:{revision:1}};};
  assert.equal(await f.controller.upload(file,policy),false);
  assert.equal(f.controller.state.materialAction,'parse');
  assert.equal(await f.controller.retry(),true);
  assert.equal(parses,1);assert.equal(reads,1);
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
});
console.log(`${passed} attachment state groups passed`);
