import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createServer} from 'node:http';

const python=process.env.QX_TEST_PYTHON;
const uuid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
async function fixture(t){
  const {apply}=await import('./index.mjs');
  const workspace=await mkdtemp(join(tmpdir(),'qx-memory-routes-'));
  const routes=new Map(),disposers=[];
  apply({connection:{fetch:{register:r=>routes.set(r.path,r)}},effect:f=>disposers.push(f())},{workspace,python:python||'missing-test-python'});
  t.after(async()=>{for(const dispose of disposers)dispose();await rm(workspace,{recursive:true,force:true,maxRetries:8,retryDelay:150});});
  const request=async(path,options={})=>{
    const method=options.method||'GET';
    const req=new Request('http://dsh.internal/api/qx-case-memory/'+path,{...options,headers:{host:'127.0.0.1:3080',
      ...(method==='POST'?{origin:'http://127.0.0.1:3080','x-qx-case-memory':'1','content-type':'application/json'}:{}),...options.headers}});
    const route=routes.get(new URL(req.url).pathname);
    assert.ok(route);assert.ok(route.methods.includes(method));
    return route.fetch(req);
  };
  return {workspace,request};
}

test('memory mutation guard uses original Host and rejects cross-origin/missing marker before workers',async t=>{
  const {request}=await fixture(t);
  for(const headers of [{'x-qx-case-memory':''},{origin:'https://attacker.invalid'},{origin:'http://dsh.internal'},
    {origin:'http://127.0.0.1:3081'},{host:'attacker.invalid',origin:'http://127.0.0.1:3080'}]){
    const response=await request('settings',{method:'POST',headers,body:'{"enabled":true}'});
    assert.equal(response.status,403);assert.equal(response.headers.get('cache-control'),'no-store');
  }
});

test('bounded strict memory inputs reject malformed identities, unknown fields and coercions',async t=>{
  const {request}=await fixture(t);
  for(const [path,body] of [['add',{case_id:'../private',content:'x',source:'manual',confirmed:true}],
    ['settings',{enabled:'true'}],['settings',{enabled:true,url:'https://attacker.invalid'}],
    ['add',{case_id:uuid,content:'x'.repeat(16001),source:'manual',confirmed:true}],
    ['add',{case_id:uuid,content:'x',source:'manual',confirmed:false}],
    ['add',{case_id:uuid,note_id:uuid,content:'override'}],
    ['delete',{case_id:uuid,memory_id:uuid,revision:1.5}],
    ['update',{case_id:uuid,memory_id:uuid,revision:0,content:'x'}]]){
    const response=await request(path,{method:'POST',body:JSON.stringify(body)});
    assert.equal(response.status,400,JSON.stringify(body));
  }
  assert.equal((await request('add',{method:'POST',body:'x'.repeat(70000)})).status,413);
  assert.equal((await request('settings',{method:'POST',headers:{'content-type':'text/plain'},body:'{}'})).status,415);
  for(const path of ['list?case_id=bad','list?case_id='+uuid+'&offset=-1','list?case_id='+uuid+'&limit=51',
    'status?token=secret','recall?case_id='+uuid+'&query=x&use_hindsight=true'])assert.equal((await request(path)).status,400,path);
});

test('isolated real Python roundtrip preserves sources, revisions and case isolation', {skip:!python},async t=>{
  const previous=process.env.QX_HINDSIGHT_URL;delete process.env.QX_HINDSIGHT_URL;
  t.after(()=>{if(previous===undefined)delete process.env.QX_HINDSIGHT_URL;else process.env.QX_HINDSIGHT_URL=previous;});
  const {workspace,request}=await fixture(t);
  const code=`import sys,json;sys.path.insert(0,'bridge');from business_store import CaseStore;s=CaseStore(sys.argv[1]);a=s.create('合成甲案');b=s.create('合成乙案');n=s.add_note(a['id'],'fact','合成来源原文','用户提供');print(json.dumps({'a':a['id'],'b':b['id'],'note':n['id']}))`;
  const {stdout}=await promisify(execFile)(python,['-c',code,workspace],{cwd:new URL('../../',import.meta.url),windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8'}});
  const ids=JSON.parse(stdout);
  const get=async path=>{const response=await request(path);const data=await response.json();assert.ok(response.ok,JSON.stringify(data));return data;};
  const post=async(path,args)=>{const response=await request(path,{method:'POST',body:JSON.stringify(args)});const data=await response.json();assert.ok(response.ok,JSON.stringify(data));return data;};
  const initial=await get('status?case_id='+ids.a);assert.equal(initial.enabled,true);
  assert.equal(initial.service_configured,false,'fixture must never use a real memory service');
  assert.equal((await get('list_cases')).cases.length,2);
  assert.equal((await get('sources?case_id='+ids.a)).notes[0].id,ids.note);
  assert.equal((await request('add',{method:'POST',body:JSON.stringify({case_id:ids.b,note_id:ids.note})})).status,400);
  const added=await post('add',{case_id:ids.a,note_id:ids.note});
  assert.equal(added.memory.source.snapshot,'合成来源原文');
  assert.equal((await get('list?case_id='+ids.b)).total,0);
  const corrected=await post('update',{case_id:ids.a,memory_id:added.memory.id,revision:added.memory.revision,content:'修订记忆正文'});
  assert.equal(corrected.memory.source.snapshot,'合成来源原文');
  const stale=await request('update',{method:'POST',body:JSON.stringify({case_id:ids.a,memory_id:added.memory.id,revision:added.memory.revision,content:'过时覆盖'})});
  assert.equal(stale.status,409);
  const found=await get('recall?case_id='+ids.a+'&query='+encodeURIComponent('修订'));
  assert.equal(found.matches.length,1);
  const read=await get('read?case_id='+ids.a+'&memory_id='+added.memory.id);assert.ok(read.memory||read.id);
  await post('delete',{case_id:ids.a,memory_id:added.memory.id,revision:corrected.memory.revision});
  assert.equal((await get('list?case_id='+ids.a)).total,0);
  assert.equal((await get('sources?case_id='+ids.a)).notes[0].content,'合成来源原文');
  await post('settings',{case_id:ids.a,enabled:false});assert.equal((await get('status?case_id='+ids.a)).enabled,false);
  assert.equal((await get('status?case_id='+ids.b)).enabled,true);
  const manual=await post('add',{case_id:ids.b,content:'已核实的手工记忆',source:'2026-11-04 电话确认',confirmed:true});
  assert.equal(manual.memory.source.label,'2026-11-04 电话确认');
});

test('runtime proxy prepares only explicitly and never exposes control credentials',async t=>{
  const requests=[];
  const server=createServer((req,res)=>{requests.push({method:req.method,path:req.url,authorization:req.headers.authorization});res.setHeader('content-type','application/json');res.end(JSON.stringify({phase:req.method==='POST'?'installing':'not-installed',engine:'hindsight',version:'1.2.0',token:'private-token',url:'http://secret.invalid',message:'secret-token in stderr'}));});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const previous={url:process.env.QX_CASE_MEMORY_CONTROL_URL,token:process.env.QX_CASE_MEMORY_CONTROL_TOKEN};
  process.env.QX_CASE_MEMORY_CONTROL_URL=`http://127.0.0.1:${server.address().port}`;process.env.QX_CASE_MEMORY_CONTROL_TOKEN='test-control-secret';
  t.after(()=>{for(const [name,value] of [['QX_CASE_MEMORY_CONTROL_URL',previous.url],['QX_CASE_MEMORY_CONTROL_TOKEN',previous.token]]){if(value===undefined)delete process.env[name];else process.env[name]=value;}});
  const {request}=await fixture(t);
  const response=await request('runtime-status');const state=await response.json();assert.equal(state.phase,'not-installed');
  assert.deepEqual(requests.map(r=>r.method),['GET']);assert.equal(requests[0].authorization,'Bearer test-control-secret');
  assert.ok(!JSON.stringify(state).includes('secret'));assert.ok(!('url' in state));assert.ok(!('token' in state));
  const prepared=await request('prepare',{method:'POST',body:'{}'});assert.equal(prepared.status,202);
  assert.equal((await prepared.json()).phase,'installing');assert.equal(requests[1].path,'/prepare');
});
