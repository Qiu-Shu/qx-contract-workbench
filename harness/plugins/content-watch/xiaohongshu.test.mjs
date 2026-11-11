import test from 'node:test';
import assert from 'node:assert/strict';
import {createXhsClient,LoginRequiredError} from './xiaohongshu.mjs';

const ok=data=>Response.json({success:true,data});
const profile={practice:'劳动争议',targetClients:'中小企业'};
const card=(id,likes='12',extra={})=>({id,modelType:'note',xsecToken:'private-signature',noteCard:{displayTitle:'劳动争议怎么处理',type:'normal',user:{nickname:'示例作者'},interactInfo:{likedCount:likes},...extra}});

test('only explicit loopback HTTP service addresses are accepted',()=>{
  for(const baseUrl of ['https://127.0.0.1:18060','http://example.com:18060','http://127.0.0.1:18060/mcp','http://user:secret@127.0.0.1:18060','http://127.0.0.1:18060/?token=x']){
    assert.throws(()=>createXhsClient({baseUrl}),/本机/);
  }
  for(const baseUrl of ['http://127.0.0.1:18060','http://localhost:18060','http://[::1]:18060'])assert.ok(createXhsClient({baseUrl}));
});

test('login status is mapped without exposing unrelated service fields',async()=>{
  let request;
  const client=createXhsClient({authToken:()=> 'local-service-secret',fetchImpl:async(url,options)=>{request={url,options};return ok({is_logged_in:true,username:'本人',cookies:'never return'});}});
  assert.deepEqual(await client.checkLogin(),{loggedIn:true,username:'本人'});
  assert.equal(new URL(request.url).pathname,'/api/v1/login/status');
  assert.equal(request.options.headers.authorization,'Bearer local-service-secret');
  assert.equal(request.options.redirect,'error');
});

test('not logged in is observable and blocks collection before search',async()=>{
  let requests=0;
  const client=createXhsClient({fetchImpl:async()=>{requests++;return ok({is_logged_in:false});}});
  assert.deepEqual(await client.checkLogin(),{loggedIn:false});
  await assert.rejects(client.collect(profile),error=>error instanceof LoginRequiredError&&error.code==='LOGIN_REQUIRED');
  assert.equal(requests,2);
});

test('QR response only returns the image and expiry metadata',async()=>{
  const img='data:image/png;base64,aGVsbG8=';
  const client=createXhsClient({fetchImpl:async()=>ok({img,timeout:'4m0s',is_logged_in:false,cookies:'secret'})});
  assert.deepEqual(await client.loginQr(),{img,timeout:'4m0s',isLoggedIn:false});
});

test('already logged in QR response does not require an image',async()=>{
  const client=createXhsClient({fetchImpl:async()=>ok({img:'',timeout:'0s',is_logged_in:true})});
  assert.deepEqual(await client.loginQr(),{img:'',timeout:'0s',isLoggedIn:true});
});

test('collection uses read endpoints, deduplicates and normalizes real detail shapes',async()=>{
  const calls=[];
  const client=createXhsClient({fetchImpl:async(url,options)=>{
    const path=new URL(url).pathname;const body=options.body&&JSON.parse(options.body);calls.push({path,body});
    if(path.endsWith('/login/status'))return ok({is_logged_in:true});
    if(path.endsWith('/feeds/search'))return ok({feeds:[card('note1','1.2万'),card('note1'),card('note2','--',{type:'video'})]});
    return ok({feed_id:body.feed_id,data:{note:{noteId:body.feed_id,title:'劳动争议处理',desc:'这是实际取得的正文。',type:body.feed_id==='note2'?'video':'normal',time:1739536450000,user:{nickname:'详情作者'},interactInfo:{likedCount:body.feed_id==='note1'?'1.2万':'',commentCount:'0',collectedCount:'2.5千',sharedCount:'3'}}}});
  }});
  const result=await client.collect(profile);
  assert.equal(result.items.length,2);
  const item=result.items.find(item=>item.id==='note1');
  assert.equal(item.likes,12000);assert.equal(item.comments,0);assert.equal(item.collected,2500);assert.equal(item.shares,3);
  assert.equal(item.publishedAt,'2025-02-14T12:34:10.000Z');
  assert.equal(item.text,'这是实际取得的正文。');assert.equal(item.textCoverage,'正文');
  assert.equal(item.url,'https://www.xiaohongshu.com/explore/note1');
  assert.equal(result.items.find(item=>item.id==='note2').textCoverage,'标题简介');
  assert.equal(result.items.find(item=>item.id==='note2').likes,null);
  assert.ok(item.keywords.some(keyword=>keyword.includes('中小企业')));
  assert.ok(!JSON.stringify(result).includes('private-signature'));
  assert.ok(calls.every(call=>['/api/v1/login/status','/api/v1/feeds/search','/api/v1/feeds/detail'].includes(call.path)));
  for(const call of calls.filter(call=>call.path.endsWith('/feeds/search')))assert.equal(call.body.filters.publish_time,'一周内');
  for(const call of calls.filter(call=>call.path.endsWith('/feeds/detail')))assert.equal(call.body.load_all_comments,false);
});

test('bounded sampling skips live cards and reads at most six details',async()=>{
  let searches=0,details=0;
  const client=createXhsClient({fetchImpl:async(url,options)=>{
    const path=new URL(url).pathname;
    if(path.endsWith('/login/status'))return ok({is_logged_in:true});
    if(path.endsWith('/feeds/search')){searches++;return ok({feeds:[{id:'live',modelType:'live_v2'},...Array.from({length:30},(_,i)=>card('n'+i,String(i)))]});}
    details++;const body=JSON.parse(options.body);return ok({data:{note:{noteId:body.feed_id,title:'标题',desc:'正文',type:'normal'}}});
  }});
  const result=await client.collect({practice:'劳动、合同、婚姻、刑事',targetClients:'企业'});
  assert.ok(searches<=3);assert.equal(details,6);assert.ok(result.items.length<=20);assert.ok(!result.items.some(item=>item.id==='live'));
  assert.ok(result.warnings.some(item=>item.includes('样本')));
});

test('seen items are removed before bounded details so later runs can discover the next candidates',async()=>{
  const details=[];
  const client=createXhsClient({fetchImpl:async(url,options)=>{
    const path=new URL(url).pathname;
    if(path.endsWith('/login/status'))return ok({is_logged_in:true});
    if(path.endsWith('/feeds/search'))return ok({feeds:Array.from({length:8},(_,i)=>card('n'+i,String(100-i)))});
    const body=JSON.parse(options.body);details.push(body.feed_id);return ok({data:{note:{noteId:body.feed_id,desc:'合成正文'}}});
  }});
  const result=await client.collect(profile,{seenIds:['n0','n1','n2','n3','n4','n5']});
  assert.deepEqual(details,['n6','n7']);assert.deepEqual(result.items.map(item=>item.id),['n6','n7']);
});

test('unknown metrics and unread detail stay explicitly missing',async()=>{
  const client=createXhsClient({fetchImpl:async(url)=>{
    const path=new URL(url).pathname;
    if(path.endsWith('/login/status'))return ok({is_logged_in:true});
    if(path.endsWith('/feeds/search'))return ok({feeds:[card('one','--')]});
    return Response.json({error:'页面不存在',details:'secret-token'},{status:500});
  }});
  const result=await client.collect(profile);
  assert.equal(result.items[0].likes,null);assert.equal(result.items[0].publishedAt,null);
  assert.equal(result.items[0].textCoverage,'标题简介');assert.ok(result.warnings.some(item=>item.includes('正文')));
  assert.ok(!JSON.stringify(result).includes('secret-token'));
});

test('HTTP 200 failure is not silently accepted as an empty search',async()=>{
  const client=createXhsClient({fetchImpl:async(url)=>new URL(url).pathname.endsWith('/login/status')?ok({is_logged_in:true}):Response.json({success:false,error:'失败',details:'sensitive body'})});
  await assert.rejects(client.collect(profile),error=>error.code==='COMPONENT_UNAVAILABLE'&&!error.message.includes('sensitive'));
});

test('expired login in an upstream error is classified for re-scan',async()=>{
  const client=createXhsClient({fetchImpl:async(url)=>new URL(url).pathname.endsWith('/login/status')?ok({is_logged_in:true}):Response.json({error:'搜索失败',details:'请先登录小红书 token=secret'},{status:500})});
  await assert.rejects(client.collect(profile),error=>error.code==='LOGIN_REQUIRED'&&!error.message.includes('secret'));
});

test('empty search is checked again so an expired session does not look like zero content',async()=>{
  let checks=0;
  const client=createXhsClient({fetchImpl:async(url)=>{
    if(new URL(url).pathname.endsWith('/login/status'))return ok({is_logged_in:++checks===1});
    return ok({feeds:[]});
  }});
  await assert.rejects(client.collect(profile),error=>error.code==='LOGIN_REQUIRED');
});

test('service failure and malformed responses do not leak raw URLs or credentials',async()=>{
  for(const fetchImpl of [async()=>{throw Error('request token=secret failed at http://127.0.0.1:18060');},async()=>new Response('<html>cookies=secret</html>'),async()=>ok({})]){
    const client=createXhsClient({fetchImpl});
    await assert.rejects(client.checkLogin(),error=>error.code==='COMPONENT_UNAVAILABLE'&&!/secret|http:/.test(error.message));
  }
});

test('an aborted collection stays cancelled',async()=>{
  const control=new AbortController();control.abort();
  const client=createXhsClient({fetchImpl:async()=>{throw Error('must not call');}});
  await assert.rejects(client.collect(profile,{signal:control.signal}),error=>error.name==='AbortError');
});

test('malformed cards are ignored and impossible counters remain unknown',async()=>{
  const client=createXhsClient({fetchImpl:async(url)=>{
    const path=new URL(url).pathname;
    if(path.endsWith('/login/status'))return ok({is_logged_in:true});
    if(path.endsWith('/feeds/search'))return ok({feeds:[null,42,{id:'missing-card',modelType:'note'},card('one','9999999999999999999999999万')]});
    return Response.json({error:'unavailable'},{status:500});
  }});
  const result=await client.collect(profile);
  assert.equal(result.items.length,1);assert.equal(result.items[0].likes,null);
});
