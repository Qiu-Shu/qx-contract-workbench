import test from 'node:test';
import assert from 'node:assert/strict';
import {createTransport, documentRef, boundedFetch} from '../api.js';

const json=value=>new Response(JSON.stringify(value),{headers:{'content-type':'application/json'}});
test('document URLs reject foreign hosts, credentials, traversal and unsupported resources',()=>{
  for(const url of ['https://evil.test/docx/abc','https://feishu.cn.evil.test/docx/abc','http://x.feishu.cn/docx/abc','https://u:p@x.feishu.cn/docx/abc','https://x.feishu.cn:444/docx/abc','https://x.feishu.cn/sheets/abc','https://x.feishu.cn/docx/a%2fb','https://x.feishu.cn/docx/abc/extra'])assert.throws(()=>documentRef(url));
  assert.deepEqual(documentRef('https://synthetic.feishu.cn/docx/Doc123?from=test#x'),{kind:'docx',id:'Doc123',url:'https://synthetic.feishu.cn/docx/Doc123'});
  assert.equal(documentRef('https://synthetic.feishu.cn/docs/Old123').kind,'doc');
});
test('bounded official fetch blocks redirects, oversized streamed bodies and credential leak errors',async()=>{
  let options;
  const request=boundedFetch(async(_url,init)=>{options=init;return new Response(null,{status:302,headers:{location:'https://evil.test'}});});
  await assert.rejects(()=>request('https://open.feishu.cn/open-apis/im/v1/messages'),/重定向/);
  assert.equal(options.redirect,'error');
  await assert.rejects(()=>request('https://evil.test/open-apis/test'),/官方/);
  const large=boundedFetch(async()=>new Response(new ReadableStream({start(c){c.enqueue(new Uint8Array(9));c.enqueue(new Uint8Array(9));c.close();}})),{maxBytes:16});
  await assert.rejects(()=>large('https://open.feishu.cn/open-apis/im/v1/messages'),/大小/);
  const failing=boundedFetch(async()=>{throw Error('secret=synthetic-sensitive');});
  await assert.rejects(()=>failing('https://open.feishu.cn/open-apis/im/v1/messages'),e=>!e.message.includes('synthetic-sensitive'));
});
test('docx, wiki and legacy doc read use only fixed official APIs and pagination retains a source',async()=>{
  const urls=[];
  const transport=createTransport({appId:'cli_synthetic',appSecret:'synthetic-secret',fetchImpl:async(url)=>{
    urls.push(url);
    if(url.includes('/auth/'))return json({code:0,tenant_access_token:'synthetic-token',expire:7200});
    if(url.includes('/wiki/'))return json({code:0,data:{node:{obj_token:'Resolved123',obj_type:'docx'}}});
    return json({code:0,data:{content:'虚构合同正文'}});
  }});
  assert.equal((await transport.readDocument('https://synthetic.feishu.cn/docx/Doc123')).content,'虚构合同正文');
  await transport.readDocument('https://synthetic.feishu.cn/wiki/Wiki123');
  await transport.readDocument('https://synthetic.feishu.cn/docs/Old123');
  assert.ok(urls.includes('https://open.feishu.cn/open-apis/docx/v1/documents/Resolved123/raw_content'));
  assert.ok(urls.includes('https://open.feishu.cn/open-apis/doc/v2/Old123/raw_content'));
  assert.ok(urls.every(url=>new URL(url).hostname==='open.feishu.cn'));
});
test('wiki unsupported type and API permission errors fail without interpreting provider text',async()=>{
  const transport=createTransport({appId:'cli_synthetic',appSecret:'synthetic-secret',fetchImpl:async(url)=>url.includes('/auth/')?json({code:0,tenant_access_token:'synthetic-token'}):json({code:0,data:{node:{obj_token:'Sheet123',obj_type:'sheet'}}})});
  await assert.rejects(()=>transport.readDocument('https://synthetic.feishu.cn/wiki/Wiki123'),/不支持/);
  const blocked=createTransport({appId:'cli_synthetic',appSecret:'synthetic-secret',fetchImpl:async()=>json({code:99991664,msg:'echo synthetic-secret'})});
  await assert.rejects(()=>blocked.readDocument('https://synthetic.feishu.cn/docx/Doc123'),e=>e.message.includes('权限')&&!e.message.includes('synthetic-secret'));
});
