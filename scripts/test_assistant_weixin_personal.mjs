import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {bindPersonalWeixin} from '../src/cn_contract/web/static/assistant-weixin-personal.mjs';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';
const cid='11111111-2222-4333-8444-555555555555',other='22222222-2222-4333-8444-555555555555';
const defer=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve:v=>resolve(v)};};
const tick=()=>new Promise(setImmediate);
class Element{
  constructor(){this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.attrs=new Map();this.listeners=new Map();this.writes=[];}
  setAttribute(k,v){this.writes.push([k,v]);this.attrs.set(k,v);}getAttribute(k){return this.attrs.get(k);}removeAttribute(k){this.attrs.delete(k);}
  addEventListener(k,fn){this.listeners.set(k,fn);}fire(k){return this.listeners.get(k)?.({preventDefault(){}});}focus(){this.focused=true;}
}
function fixture(options={}){
  const els=new Map(),calls=[];let blocked=false,read={ok:true,connection:null};
  const document={getElementById(id){if(!els.has(id))els.set(id,new Element());return els.get(id);}};
  const controller={state:{id:cid,status:'saved',loading:false,view:{},text:''}};
  const bridge={};for(const key of ['Start','Disable','Verify'])bridge['personalWeixin'+key]=async(...args)=>{calls.push([key,...args]);return {ok:true};};
  bridge.personalWeixinStatus=async()=>structuredClone(read);
  const incoming=[];const ui=bindPersonalWeixin({controller,bridge,document,isBlocked:()=>blocked,
    onIncoming:async()=>incoming.push(controller.state.text),setTimer:()=>1,clearTimer:()=>{},...options});
  ui.state(controller.state);
  return {ui,controller,bridge,calls,incoming,at:name=>document.getElementById('personal-weixin-'+name),
    blocked:value=>blocked=value,status:value=>read={ok:true,connection:{state:'connected',conversation_id:cid,automatic:true,notice:'虚构',qr_ready:false,...value}}};
}
test('plain browser and restored copy cannot connect',async()=>{
  for(const options of [{bridge:null},{readonly:true}]){const f=fixture(options);await f.ui.refresh();assert.equal(f.at('start').disabled,true);await f.at('start').fire('click');assert.equal(f.calls.length,0);f.ui.dispose();}
});
test('native intent contains no renderer identity or policy and duplicate click is blocked',async()=>{
  const f=fixture();await f.ui.refresh();const hold=defer();f.bridge.personalWeixinStart=(...args)=>{f.calls.push(['Start',...args]);return hold.promise;};
  const pending=f.at('start').fire('click');await f.at('start').fire('click');assert.deepEqual(f.calls,[['Start']]);
  hold.resolve({ok:true});await pending;await tick();f.ui.dispose();
});
test('connection keeps original CID while browsing; QR never crosses into other chat',async()=>{
  const f=fixture();f.status({state:'waiting_scan',qr_ready:true});await f.ui.refresh();
  assert.equal(f.at('qr').getAttribute('src'),'/api/assistant/conversations/'+cid+'/personal-weixin/qr.svg');
  f.controller.state.id=other;f.ui.state(f.controller.state);await f.ui.refresh();
  assert.equal(f.at('origin').hidden,false);assert.equal(f.at('origin').href,'/assistant/'+cid);
  assert.match(f.at('scope').textContent,/原聊天/);assert.equal(f.at('start').disabled,true);
  assert.equal(f.at('qr').getAttribute('src'),undefined);assert.equal(f.at('disable').hidden,false);f.ui.dispose();
});
test('late status cannot replace the new page state',async()=>{
  const f=fixture(),hold=defer();f.bridge.personalWeixinStatus=()=>hold.promise;const pending=f.ui.refresh();
  f.controller.state.id=other;f.ui.state(f.controller.state);hold.resolve({ok:true,connection:{conversation_id:cid,state:'waiting_scan',qr_ready:true}});await pending;
  assert.equal(f.at('qr').getAttribute('src'),undefined);assert.match(f.at('summary').textContent,/核对/);f.ui.dispose();
});
test('explicit refresh retries a failed local QR without starting another connection',async()=>{
  const f=fixture();f.status({state:'waiting_scan',qr_ready:true});await f.ui.refresh();
  const src=f.at('qr').getAttribute('src'),writes=f.at('qr').writes.length;
  f.at('qr').fire('error');assert.equal(f.at('qr-frame').hidden,true);
  await f.ui.refresh();assert.equal(f.at('qr').writes.length,writes);assert.equal(f.at('qr-frame').hidden,true);
  await f.at('refresh').fire('click');await tick();
  assert.equal(f.at('qr').getAttribute('src'),src);assert.ok(f.at('qr').writes.length>writes);
  assert.equal(f.at('qr-frame').hidden,false);assert.deepEqual(f.calls,[]);f.ui.dispose();
});
test('verification copy does not claim the code stays only on this computer',()=>{
  const html=readFileSync(new URL('../src/cn_contract/web/templates/assistant.html',import.meta.url),'utf8');
  assert.match(html,/验证码用于本次微信连接，不会显示在聊天中/);assert.doesNotMatch(html,/验证码仅在本机提交/);
});
test('dirty composer is kept while read-only incoming refresh runs',async()=>{
  const f=fixture();f.controller.state.text='未发送文字';f.controller.state.dirty=true;f.status({});await f.ui.refresh();
  assert.equal(f.controller.state.text,'未发送文字');assert.deepEqual(f.incoming,['未发送文字']);assert.deepEqual(f.calls,[]);f.ui.dispose();
});
test('worksheet/material/local pending pauses history refresh but keeps connection status',async()=>{
  const f=fixture();f.status({});f.blocked(true);await f.ui.refresh();assert.equal(f.incoming.length,0);assert.match(f.at('summary').textContent,/已连接/);
  f.blocked(false);await f.ui.refresh();assert.equal(f.incoming.length,1);f.ui.dispose();
});
test('keyboard verification uses text preserving leading zeros and clears after success/close',async()=>{
  const f=fixture();f.status({state:'need_verifycode'});await f.ui.refresh();
  f.at('code').value='001234';await f.at('verify-form').fire('submit');await tick();
  assert.deepEqual(f.calls,[['Verify','001234']]);assert.equal(f.at('code').value,'');
  f.at('code').value='1234';f.at('panel').open=false;f.at('panel').fire('toggle');assert.equal(f.at('code').value,'');f.ui.dispose();
});
test('invalid code never reaches native bridge; revoked state clears code and QR',async()=>{
  const f=fixture();f.status({state:'need_verifycode'});await f.ui.refresh();f.at('code').value='１２３４';f.at('verify-form').fire('submit');await tick();
  assert.deepEqual(f.calls,[]);f.controller.state.status='revoked';f.ui.state(f.controller.state);
  assert.equal(f.at('code').value,'');assert.equal(f.at('qr').getAttribute('src'),undefined);f.ui.dispose();
});
test('unknown status never presents disconnected as confirmed',async()=>{
  const f=fixture();f.bridge.personalWeixinStatus=async()=>({ok:false});await f.ui.refresh();assert.equal(f.at('start').disabled,true);
  assert.match(f.at('state').textContent,/尚未确认/);f.ui.dispose();
});
test('background controller refresh retains text and conflict; pending guard prevents late apply',async()=>{
  const scope={workspace_id:'work',conversation_id:cid,scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0};
  let remote={scope,draft_input:'',composer_revision:0,messages:[],latest_run:null,next_before:null},hold=null;
  const controller=createDraftController({getConversation:async()=>hold?hold.promise:structuredClone(remote)});
  await controller.open(cid);controller.edit('本地草稿');remote={...remote,scope:{...scope,input_revision:1},draft_input:'新服务端草稿',composer_revision:1};
  let localPending=false;hold=defer();const pending=controller.refresh(false,()=>!localPending);localPending=true;hold.resolve(structuredClone(remote));
  assert.equal(await pending,false);assert.equal(controller.state.view.composer_revision,0);assert.equal(controller.state.text,'本地草稿');
  hold=null;localPending=false;assert.equal(await controller.refresh(false,()=>!localPending),false);
  assert.equal(controller.state.text,'本地草稿');assert.equal(controller.state.conflict.server,'新服务端草稿');controller.close();
});
