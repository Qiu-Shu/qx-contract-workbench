import assert from 'node:assert/strict';
import test from 'node:test';
import {createMaterialGenerationController} from '../src/cn_contract/web/static/assistant-material-generation.mjs';

const scope={workspace_id:'w',conversation_id:'c',scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:4,materials_revision:2};
const result=body=>({input_format:'material-business-v1',scope:{...body.expected_scope,
  input_revision:body.expected_scope.input_revision+1}});

function fixture({approval=true,native=true,onApprove=null}={}){
  const calls=[];
  const state={id:'c',text:'审查这份虚构合同',view:{scope:{...scope},composer_revision:3},
    status:'saved',loading:false,conflict:null,materials:{items:[{attachment_id:'f'}]},
    business:{selectedTask:'task',items:[{run_id:'parent',task_id:'task',workflow:'contract',scope:{materials_revision:2}}]}};
  const api={
    async submitMaterialGeneration(cid,body){calls.push(['submit',cid,structuredClone(body)]);return result(body);},
    async findGenerationRequest(cid,key){calls.push(['find',cid,key]);return null;},
  };
  const host={state,readonly:false,uuid:()=> 'request-1',notify:()=>{},token:()=>1,current:()=>true,
    blocked:()=>false,saveDraft:async()=>{calls.push(['save']);return true;},
    refreshDraft:async()=>{calls.push(['draft']);return true;},refreshHistory:async()=>{calls.push(['history']);return true;},
    accept:(body,value)=>calls.push(['accept',structuredClone(body),structuredClone(value)]),fail:()=>false,
    ...(native?{nativeMaterialAuthorization:async value=>{calls.push(['approve',structuredClone(value)]);
      return onApprove?onApprove(value):{ok:approval};}}:{})};
  return {state,api,host,calls,controller:createMaterialGenerationController(api,host)};
}

test('missing native capability or explicit cancellation never submits material',async()=>{
  for(const options of [{native:false},{approval:false}]){
    const f=fixture(options);
    assert.equal(await f.controller.send('parent'),false);
    assert.equal(f.calls.some(call=>call[0]==='submit'),false);
    assert.equal(f.state.materialGeneration.phase,'idle');
  }
});

test('one confirmation saves first and double click submits one exact request',async()=>{
  const f=fixture();
  const first=f.controller.send('parent'),second=f.controller.send('parent');
  assert.equal(await first,true);assert.equal(await second,false);
  assert.deepEqual(f.calls.map(call=>call[0]),['save','approve','submit','accept','draft','history']);
  const approval=f.calls[1][1],submitted=f.calls[2][2];
  assert.equal(approval.request_id,'request-1');assert.equal(submitted.request_id,'request-1');
  assert.equal(submitted.parent_business_run_id,'parent');assert.deepEqual(submitted.expected_scope,scope);
  assert.equal(submitted.expected_composer_revision,3);
});

test('changing input while native confirmation is open prevents submission',async()=>{
  const f=fixture({onApprove:()=>{f.state.text+='，新增要求';return {ok:true};}});
  assert.equal(await f.controller.send('parent'),false);
  assert.equal(f.calls.some(call=>call[0]==='submit'),false);
  assert.equal(f.state.materialGeneration.error.code,'INPUT_CHANGED');
});

test('network-unknown submission is recovered by GET with the original request identity',async()=>{
  const f=fixture();let body;
  f.api.submitMaterialGeneration=async(cid,value)=>{body=structuredClone(value);f.calls.push(['submit',cid,value]);throw {status:0,code:'NETWORK_UNKNOWN'};};
  f.api.findGenerationRequest=async(cid,key)=>{f.calls.push(['find',cid,key]);return result(body);};
  assert.equal(await f.controller.send('parent'),false);
  assert.equal(f.state.materialGeneration.phase,'unknown');
  assert.equal(await f.controller.send('parent'),true);
  assert.equal(f.calls.filter(call=>call[0]==='submit').length,1);
  assert.equal(f.calls.filter(call=>call[0]==='find').length,1);
  assert.equal(f.calls.find(call=>call[0]==='find')[2],'request-1');
});

test('reset while confirmation is open invalidates late approval',async()=>{
  let release;
  const gate=new Promise(resolve=>{release=resolve;});
  const f=fixture({onApprove:()=>gate});
  const sending=f.controller.send('parent');
  await new Promise(resolve=>setImmediate(resolve));
  f.controller.reset();release({ok:true});
  assert.equal(await sending,false);
  assert.equal(f.calls.some(call=>call[0]==='submit'),false);
});
