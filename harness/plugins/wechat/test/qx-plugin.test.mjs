import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, readdir, mkdir, writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {apply} from '../qx-plugin.js';
import {WechatState} from '../state.js';
import {encryptAesEcb,decryptAesEcb} from '../ilink.js';
import {createDesktopFileAccess} from '../qx-desktop-files.js';

function context({deferReplies=false,onFollowup=()=>{}}={}) {
  const routes=new Map(),tools=[],events=new Map(),disposers=[],messages=[],registered=[],attached=[];
  class Missing extends Error {}
  let created=0,resumed=0,turn=0;const completions=[];
  const agent={session:{id:'fixed-session'},followup(message){
    messages.push(message);
    const current=++turn;
    emit('agent/inbox/claimed',{agent,message,turn:current});
    const finish=()=>{emit('session/event',{id:'fixed-session'},{type:'assistant/message',data:{turn:current,message:{content:[{type:'text',text:'虚构测试回复'}]}}});
    emit('session/event',{id:'fixed-session'},{type:'turn/end',data:{turn:current,reason:{kind:'end_turn'}}});};
    if(deferReplies)completions.push(finish);else finish();onFollowup(message);
  }};
  function emit(name,...args){for(const fn of events.get(name)??[])fn(...args);}
  const ctx={
    on(name,fn){events.set(name,[...(events.get(name)??[]),fn]);},
    get(name){return name==='workspaceRegistry'?{async create(path){registered.push(path);return{id:'workspace',async attachSession(id){attached.push(id);}};}}:undefined;},effect(fn){const cleanup=fn();if(typeof cleanup==='function')disposers.push(cleanup);},
    inject(_names,fn){fn(ctx);},
    tools:{register(tool){tools.push(tool);return()=>{};}},webServer:{register(route){routes.set(route.path,route.handler);return()=>{};}},
    agents:{get(){return undefined;},async resume(){resumed++;if(!created)throw new Missing();return{agent,dispose(){}};},async create(args){assert.equal(args.sessionId,'fixed-session');created++;return{agent,dispose(){}};}},
    loader:{baseUrl:'test',internal:{async import(module){
      if(module.endsWith('session-persistence'))return{SessionPersistenceNotFoundError:Missing};
      if(module.endsWith('dsh-llm'))return{createUserMessage:input=>({id:`message-${turn+1}`,...input})};
      throw new Error('unexpected module '+module);
    }}},
  };
  return {ctx,routes,tools,messages,registered,attached,completeNext(){completions.shift()?.();},stop(){disposers.reverse().forEach(fn=>fn());},counts:()=>({created,resumed,turn})};
}
async function getState(env){let payload;await env.routes.get('/qx-wechat/state')({method:'GET',headers:{host:'127.0.0.1:3080'},socket:{remoteAddress:'127.0.0.1'}},{writeHead(){},end(text){payload=JSON.parse(text);}});return payload;}

async function waitFor(predicate, description) {
  const deadline = Date.now() + 30000;
  while (!await predicate()) {
    assert.ok(Date.now() < deadline, `Timed out waiting for ${description}`);
    await new Promise(resolve => setTimeout(resolve, 20));
  }
}

test('fresh installation mounts personal file lookup/send tools and settings, with no requests',async()=>{
  const root=await mkdtemp(join(tmpdir(),'qx-empty-'));
  const original=globalThis.fetch;globalThis.fetch=()=>{throw new Error('network forbidden');};
  const env=context();try{
    await apply(env.ctx,{workspace:join(root,'workspace'),stateDir:join(root,'state'),sessionId:'fixed-session'});
    assert.deepEqual(env.tools.map(t=>t.name),['wechat_find_desktop_files','wechat_send_file']);
    await assert.rejects(env.tools.find(t=>t.name==='wechat_find_desktop_files').execute({name:'合同'}),/尚未绑定/);
    assert.equal(env.routes.size,4);assert.equal((await getState(env)).connected,false);
    assert.deepEqual(env.counts(),{created:0,resumed:0,turn:0});
  }finally{env.stop();globalThis.fetch=original;}
});

test('selected synthetic desktop file reaches only bound owner with exact bytes through real send tool',async t=>{
  const root=await mkdtemp(join(tmpdir(),'qx-desktop-send-'));t.after(()=>rm(root,{recursive:true,force:true}));
  const workspace=join(root,'workspace'),desktop=join(root,'desktop'),stateDir=join(root,'state');
  await mkdir(workspace);await mkdir(desktop);
  const bytes=Buffer.from('synthetic requested contract');await writeFile(join(desktop,'合同.docx'),bytes);
  const access=createDesktopFileAccess({workspace,getDirectories:async()=>[desktop]});
  const candidates=await access.find('合同');assert.equal(candidates.files.length,1);
  const staged=await access.prepare(candidates.files[0].path);
  const state=new WechatState({root:stateDir});
  await state.saveAccount('bot',{token:'synthetic-token',baseUrl:'https://example.invalid',userId:'owner',botId:'bot'});
  await state.saveContextToken('bot','owner','synthetic-context');
  const sent=[];let uploadKey;const original=globalThis.fetch;
  globalThis.fetch=async(url,options)=>{
    if(String(url).includes('getupdates'))return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true}));
    if(String(url).includes('getuploadurl')){
      const body=JSON.parse(options.body);assert.equal(body.to_user_id,'owner');uploadKey=Buffer.from(body.aeskey,'hex');
      return new Response(JSON.stringify({upload_full_url:'https://example.invalid/test-upload'}));
    }
    if(String(url)==='https://example.invalid/test-upload'){
      assert.deepEqual(decryptAesEcb(Buffer.from(options.body),uploadKey),bytes);
      return new Response('',{headers:{'x-encrypted-param':'synthetic-download'}});
    }
    if(String(url).includes('sendmessage')){sent.push(JSON.parse(options.body));return new Response(JSON.stringify({ret:0}));}
    throw Error('Unexpected network call');
  };
  const env=context();try{
    await apply(env.ctx,{workspace,stateDir,sessionId:'fixed-session'});
    const tool=env.tools.find(x=>x.name==='wechat_send_file');assert.deepEqual(Object.keys(tool.parameters),['path']);
    assert.match(await tool.execute({path:staged}),/已发回本人微信/);
    assert.equal(sent.length,1);assert.equal(sent[0].msg.to_user_id,'owner');
    assert.equal(sent[0].msg.item_list[0].file_item.file_name,'合同.docx');
    assert.deepEqual(await readFile(join(desktop,'合同.docx')),bytes);
  }finally{env.stop();globalThis.fetch=original;}
});

test('local prepare creates the fixed empty desktop session without calling a model or WeChat',async()=>{
  const root=await mkdtemp(join(tmpdir(),'qx-prepare-')),env=context();
  const original=globalThis.fetch;globalThis.fetch=()=>{throw new Error('network forbidden');};
  try {
    await apply(env.ctx,{workspace:join(root,'workspace'),stateDir:join(root,'state'),sessionId:'fixed-session'});
    let html='';const req={method:'GET',headers:{host:'127.0.0.1:3080'},socket:{remoteAddress:'127.0.0.1'}};
    await env.routes.get('/qx-wechat')(req,{writeHead(){},end(text){html=text;}});
    const token=html.match(/'x-qx-token':'([^']+)'/)[1];
    let status,body;
    await env.routes.get('/qx-wechat/action')({...req,method:'POST',headers:{...req.headers,'x-qx-token':token},async *[Symbol.asyncIterator](){yield JSON.stringify({action:'prepare'});}},{writeHead(value){status=value;},end(value){body=JSON.parse(value);}});
    assert.equal(status,200,JSON.stringify(body));
    assert.deepEqual(env.counts(),{created:1,resumed:1,turn:0});
    assert.deepEqual(env.registered,[join(root,'workspace')]);
    assert.deepEqual(env.attached,['fixed-session']);
  }finally{env.stop();globalThis.fetch=original;}
});

test('a previously materialized route with missing storage is not replaced by an empty session',async()=>{
  const root=await mkdtemp(join(tmpdir(),'qx-missing-history-')),stateDir=join(root,'state'),env=context();
  await mkdir(stateDir);await writeFile(join(stateDir,'qx-route.json'),JSON.stringify({sessionId:'fixed-session'}));
  try{
    await apply(env.ctx,{workspace:join(root,'workspace'),stateDir,sessionId:'fixed-session'});
    let html='';const req={method:'GET',headers:{host:'127.0.0.1:3080'},socket:{remoteAddress:'127.0.0.1'}};
    await env.routes.get('/qx-wechat')(req,{writeHead(){},end(text){html=text;}});
    const token=html.match(/'x-qx-token':'([^']+)'/)[1];let status;
    await env.routes.get('/qx-wechat/action')({...req,method:'POST',headers:{...req.headers,'x-qx-token':token},async *[Symbol.asyncIterator](){yield '{"action":"prepare"}';}},{writeHead(value){status=value;},end(){}});
    assert.equal(status,400);assert.equal(env.counts().created,0);
  }finally{env.stop();}
});

test('synthetic owner burst preserves good text and attachment, flags failed media, ignores peers and duplicates',async()=>{
  const root=await mkdtemp(join(tmpdir(),'qx-wire-')), stateDir=join(root,'state');
  const state=new WechatState({root:stateDir});
  await state.saveAccount('bot',{token:'synthetic-not-real',baseUrl:'https://example.invalid',userId:'owner',botId:'bot'});
  const owner=(id,text)=>({message_id:id,from_user_id:'owner',message_type:1,context_token:'synthetic-context',item_list:[{type:1,text_item:{text}}]});
  let polls=0;const sends=[];const original=globalThis.fetch;
  const bytes=Buffer.from('synthetic attachment only'), key=Buffer.alloc(16,7);
  const attached=owner('one','first');
  attached.item_list.push({type:4,file_item:{file_name:'agreement.txt',media:{full_url:'https://example.invalid/media',aes_key:key.toString('base64')}}});
  attached.item_list.push({type:4,file_item:{file_name:'missing.txt',media:{full_url:'https://example.invalid/broken',aes_key:key.toString('base64')}}});
  globalThis.fetch=async(url,options)=>{
    if(String(url).includes('getupdates')){
      if(polls++===0)return new Response(JSON.stringify({ret:0,get_updates_buf:'cursor',msgs:[
        {...owner('other','ignored'),from_user_id:'stranger'},
        {...owner('group','ignored'),group_id:'group'},
        attached,owner('one','redelivery'),owner('two','continue'),
      ]}));
      return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true}));
    }
    if(String(url).includes('sendmessage')){sends.push(JSON.parse(options.body));return new Response(JSON.stringify({ret:0}));}
    if(String(url)==='https://example.invalid/broken')return new Response('synthetic unavailable',{status:503});
    if(String(url)==='https://example.invalid/media')return new Response(encryptAesEcb(bytes,key));
    throw new Error('unexpected external call '+url);
  };
  const env=context();try{
    await apply(env.ctx,{workspace:join(root,'workspace'),stateDir,sessionId:'fixed-session',coalesceQuietMs:30,coalesceMediaQuietMs:50});
    await waitFor(() => sends.length >= 1, 'the owner reply after protected credential persistence');
    assert.equal(sends.length,1);assert.ok(sends.every(s=>s.msg.to_user_id==='owner'));
    assert.deepEqual(env.counts(),{created:1,resumed:1,turn:1});
    assert.equal((await getState(env)).ignored,2);
    assert.deepEqual(JSON.parse(await readFile(join(stateDir,'qx-route.json'),'utf8')),{sessionId:'fixed-session'});
    const inbox=join(root,'workspace','wechat-inbox');
    const paths=await readdir(inbox,{recursive:true,withFileTypes:true});
    const file=paths.find(entry=>entry.isFile());
    assert.ok(file);const saved=join(file.parentPath,file.name);
    assert.deepEqual(await readFile(saved),bytes);
    assert.ok(env.messages[0].content[0].text.includes(saved));
    assert.ok(env.messages[0].content[0].text.indexOf('first')<env.messages[0].content[0].text.indexOf('continue'));
    assert.ok(!env.messages[0].content[0].text.includes('redelivery'));
    assert.ok(env.messages[0].content[0].text.includes('附件未读取'));assert.ok(env.messages[0].content[0].text.includes('不得推断其内容'));assert.ok(env.messages[0].content[0].text.includes('请求补发'));
    const pending=JSON.parse(await readFile(join(stateDir,'qx-pending.json'),'utf8'));
    assert.equal(pending.history.length,1);assert.equal(pending.history[0].messageIds.length,2);assert.equal(pending.history[0].warningCount,1);
  }finally{env.stop();globalThis.fetch=original;}
});


test('actual plugin keeps polling and persists the next burst while the first model turn is unfinished',async()=>{
  const root=await mkdtemp(join(tmpdir(),'qx-nonblocking-')),stateDir=join(root,'state');
  const state=new WechatState({root:stateDir});
  await state.saveAccount('bot',{token:'synthetic-not-real',baseUrl:'https://example.invalid',userId:'owner',botId:'bot'});
  const owner=(id,text)=>({message_id:id,from_user_id:'owner',message_type:1,context_token:'synthetic-context',item_list:[{type:1,text_item:{text}}]});
  let firstStarted;const first=new Promise(r=>{firstStarted=r;});let polls=0;const sends=[];
  const env=context({deferReplies:true,onFollowup:()=>firstStarted()});const original=globalThis.fetch;
  globalThis.fetch=async(url,options)=>{
    if(String(url).includes('getupdates')){
      const n=polls++;
      if(n===0)return new Response(JSON.stringify({ret:0,get_updates_buf:'cursor-1',msgs:[owner('one','第一批')]}));
      if(n===1){await first;return new Response(JSON.stringify({ret:0,get_updates_buf:'cursor-2',msgs:[owner('two','第二批上半段'),owner('three','第二批补充'),owner('three','重复')]}));}
      return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true}));
    }
    if(String(url).includes('sendmessage')){sends.push(JSON.parse(options.body));return new Response(JSON.stringify({ret:0}));}
    throw new Error('unexpected external call');
  };
  try{
    await apply(env.ctx,{workspace:join(root,'workspace'),stateDir,sessionId:'fixed-session',coalesceQuietMs:20,coalesceMediaQuietMs:30});
    await waitFor(async () => (await getState(env)).batching.pendingMessages === 2 && await state.loadCursor('bot') === 'cursor-2', 'the persisted second burst');
    let snapshot=await getState(env);assert.equal(snapshot.batching.active,true);assert.equal(snapshot.batching.pendingMessages,2);assert.equal(env.messages.length,1);assert.equal(sends.length,0);assert.ok(polls>=2);
    const pending=JSON.parse(await readFile(join(stateDir,'qx-pending.json'),'utf8'));
    assert.equal(pending.pending[0].items.length,2);assert.equal(await state.loadCursor('bot'),'cursor-2');
    assert.ok(!JSON.stringify(pending).includes('synthetic-context'));assert.ok(!JSON.stringify(pending).includes('synthetic-not-real'));
    env.completeNext();
    await waitFor(() => env.messages.length >= 2, 'the second model turn');
    assert.equal(env.messages.length,2);assert.equal(sends.length,1);assert.ok(env.messages[1].content[0].text.includes('第二批上半段'));assert.ok(env.messages[1].content[0].text.includes('第二批补充'));assert.ok(!env.messages[1].content[0].text.includes('重复'));
    env.completeNext();await waitFor(async () => !(await getState(env)).batching.active, 'the completed second reply');
    assert.equal(sends.length,2);snapshot=await getState(env);assert.equal(snapshot.batching.pendingMessages,0);assert.equal(snapshot.batching.failed,0);
  }finally{env.completeNext();env.stop();globalThis.fetch=original;}
});


test('an unreadable attachment-only batch reports failure without a model request',async()=>{
 const root=await mkdtemp(join(tmpdir(),'qx-empty-media-')),stateDir=join(root,'state'),env=context();
 const state=new WechatState({root:stateDir});await state.saveAccount('bot',{token:'synthetic',baseUrl:'https://example.invalid',userId:'owner',botId:'bot'});
 let polls=0;const sends=[];const original=globalThis.fetch;
 globalThis.fetch=async(url,options)=>{
  if(String(url).includes('getupdates')){if(polls++===0)return new Response(JSON.stringify({ret:0,msgs:[{message_id:'bad',from_user_id:'owner',message_type:1,context_token:'synthetic-context',item_list:[{type:4,file_item:{file_name:'bad.txt',media:{full_url:'https://example.invalid/bad',aes_key:Buffer.alloc(16).toString('base64')}}}]}]}));return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true}));}
  if(String(url).includes('sendmessage')){sends.push(JSON.parse(options.body));return new Response(JSON.stringify({ret:0}));}
  return new Response('unavailable',{status:503});
 };
 try{
  await apply(env.ctx,{workspace:join(root,'workspace'),stateDir,sessionId:'fixed-session',coalesceMediaQuietMs:20});
  await waitFor(async () => (await getState(env)).batching.failed > 0, 'the unreadable-attachment failure reply');
  assert.equal(env.messages.length,0);assert.equal(sends.length,1);assert.equal((await getState(env)).batching.failed,1);assert.match(JSON.stringify(sends),/没有可读取内容/);
 }finally{env.stop();globalThis.fetch=original;}
});
