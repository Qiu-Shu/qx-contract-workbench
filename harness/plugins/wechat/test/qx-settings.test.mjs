import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {apply} from '../qx-plugin.js';
import {WechatState} from '../state.js';
import {WechatLoginManager} from '../login.js';

async function setup(options={}){
  const root=options.root||await mkdtemp(join(tmpdir(),'qx-settings-'));
  const workspace=join(root,'workspace'),stateDir=join(root,'state');
  const routes=new Map(),cleanup=[],items=[
    {sessionId:'first',cwd:workspace,updatedAt:2,projections:{values:{title:'采购合同审查'}}},
    {sessionId:'second',cwd:workspace,updatedAt:1,projections:{values:{title:'劳动争议'}}},
    {sessionId:'archived',cwd:workspace,projections:{values:{title:'已归档'}}},
    {sessionId:'foreign',cwd:join(root,'other'),projections:{values:{title:'其他工作区'}}}];
  let created=0;
  const registry={archivedSessionIds:['archived'],async create(){return{async attachSession(){}}}};
  const controller={async list(){return{items}},async create(request){created++;items.push({sessionId:request.sessionId,cwd:workspace,updatedAt:3,projections:{values:{}}});return{sessionId:request.sessionId}}};
  const ctx={on(){},get:name=>name==='workspaceRegistry'?registry:name==='sessionController'?controller:undefined,
    effect(fn){const f=fn();if(typeof f==='function')cleanup.push(f)},inject(names,fn){fn(ctx)},
    tools:{register(){return()=>{}}},webServer:{register(route){routes.set(route.path,route.handler);return()=>{}}},
    agents:{get:id=>({session:{id}})}};
  await apply(ctx,{workspace,stateDir,sessionId:'first',autoConnect:false});
  async function request(path,body,token,beforeBody){
    let status,payload;
    const req={method:body?'POST':'GET',headers:{host:'127.0.0.1:3080',origin:'http://127.0.0.1:3080',...(token?{'x-qx-token':token}:{})},socket:{remoteAddress:'127.0.0.1'},async *[Symbol.asyncIterator](){beforeBody?.();yield JSON.stringify(body)}};
    const handler=routes.get(path);assert.ok(handler,'settings route exists');
    await handler(req,{writeHead(code){status=code},end(text){payload=JSON.parse(text)}});return{status,payload};
  }
  const settings=()=>request('/qx-wechat/settings');
  const action=async body=>request('/qx-wechat/action',body,(await settings()).payload.csrf);
  return{root,workspace,stateDir,settings,action,request,created:()=>created,close:()=>cleanup.reverse().forEach(fn=>fn())};
}

test('settings list persisted session names, exclude archived and other workspaces, and require CSRF for writes',async()=>{
  const env=await setup();try{
    const result=await env.settings();assert.equal(result.status,200);
    assert.deepEqual(result.payload.sessions.map(x=>x.title),['采购合同审查','劳动争议']);
    assert.equal((await env.request('/qx-wechat/action',{action:'session',sessionId:'second'})).status,403);
    assert.equal((await env.action({action:'session',sessionId:'foreign'})).status,400);
    assert.equal((await env.action({action:'session',sessionId:'second'})).status,200);
    assert.equal(JSON.parse(await readFile(join(env.stateDir,'qx-route.json'),'utf8')).sessionId,'second');
  }finally{env.close()}
});
test('new session is created, bound durably, and appears by name without a model request',async()=>{
  const env=await setup();try{
    const result=await env.action({action:'new-session'});assert.equal(result.status,200);
    assert.equal(env.created(),1);assert.ok(result.payload.sessionId.startsWith('session-'));
    assert.equal(JSON.parse(await readFile(join(env.stateDir,'qx-route.json'),'utf8')).sessionId,result.payload.sessionId);
    assert.ok((await env.settings()).payload.sessions.some(x=>x.id===result.payload.sessionId&&x.title==='新会话'));
  }finally{env.close()}
});
test('scan replacement selects the confirmed account and survives restart while keeping old credentials',async(t)=>{
  const root=await mkdtemp(join(tmpdir(),'qx-rescan-')),state=new WechatState({root:join(root,'state')});await state.init();
  await state.saveAccount('old',{userId:'old-owner',token:'synthetic-old',baseUrl:'https://example.invalid'});
  await state.saveAccount('new',{userId:'new-owner',token:'synthetic-new',baseUrl:'https://example.invalid'});
  t.mock.method(WechatLoginManager.prototype,'start',async()=>({id:'scan',status:'wait'}));
  t.mock.method(WechatLoginManager.prototype,'run',async()=>({status:'confirmed',accountId:'new'}));
  t.mock.method(globalThis,'fetch',async(_url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true})));
  const env=await setup({root});
  try{
    assert.equal((await env.action({action:'switch-account'})).status,200);
    for(let i=0;i<100;i++){if((await env.request('/qx-wechat/state')).payload.owner==='new-owner')break;await new Promise(r=>setTimeout(r,10))}
    assert.equal((await env.request('/qx-wechat/state')).payload.owner,'new-owner');
    assert.equal((await state.loadAccounts()).length,2);
    env.close();
    const restored=await setup({root});try{assert.equal((await restored.request('/qx-wechat/state')).payload.owner,'new-owner')}finally{restored.close()}
  }finally{env.close()}
});

test('confirmation remains locked until credentials and active account are ready',async(t)=>{
  let release,attempt;
  const gate=new Promise(resolve=>{release=resolve});
  t.mock.method(WechatLoginManager.prototype,'start',async()=>attempt={id:'scan',status:'wait'});
  t.mock.method(WechatLoginManager.prototype,'run',async attempt=>{await gate;return {...attempt,accountId:'new'}});
  t.mock.method(WechatState.prototype,'loadAccount',async()=>({userId:'new-owner',token:'synthetic-new',baseUrl:'https://example.invalid'}));
  t.mock.method(globalThis,'fetch',async(_url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true})));
  const env=await setup();try{
    assert.equal((await env.action({action:'switch-account'})).status,200);
    const csrf=(await env.settings()).payload.csrf;
    assert.equal((await env.request('/qx-wechat/action',{action:'pause'},csrf,()=>{attempt.status='confirmed'})).status,409);
    assert.equal((await env.request('/qx-wechat/state')).payload.login.status,'activating');
    for(const action of ['pause','resume','cancel','switch-account','new-session'])assert.equal((await env.action({action})).status,409,action);
    release();
    for(let i=0;i<100;i++){if((await env.request('/qx-wechat/state')).payload.connected)break;await new Promise(r=>setTimeout(r,10))}
    assert.equal((await env.request('/qx-wechat/state')).payload.owner,'new-owner');
    assert.equal((await env.action({action:'pause'})).status,200);
    assert.equal((await env.request('/qx-wechat/state')).payload.connected,false);
  }finally{release();env.close()}
});
