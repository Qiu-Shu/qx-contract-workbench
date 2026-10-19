import assert from 'node:assert/strict';
import test from 'node:test';
import {request} from '../src/cn_contract/web/static/assistant-api.mjs';
import * as api from '../src/cn_contract/web/static/assistant-api.mjs';
import {bindComposer} from '../src/cn_contract/web/static/assistant-composer.mjs';

test('same-origin transport carries CSRF only on writes and preserves original request identity',async()=>{
  const oldFetch=globalThis.fetch, oldDocument=globalThis.document;
  const seen=[];
  globalThis.document={cookie:'other=x; qx_csrf=synthetic%20token'};
  globalThis.fetch=async(path,options)=>{seen.push({path,options});return {ok:true,json:async()=>({ok:true})};};
  try {
    await request('/api/assistant/skills');
    await request('/api/assistant/conversations',{method:'POST',body:{request_id:'same-synthetic-id'}});
    assert.equal(seen[0].options.headers['X-CSRF-Token'],undefined);
    assert.equal(seen[1].options.headers['X-CSRF-Token'],'synthetic token');
    assert.equal(JSON.parse(seen[1].options.body).request_id,'same-synthetic-id');
    assert.equal(seen[1].options.credentials,'same-origin');
    assert.equal(seen[1].options.cache,'no-store');
  } finally {globalThis.fetch=oldFetch;globalThis.document=oldDocument;}
});

test('network and invalid responses are unknown, not proof a write failed',async()=>{
  const oldFetch=globalThis.fetch;
  try {
    globalThis.fetch=async()=>{throw Error('private transport diagnostic');};
    await assert.rejects(request('/api/assistant/skills'),error=>error.code==='NETWORK_UNKNOWN' && error.status===0);
    globalThis.fetch=async()=>({ok:true,status:200,json:async()=>{throw Error('private data');}});
    await assert.rejects(request('/api/assistant/skills'),error=>error.code==='NETWORK_UNKNOWN');
    globalThis.fetch=async()=>({ok:false,status:401,json:async()=>({code:'AUTHORIZATION_REQUIRED',message:'private raw value'})});
    await assert.rejects(request('/api/assistant/skills'),error=>error.code==='AUTHORIZATION_REQUIRED' && error.status===401 && !error.message.includes('private'));
  } finally {globalThis.fetch=oldFetch;}
});

test('generation transport keeps registration explicit and history bounded to requested identities',async()=>{
  const oldFetch=globalThis.fetch,oldDocument=globalThis.document,seen=[];
  globalThis.document={cookie:'qx_csrf=synthetic'};
  globalThis.fetch=async(path,options)=>{seen.push({path,options});return {ok:true,json:async()=>({})};};
  try {
    await api.getGenerationCapability('conversation');
    await api.submitGeneration('conversation',{request_id:'fixed-id',content:'合成文字'});
    await api.findGenerationRequest('conversation','fixed-id');
    await api.getGenerationAttempt('attempt');
    await api.getGenerationHistory('conversation',['message-one','message-two']);
    assert.deepEqual(seen.map(x=>x.options.method),['GET','POST','GET','GET','GET']);
    assert.equal(seen[0].path,'/api/assistant/conversations/conversation/generation-capability');
    assert.equal(seen[1].path,'/api/assistant/conversations/conversation/generations');
    assert.deepEqual(JSON.parse(seen[1].options.body),{request_id:'fixed-id',content:'合成文字'});
    assert.equal(seen[2].path,'/api/assistant/conversations/conversation/generations/by-request/fixed-id');
    assert.equal(seen[3].path,'/api/assistant/attempts/attempt');
    assert.deepEqual(new URL(seen[4].path,'http://localhost').searchParams.getAll('message_id'),['message-one','message-two']);
    assert.equal(seen.filter(x=>x.options.method==='POST').length,1);
  } finally {globalThis.fetch=oldFetch;globalThis.document=oldDocument;}
});

test('transport abandons a stalled connection with an unknown outcome',async()=>{
  const oldFetch=globalThis.fetch, oldSet=globalThis.setTimeout, oldClear=globalThis.clearTimeout;
  let abort, signal;
  globalThis.setTimeout=callback=>{abort=callback;return 1;};
  globalThis.clearTimeout=()=>{};
  globalThis.fetch=async(path,options)=>{
    signal=options.signal;
    if(!signal)return {ok:true,json:async()=>({unbounded:true})};
    return new Promise((resolve,reject)=>{
      signal.addEventListener('abort',()=>reject(Error('aborted')));
      queueMicrotask(()=>abort());
    });
  };
  try {
    await assert.rejects(request('/api/assistant/skills'),error=>error.code==='NETWORK_UNKNOWN');
    assert.equal(signal.aborted,true);
  }
  finally {globalThis.fetch=oldFetch;globalThis.setTimeout=oldSet;globalThis.clearTimeout=oldClear;}
});

test('Enter, Shift+Enter, held keys and composition boundaries keep native input intact',()=>{
  const original=globalThis.performance;
  let now=1000,sends=0;const edits=[];
  globalThis.performance={now:()=>now};
  const input=new EventTarget();input.value='中文草稿';const form=new EventTarget();
  const bound=bindComposer({input,form,onEdit:text=>edits.push(text),onSend:()=>sends++});
  function key(values={}) {
    const event=new Event('keydown',{cancelable:true});
    Object.assign(event,{key:'Enter',shiftKey:false,isComposing:false,repeat:false,keyCode:13,...values});
    input.dispatchEvent(event);return event;
  }
  try {
    assert.equal(key().defaultPrevented,true);assert.equal(sends,1);
    assert.equal(key({shiftKey:true}).defaultPrevented,false);assert.equal(sends,1);
    key({repeat:true});assert.equal(sends,1);
    key({isComposing:true});key({keyCode:229});assert.equal(sends,1);
    input.dispatchEvent(new Event('compositionstart'));
    key();input.dispatchEvent(new Event('input'));assert.equal(sends,1);assert.deepEqual(edits,[]);
    input.dispatchEvent(new Event('compositionend'));key();assert.equal(sends,1);assert.deepEqual(edits,['中文草稿']);
    now+=200;key();assert.equal(sends,2);
    assert.equal(input.value,'中文草稿');
    bound.dispose();key();input.dispatchEvent(new Event('input'));assert.equal(sends,2);assert.equal(edits.length,1);
  } finally {globalThis.performance=original;bound.dispose();}
});
