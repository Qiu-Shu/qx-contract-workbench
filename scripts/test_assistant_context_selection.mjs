import assert from 'node:assert/strict';
import test from 'node:test';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';
import {savedCitations} from '../src/cn_contract/web/static/assistant-context.mjs';

const copy=structuredClone, tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const scope=id=>({workspace_id:'workspace',conversation_id:id,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:0});
const CITATIONS=[...Array(9)].map((_,index)=>({id:`citation-${index}`,title:`合成资料 ${index+1}`,
  kind:index%2?'case_csv':'law_markdown',line_start:index+1,line_end:index+5}));
function receipt(citations){
  return {run_id:'run-0',scope:scope('one'),handler_id:'legal_library.search',
    result:{citation_ids:citations.map(c=>c.id),result:{scope:scope('one'),state:'ready',
      page:{state:'ready',citations:citations.map(c=>({title:c.title,kind:c.kind,line_start:c.line_start,
        line_end:c.line_end})),omitted_hits:0}}}};
}
function previewResponse(remote,body,basisChanges={}){
  const sources=body.citation_ids.map(id=>CITATIONS.find(c=>c.id===id))
    .map(c=>({saved_citation_id:c.id,title:c.title,kind:c.kind,line_start:c.line_start,line_end:c.line_end}));
  const basis={input_format:'library-context-v1',template_version:'saved-library-context-system-v1',
    request_id:body.request_id,expected_scope:copy(body.expected_scope),
    expected_composer_revision:body.expected_composer_revision,system_sha256:'a'.repeat(64),
    manifest_sha256:'b'.repeat(64),config_sha256:'c'.repeat(64),wire_sha256:'d'.repeat(64),
    source_bindings:body.citation_ids.map(id=>({saved_citation_id:id,citation_sha256:'e'.repeat(64)})),
    ...basisChanges};
  return {scope:copy(remote.scope),composer_revision:remote.composer_revision,
    manifest:{format_version:'saved-library-context-v1',question:remote.draft_input,sources},
    manifest_sha256:'b'.repeat(64),system_text:'合成系统提示',state:'ready',model:'deepseek-flash',
    config_sha256:'c'.repeat(64),max_input_bytes:65536,wire_payload_json:'{}',wire_sha256:'d'.repeat(64),
    wire_bytes:100,sending_enabled:false,send_basis:basis};
}
function fixture({readonly=false,bridged=true,answer={ok:true}}={}) {
  let remote={scope:scope('one'),draft_input:'',composer_revision:0,
    messages:[{id:'m0',role:'user',content:'合成检索'}],latest_run:null},sequence=0;
  const calls=[],byRequest=new Map();let attempt=null,previewCalls=[],previewOverride=null;
  const api={
    async createConversation(){return copy(remote);},
    async getConversation(id){return copy({...remote,scope:{...remote.scope,conversation_id:id}});},
    async getMaterials(){return {scope:copy(remote.scope),items:[],attachments:[]};},
    async saveDraft(id,body){calls.push('save');remote={...remote,draft_input:body.content,
      composer_revision:remote.composer_revision+1};return copy(remote);},
    async submitResearch(){throw Object.assign(Error('fixture never submits research'),{code:'FIXTURE'});},
    async findResearchRequest(){return null;},
    async getResearchHistory(){return {scope:copy(remote.scope),items:[{message_id:'m0',
      research:{run:{id:'run-0',message_id:'m0',request_id:'r0',requested_skill:'legal_research',
        scope:copy(remote.scope),state:'completed'},
        receipts:[receipt(CITATIONS.slice(0,8)),receipt(CITATIONS.slice(8))]}}]};},
    async getGenerationCapability(){return {scope:copy(remote.scope),composer_revision:remote.composer_revision,
      basis:'saved_draft',content_sha256:null,state:'unconfigured'};},
    async getGenerationHistory(){return {scope:copy(remote.scope),items:[]};},
    async submitContextPreview(id,body){calls.push(['preview',copy(body)]);previewCalls.push(copy(body));
      if(previewOverride)return previewOverride(remote,body);return previewResponse(remote,body);},
    async submitContextGeneration(id,body){
      calls.push(['submit',copy(body)]);
      assert.deepEqual(body.expected_scope,remote.scope);
      assert.equal(body.expected_composer_revision,remote.composer_revision);
      assert.equal(body.content,remote.draft_input);
      remote={...remote,scope:{...remote.scope,input_revision:remote.scope.input_revision+1},
        draft_input:'',composer_revision:remote.composer_revision+1};
      attempt={id:'attempt-1',run_id:'run-ctx',scope:copy(remote.scope),input_format:'library-context-v1',
        state:'reserved',reserved_usd:'0.01',unit:'USD',receipt:null,output:null};
      remote.latest_run={id:'run-ctx',message_id:'m1',request_id:body.request_id,requested_skill:null,
        scope:copy(remote.scope),state:'generating'};
      remote.messages.push({id:'m1',role:'user',content:body.content});
      byRequest.set(body.request_id,attempt);return copy(attempt);
    },
    async findGenerationRequest(id,key){calls.push('find');return copy(byRequest.get(key)||null);},
  };
  const approvals=[];
  const controller=createDraftController(api,{uuid:()=>`request-${++sequence}`,readonly,
    nativeContextAuthorization:bridged?async value=>{approvals.push(copy(value));return answer;}:null});
  return {api,calls,approvals,byRequest,controller,
    setPreviewOverride(fn){previewOverride=fn;},
    get previewCalls(){return previewCalls;},
    get attempt(){return attempt;},
    get remote(){return remote;},set remote(value){remote=value;}};
}
async function selectedFixture(options={}) {
  const f=fixture(options),c=f.controller;
  await c.open('one');await c.refreshGeneration();
  c.edit(' 合成问题：请核对所选片段。 ');await c.save();
  c.toggleContextCitation('citation-0');c.toggleContextCitation('citation-1');
  return f;
}

test('saved citations enumerate from own search receipts in order and dedupe',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');await c.refreshGeneration();
  const listed=savedCitations(c.state);
  assert.equal(listed.length,9);
  assert.deepEqual(listed.map(citation=>citation.id),CITATIONS.map(citation=>citation.id));
  assert.equal(listed[0].title,'合成资料 1');
});

test('selection keeps click order, toggles off, and refuses a ninth citation',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');await c.refreshGeneration();
  c.toggleContextCitation('citation-3');c.toggleContextCitation('citation-1');
  assert.deepEqual(c.state.context.selected,['citation-3','citation-1']);
  c.toggleContextCitation('citation-3');
  assert.deepEqual(c.state.context.selected,['citation-1']);
  for(const id of [...c.state.context.selected])c.toggleContextCitation(id);
  for(const citation of CITATIONS)c.toggleContextCitation(citation.id);
  assert.equal(c.state.context.selected.length,8);
  assert.ok(!c.state.context.selected.includes('citation-8'));
  c.toggleContextCitation('unknown-id');
  assert.equal(c.state.context.selected.length,8);
});

test('preview carries the fixed request and validates the deterministic response',async()=>{
  const f=await selectedFixture();
  assert.equal(f.controller.state.context.canPreview,true);
  assert.equal(await f.controller.previewContext(),true);
  const body=f.previewCalls[0];
  assert.equal(body.max_rounds,1);assert.equal(typeof body.request_id,'string');
  assert.deepEqual(body.citation_ids,['citation-0','citation-1']);
  const preview=f.controller.state.context.preview;
  assert.equal(preview.response.state,'ready');
  assert.equal(preview.response.send_basis.request_id,body.request_id);
  assert.equal(f.controller.state.context.canSend,true,'bridged desktop approval enables send');
});

test('editing the question or the selection invalidates the preview and remints the request',async()=>{
  const f=await selectedFixture();await f.controller.previewContext();
  const first=f.controller.state.context.requestId;
  f.controller.edit('改后的问题');f.controller.state.text='改后的问题';
  assert.equal(f.controller.state.context.preview,null);
  assert.notEqual(f.controller.state.context.requestId,first);
  await f.controller.save();await f.controller.previewContext();
  const second=f.controller.state.context.requestId;
  f.controller.toggleContextCitation('citation-2');
  assert.equal(f.controller.state.context.preview,null);
  assert.notEqual(f.controller.state.context.requestId,second);
});

test('broken preview responses are rejected as invalid and never enable sending',async()=>{
  for(const mutate of [
    body=>({...body,sending_enabled:true}),
    body=>({...body,manifest:{...body.manifest,question:'篡改的问题'}}),
    body=>({...body,manifest:{...body.manifest,sources:[...body.manifest.sources].reverse()}}),
    body=>({...body,send_basis:{...body.send_basis,request_id:'other-request'}}),
    body=>({...body,send_basis:{...body.send_basis,wire_sha256:'f'.repeat(64)}}),
  ]){
    const f=await selectedFixture();
    f.setPreviewOverride((remote,body)=>{const response=previewResponse(remote,body);return mutate(response);});
    assert.equal(await f.controller.previewContext(),false);
    assert.equal(f.controller.state.context.preview,null);
    assert.equal(f.controller.state.context.canSend,false);
    assert.equal(f.controller.state.context.error.code,'INVALID_RESPONSE');
  }
});

test('send confirms natively once, submits the same request and hands off to tracking',async()=>{
  const f=await selectedFixture();await f.controller.previewContext();
  assert.equal(await f.controller.send(),true);
  assert.equal(f.approvals.length,1);
  assert.deepEqual(f.approvals[0].citation_ids,['citation-0','citation-1']);
  assert.equal(f.approvals[0].request_id,f.previewCalls[0].request_id);
  const submits=f.calls.filter(call=>Array.isArray(call)&&call[0]==='submit');
  assert.equal(submits.length,1);
  assert.equal(submits[0][1].request_id,f.approvals[0].request_id);
  assert.equal(f.controller.state.context.phase,'tracking');
  assert.equal(f.controller.state.text,'','accepted answer clears the submitted question');
});

test('native cancellation never submits and returns to idle',async()=>{
  const f=await selectedFixture({answer:{ok:false,code:'APPROVAL_CANCELED',canceled:true}});
  await f.controller.previewContext();
  assert.equal(await f.controller.send(),false);
  assert.equal(f.calls.filter(call=>Array.isArray(call)&&call[0]==='submit').length,0);
  assert.equal(f.controller.state.context.phase,'idle');
  assert.notEqual(f.controller.state.text,'');
});

test('unknown submit outcome is recovered by the original lookup without resending',async()=>{
  const f=await selectedFixture();await f.controller.previewContext();
  const submit=f.api.submitContextGeneration;
  f.api.submitContextGeneration=async(...args)=>{const result=await submit(...args);throw Object.assign(Error('lost'),{code:'NETWORK_UNKNOWN',status:0});};
  assert.equal(await f.controller.send(),false);
  assert.equal(f.controller.state.context.phase,'unknown');
  assert.equal(await f.controller.refreshGeneration(),true);
  assert.equal(f.calls.filter(x=>x==='find').length,1);
  assert.equal(f.calls.filter(call=>Array.isArray(call)&&call[0]==='submit').length,1);
  assert.equal(f.controller.state.context.phase,'tracking');
});

test('without the desktop bridge preview works but sending stays closed',async()=>{
  const f=await selectedFixture({bridged:false});
  assert.equal(await f.controller.previewContext(),true);
  assert.equal(f.controller.state.context.preview.response.state,'ready');
  assert.equal(f.controller.state.context.canSend,false);
  assert.equal(await f.controller.send(),false);
  assert.equal(f.calls.filter(call=>Array.isArray(call)&&call[0]==='submit').length,0);
});

test('skill selection, materials, readonly or empty draft block selection and send',async()=>{
  for(const options of [{readonly:true}]){
    const f=fixture(options),c=f.controller;await c.open('one');
    c.toggleContextCitation('citation-0');
    assert.deepEqual(c.state.context.selected,[],'readonly never selects');
  }
  const f=await selectedFixture();
  f.controller.selectSkill('client_reply');
  assert.equal(f.controller.state.context.canPreview,false);
  assert.equal(await f.controller.previewContext(),false);
  f.controller.selectSkill(null);
  assert.equal(f.controller.state.context.canPreview,true);
});

test('revocation discards selection state and pending context work immediately',async()=>{
  const f=await selectedFixture();await f.controller.previewContext();
  const gate=deferred(),submit=f.api.submitContextGeneration;
  f.api.submitContextGeneration=async(...args)=>{await gate.promise;return submit(...args);};
  const sending=f.controller.send();await tick();
  f.controller.revoke({code:'AUTHORIZATION_REQUIRED',status:401});
  gate.resolve();await sending;
  assert.equal(f.controller.state.status,'revoked');
  assert.deepEqual(f.controller.state.context.selected,[]);
});
