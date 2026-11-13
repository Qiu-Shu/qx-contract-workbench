import test from 'node:test';
import assert from 'node:assert/strict';
import {createJustOneClient} from './justone.mjs';

const profile={practice:'劳动争议',targetClients:'中小企业'};
const now=Date.parse('2026-11-08T04:00:00Z');
const ok=data=>Response.json({code:0,message:'',data});
const secret='synthetic-private-token';
// Synthetic content, following official rendered examples read on 2026-11-08:
// https://docs.justoneapi.com/en/api/xiaohongshu-rednote/note-search-v4
// https://docs.justoneapi.com/en/api/xiaohongshu-rednote/note-details-v1
const card=(id,extra={})=>({id,title:'劳动争议怎么处理',type:'normal',user:{nickname:'示例作者'},liked_count:'12',...extra});
const detail=(id,extra={})=>[{model_type:'note',note_list:[{id,title:'劳动争议处理',desc:'这是合成的笔记正文。',type:'normal',time:Math.floor((now-3600000)/1000),...extra}]}];
const isSearch=url=>new URL(url).pathname.endsWith('/search-note/v4');

test('checking a stored token is local and does not claim provider verification',async()=>{
  let calls=0,token=secret;
  const client=createJustOneClient({token:async()=>token,fetchImpl:async()=>{calls++;throw Error('must not call');}});
  assert.deepEqual(await client.checkLogin(),{loggedIn:true,verified:false});
  token='';
  await assert.rejects(client.checkLogin(),error=>error.code==='TOKEN_REQUIRED');
  await assert.rejects(client.collect(profile),error=>error.code==='TOKEN_REQUIRED');
  assert.equal(calls,0);
});

test('token lookup errors are sanitized before leaving the adapter',async()=>{
  const client=createJustOneClient({token:async()=>{throw Error(secret);}});
  await assert.rejects(client.checkLogin(),error=>error.code==='TOKEN_REQUIRED'&&!error.message.includes(secret));
});

test('business failure codes stop immediately without retry or exposing provider data',async()=>{
  for(const [code,expected] of [[100,'TOKEN_INVALID'],[302,'RATE_LIMIT'],[303,'QUOTA_EXCEEDED'],[600,'API_PERMISSION'],[601,'BUDGET_EXCEEDED'],[602,'BUDGET_EXCEEDED'],[301,'PROVIDER_UNAVAILABLE'],[500,'PROVIDER_UNAVAILABLE'],[999,'PROVIDER_UNAVAILABLE']]){
    let calls=0;
    const client=createJustOneClient({token:secret,fetchImpl:async()=>{calls++;return Response.json({code,message:secret,reason:'https://provider.invalid/?token='+secret,data:{}});}});
    await assert.rejects(client.collect(profile),error=>error.code===expected&&!/synthetic-private|https:/.test(error.message)&&error.cause===undefined);
    assert.equal(calls,1);
  }
});

test('HTTP errors, missing numeric code, malformed data and transport failures are safe failures',async()=>{
  for(const fetchImpl of [
    async()=>{throw Error('https://api.justoneapi.com?token='+secret);},
    async()=>new Response('<html>'+secret+'</html>'),
    async()=>Response.json({success:true,data:{}}),
    async()=>Response.json({code:'0',data:{}}),
    async()=>ok({}),
    async()=>Response.json({code:0,data:{}},{status:500}),
    async()=>new Response(null,{status:302,headers:{location:'https://other.invalid/?token='+secret}}),
  ]){
    const client=createJustOneClient({token:secret,fetchImpl});
    await assert.rejects(client.collect(profile),error=>error.code==='PROVIDER_UNAVAILABLE'&&!/synthetic-private|https:/.test(error.message));
  }
});

test('caller cancellation before token lookup performs no work',async()=>{
  const control=new AbortController();control.abort(secret);let calls=0;
  const client=createJustOneClient({token:()=>{calls++;return secret;},fetchImpl:async()=>{calls++;return ok({});}});
  await assert.rejects(client.checkLogin({signal:control.signal}),error=>error.name==='AbortError'&&!error.message.includes(secret));
  await assert.rejects(client.collect(profile,{signal:control.signal}),error=>error.name==='AbortError');
  assert.equal(calls,0);
});

test('in-flight cancellation and timeout do not leak fetch errors or retry',async()=>{
  for(const cancel of [true,false]){
    const control=new AbortController();let calls=0;
    const client=createJustOneClient({token:secret,timeoutMs:15,fetchImpl:async(url,{signal})=>{
      calls++;
      if(cancel)setTimeout(()=>control.abort(secret),5);
      return await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(Error('timeout did not abort')),300);
        signal.addEventListener('abort',()=>{clearTimeout(timer);reject(Error(secret));},{once:true});
      });
    }});
    await assert.rejects(client.collect(profile,{signal:control.signal}),error=>(cancel?error.name==='AbortError':error.code==='PROVIDER_UNAVAILABLE')&&!error.message.includes(secret));
    assert.equal(calls,1);
  }
});

test('oversized streamed responses are cancelled and bounded',async()=>{
  let cancelled=false,pulls=0;
  const client=createJustOneClient({token:secret,fetchImpl:async()=>new Response(new ReadableStream({
    pull(controller){pulls++;controller.enqueue(new Uint8Array(1024*1024));},
    cancel(){cancelled=true;},
  }))});
  await assert.rejects(client.collect(profile),error=>error.code==='PROVIDER_UNAVAILABLE');
  assert.equal(cancelled,true);assert.ok(pulls<=6);
});

test('collection uses the fixed origin, read endpoints and bounded recent search filters',async()=>{
  const calls=[];
  const client=createJustOneClient({token:async()=>secret,clock:()=>now,fetchImpl:async(url,options)=>{
    calls.push({url:new URL(url),options});
    if(isSearch(url))return ok({api_info:{code:10200,session_id:secret},notes:[card('one',{images_list:[{url:'https://image.invalid/?signature='+secret}]}),card('one'),card('two',{type:'video'})]});
    const id=new URL(url).searchParams.get('noteId');
    return ok(detail(id,{type:id==='two'?'video':'normal',liked_count:'1.2万',comments_count:'0',collected_count:'2.5千',shared_count:'3'}));
  }});
  const result=await client.collect(profile);
  assert.equal(result.items.length,2);assert.equal(calls.length,6);
  const searches=calls.filter(call=>isSearch(call.url));
  assert.equal(searches.length,4);
  assert.deepEqual([...new Set(searches.map(call=>call.url.searchParams.get('sortType')))].sort(),['popularity_descending','time_descending']);
  assert.ok(searches.some(call=>call.url.searchParams.get('keyword').includes('中小企业')));
  for(const {url,options} of calls){
    assert.equal(url.origin,'https://api.justoneapi.com');assert.equal(options.method,'GET');assert.equal(options.redirect,'error');
    assert.equal(options.body,undefined);assert.equal(url.searchParams.get('token'),secret);
    if(isSearch(url)){assert.equal(url.searchParams.get('page'),'1');assert.equal(url.searchParams.get('timeFilter'),'ONE_WEEK');assert.equal(url.searchParams.get('noteType'),'ALL');assert.ok(url.searchParams.get('keyword').length<=80);}
    else assert.equal(url.pathname,'/api/xiaohongshu/get-note-detail/v1');
  }
  const item=result.items.find(item=>item.id==='one');
  assert.equal(item.likes,12000);assert.equal(item.comments,0);assert.equal(item.collected,2500);assert.equal(item.shares,3);
  assert.equal(item.publishedAt,'2026-11-08T03:00:00.000Z');assert.equal(item.textCoverage,'正文');
  assert.equal(item.url,'https://www.xiaohongshu.com/explore/one');assert.equal(result.items[1].textCoverage,'标题简介');
  assert.ok(!JSON.stringify(result).includes(secret));assert.ok(result.warnings.some(value=>value.includes('视频')));
});

test('seen and known old notes are skipped before detail, leaving room for new candidates',async()=>{
  const requested=[];
  const cards=[...Array.from({length:20},(_,i)=>card('seen'+i)),card('old',{timestamp:Math.floor((now-8*86400000)/1000),last_update_time:Math.floor(now/1000)}),card('new')];
  const client=createJustOneClient({token:secret,clock:()=>now,fetchImpl:async(url)=>{
    if(isSearch(url))return ok({notes:cards});
    const id=new URL(url).searchParams.get('noteId');requested.push(id);return ok(detail(id));
  }});
  const result=await client.collect(profile,{seenIds:cards.slice(0,20).map(item=>item.id)});
  assert.deepEqual(requested,['new']);assert.deepEqual(result.items.map(item=>item.id),['new']);
});

test('sampling reserves recent results and uses at most six detail requests',async()=>{
  let searches=0,details=0;
  const client=createJustOneClient({token:secret,clock:()=>now,fetchImpl:async(url)=>{
    if(isSearch(url)){
      searches++;const recent=new URL(url).searchParams.get('sortType')==='time_descending';
      return ok({notes:Array.from({length:40},(_,i)=>card((recent?'recent':'popular')+i,{timestamp:Math.floor((now-3600000)/1000),liked_count:recent?'1':'10000'}))});
    }
    details++;return ok(detail(new URL(url).searchParams.get('noteId')));
  }});
  const result=await client.collect({practice:'劳动争议、合同纠纷、婚姻、刑事',targetClients:'中小企业、创业者'});
  assert.equal(searches,4);assert.equal(details,6);assert.equal(result.items.length,20);
  assert.equal(result.items.filter(item=>item.id.startsWith('recent')).length,10);
});

test('a full practice-only page cannot crowd target-client searches out of the first six notes',async()=>{
  let searches=0;const requested=[];
  const client=createJustOneClient({token:secret,clock:()=>now,fetchImpl:async(url)=>{
    const params=new URL(url).searchParams;
    if(isSearch(url)){
      searches++;
      const group=params.get('keyword').includes('中小企业')?'target':'practice';
      const order=params.get('sortType')==='time_descending'?'recent':'popular';
      return ok({notes:Array.from({length:20},(_,i)=>card(`${group}-${order}-${i}`,{timestamp:Math.floor((now-3600000)/1000)}))});
    }
    const id=params.get('noteId');requested.push(id);return ok(detail(id));
  }});
  const result=await client.collect(profile),firstSix=result.items.slice(0,6);
  assert.equal(searches,4);assert.equal(requested.length,6);assert.equal(result.items.length,20);
  assert.deepEqual(new Set(firstSix.map(item=>item.id.split('-').slice(0,2).join('-'))),
    new Set(['practice-popular','practice-recent','target-popular','target-recent']));
  assert.deepEqual(requested,firstSix.map(item=>item.id));assert.equal(new Set(result.items.map(item=>item.id)).size,20);
  assert.ok(firstSix.some(item=>item.keywords.includes('劳动争议 中小企业')));
});

test('detail dates are checked again and unknown dates or counters stay explicitly missing',async()=>{
  const client=createJustOneClient({token:secret,clock:()=>now,fetchImpl:async(url)=>{
    if(isSearch(url))return ok({notes:[card('becameold'),card('unknown',{liked_count:'--'})]});
    const id=new URL(url).searchParams.get('noteId');
    return ok(detail(id,{time:id==='becameold'?Math.floor((now-8*86400000)/1000):'昨天',liked_count:'--',comments_count:'-1',collected_count:'99999999999999999999万'}));
  }});
  const {items,warnings}=await client.collect(profile);
  assert.deepEqual(items.map(item=>item.id),['unknown']);
  assert.equal(items[0].publishedAt,null);assert.equal(items[0].likes,null);assert.equal(items[0].comments,null);assert.equal(items[0].collected,null);assert.equal(items[0].shares,null);
  assert.ok(warnings.some(value=>value.includes('时间待核实')));
});

test('mismatched or missing detail is never attached to a different note',async()=>{
  const client=createJustOneClient({token:secret,clock:()=>now,fetchImpl:async(url)=>isSearch(url)?ok({notes:[card('one')]}):ok(detail('different'))});
  const result=await client.collect(profile);
  assert.equal(result.items[0].text,'劳动争议怎么处理');assert.equal(result.items[0].textCoverage,'标题简介');
  assert.ok(result.warnings.some(value=>value.includes('正文未能读取')));
});

test('malformed or non-note entries are skipped while an unknown search envelope fails',async()=>{
  const client=createJustOneClient({token:secret,clock:()=>now,fetchImpl:async(url)=>isSearch(url)?ok({notes:[null,42,{id:'live',type:'live'},card('https://invalid'),card('valid')]}):ok(detail('valid'))});
  const result=await client.collect(profile);assert.deepEqual(result.items.map(item=>item.id),['valid']);
  await assert.rejects(createJustOneClient({token:secret,fetchImpl:async()=>ok({items:[]})}).collect(profile),error=>error.code==='PROVIDER_UNAVAILABLE');
  await assert.rejects(createJustOneClient({token:secret,fetchImpl:async()=>ok({notes:[{note_id:'unexpected',title:'shape changed'}]})}).collect(profile),error=>error.code==='PROVIDER_UNAVAILABLE');
  const onlyLive=await createJustOneClient({token:secret,fetchImpl:async()=>ok({notes:[{id:'live',type:'live'}]})}).collect(profile);
  assert.deepEqual(onlyLive.items,[]);
});

test('quota or credential failures during detail stop all remaining paid calls',async()=>{
  for(const [code,expected] of [[100,'TOKEN_INVALID'],[302,'RATE_LIMIT'],[303,'QUOTA_EXCEEDED'],[601,'BUDGET_EXCEEDED']]){
    let calls=0;
    const client=createJustOneClient({token:secret,fetchImpl:async(url)=>{calls++;return isSearch(url)?ok({notes:[card('one'),card('two')]}):Response.json({code,message:secret});}});
    await assert.rejects(client.collect(profile),error=>error.code===expected);assert.equal(calls,5);
  }
});

test('search excerpts without a fetched detail are never presented as full text',async()=>{
  const client=createJustOneClient({token:secret,clock:()=>now,fetchImpl:async(url)=>{
    if(isSearch(url))return ok({notes:Array.from({length:8},(_,i)=>card('n'+i,{desc:'搜索中截取的简介',timestamp:Math.floor(now/1000)}))});
    return ok(detail(new URL(url).searchParams.get('noteId')));
  }});
  const {items}=await client.collect(profile);
  assert.equal(items.filter(item=>item.textCoverage==='正文').length,6);
  assert.equal(items[6].textCoverage,'标题简介');assert.equal(items[6].text,'搜索中截取的简介');
});

test('empty documented search responses do not trigger any detail or health probe',async()=>{
  let calls=0;
  const client=createJustOneClient({token:secret,fetchImpl:async(url)=>{calls++;assert.ok(isSearch(url));return ok({api_info:{code:10200},notes:[]});}});
  assert.deepEqual((await client.collect(profile)).items,[]);assert.equal(calls,4);
});
