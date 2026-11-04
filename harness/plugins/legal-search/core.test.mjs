import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createSearchService,canonicalUrl} from './core.mjs';
const source=(url='https://www.court.gov.cn/fabu/1.html',summary='摘要')=>({url,title:'最高人民法院公开资料',summary});
async function fixture(t,primary,fallback,options={}){
 const workspace=await mkdtemp(join(tmpdir(),'qx-search-'));t.after(()=>rm(workspace,{recursive:true,force:true}));
 return createSearchService({workspace,primary,fallback,fallbackIntervalMs:0,...options});
}
test('primary success avoids fallback, archive survives a fresh reader and pages full text',async t=>{
 const service=await fixture(t,async()=>({sources:[source(undefined,'全'.repeat(20000))],content:'完整响应',truncated:false}),()=>{throw Error('unexpected fallback');});
 const report=await service.search(['法律查询']);assert.equal(report.total,1);assert.equal(report.queries[0].provider,'deepseek');
 assert.ok(JSON.stringify(report).length<3000);
 const raw=JSON.parse(await readFile(report.path,'utf8'));assert.equal(raw.queries[0].attempts[0].raw.content,'完整响应');assert.equal(raw.sources[0].summary.length,20000);
 const detail=await service.read({recordId:report.recordId,entry:0});assert.equal(detail.text.length,12000);assert.equal(detail.nextStart,12000);
 const tail=await service.read({recordId:report.recordId,entry:0,start:detail.nextStart});assert.ok(tail.text.endsWith('全'));assert.equal(tail.nextStart,null);
});
test('failed primary falls back; an unsuccessful later query preserves earlier results',async t=>{
 const service=await fixture(t,async()=>{throw Object.assign(Error('do not expose token secret'),{code:'WEB_PROVIDER_ERROR'});},async q=>{if(q==='二')throw Object.assign(Error('blocked'),{code:'CAPTCHA'});return {sources:[source()],truncated:false};});
 const report=await service.search(['一','二']);assert.equal(report.total,1);assert.equal(report.queries[0].provider,'so360');assert.equal(report.queries[1].status,'failed');assert.equal(report.queries[1].attempts[1].code,'CAPTCHA');
 assert.ok(!JSON.stringify(report).includes('secret'));const raw=JSON.parse(await readFile(report.path,'utf8'));assert.equal(raw.status,'partial');assert.equal(raw.sources.length,1);
});
test('empty primary falls back; both empty explicitly report no results',async t=>{
 let count=0;const service=await fixture(t,async()=>({sources:[]}),async()=>{count++;return {sources:[]};});
 const report=await service.search(['一']);assert.equal(count,1);assert.equal(report.queries[0].status,'empty');assert.equal(report.status,'empty');
});
test('fallback keeps the empty primary response and excludes all full responses from the model directory',async t=>{
 const content='原始内容'.repeat(3000);
 const service=await fixture(t,async()=>({sources:[],content}),async()=>({sources:[source()]}));
 const report=await service.search(['一']);assert.ok(JSON.stringify(report).length<3000);
 const raw=JSON.parse(await readFile(report.path,'utf8'));assert.equal(raw.queries[0].attempts[0].raw.content,content);assert.equal(raw.queries[0].attempts[1].raw.sources.length,1);
});
test('dedup combines query provenance, preserves usable link and longest content, ranks official sources',async t=>{
 const service=await fixture(t,async({query})=>({sources:[source('https://example.org/article','论坛'),source(query==='一'?'https://www.court.gov.cn/fabu/1.html?utm_source=a':'https://court.gov.cn/fabu/1.html','法'.repeat(query==='一'?10:30))]}),async()=>({sources:[]}));
 const report=await service.search(['一','二']);assert.equal(report.total,2);assert.equal(report.items[0].sourceType,'政府或司法机关网站');assert.ok(report.items[0].url.startsWith('https://www.'));
 const raw=JSON.parse(await readFile(report.path,'utf8'));assert.deepEqual(raw.sources[0].queries,['一','二']);assert.equal(raw.sources[0].summary.length,30);
 assert.equal(canonicalUrl('https://www.Example.com/a/?utm_source=x#part'),'https://example.com/a');assert.equal(canonicalUrl('javascript:alert(1)'),null);
});
test('cancel keeps completed data and does not request fallback',async t=>{
 const controller=new AbortController();let count=0;
 const service=await fixture(t,async({query})=>{if(query==='二'){controller.abort();controller.signal.throwIfAborted();}return {sources:[source()]};},()=>{count++;});
 const report=await service.search(['一','二'],controller.signal);assert.equal(report.status,'cancelled');assert.equal(report.total,1);assert.equal(count,0);assert.equal(JSON.parse(await readFile(report.path,'utf8')).status,'cancelled');
});
test('uncooperative primary deadline triggers fallback; captcha cooldown avoids repeated requests',async t=>{
 let count=0;const service=await fixture(t,()=>new Promise(()=>{}),async()=>{count++;throw Object.assign(Error('captcha'),{code:'CAPTCHA'});},{primaryTimeoutMs:15});
 const report=await service.search(['一','二']);assert.equal(count,1);assert.equal(report.queries[0].attempts[0].code,'TIMEOUT');assert.equal(report.queries[1].attempts[1].code,'COOLDOWN');
});
test('record identifiers cannot traverse paths and paging is stable',async t=>{
 const service=await fixture(t,async()=>({sources:Array.from({length:13},(_,i)=>source('https://court.gov.cn/'+i))}),()=>{});
 const report=await service.search(['一']);assert.equal(report.items.length,8);assert.equal(report.nextOffset,8);
 const second=await service.read({recordId:report.recordId,offset:8});assert.equal(second.items.length,5);assert.equal(second.items[0].index,8);assert.equal(second.nextOffset,null);
 await assert.rejects(service.read({recordId:'../../secret'}),/编号/);
});
test('a failed primary and empty fallback do not hide the unavailable channel',async t=>{
 const service=await fixture(t,async()=>{throw Error('offline');},async()=>({sources:[]}));
 const report=await service.search(['一']);assert.equal(report.status,'failed');assert.equal(report.queries[0].status,'failed');
});
test('cancelling a queued fallback saves immediately without waiting for another search',async t=>{
 let release,entered;const gate=new Promise(r=>release=r),ready=new Promise(r=>entered=r);let requests=0;
 const service=await fixture(t,async()=>({sources:[]}),async()=>{requests++;entered();await gate;return {sources:[source()]};});
 const first=service.search(['一']);await ready;
 const controller=new AbortController(),second=service.search(['二'],controller.signal);
 await new Promise(r=>setTimeout(r,25));controller.abort();
 try{const report=await Promise.race([second,new Promise((_,reject)=>setTimeout(()=>reject(Error('cancel waited for queue')),150))]);assert.equal(report.status,'cancelled');assert.equal(JSON.parse(await readFile(report.path,'utf8')).status,'cancelled');}
 finally{release();await first;await second;}
 assert.equal(requests,1);
});
