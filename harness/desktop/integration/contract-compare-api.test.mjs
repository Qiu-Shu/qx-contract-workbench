import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm,readdir,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import * as feature from './attachment-preview.mjs';
test('HTTP and tool share session-scoped comparison; hostile origins and stale references fail',async t=>{
  assert.equal(typeof feature.installContractComparison,'function','comparison API is missing');
  const root=await mkdtemp(join(tmpdir(),'qx-compare-api-'));t.after(()=>rm(root,{recursive:true,force:true}));
  await writeFile(join(root,'a.txt'),'甲方支付100元');await writeFile(join(root,'b.txt'),'甲方支付200元');
  const routes=new Map(),registered=new Map(),header={id:'s',cwd:root};let authorized=0;
  let cwd=root;const ctx={workingDirectory:{get:()=>cwd},sessions:{get:id=>id==='s'?{header}:undefined},sessionQuery:{listSessions:async()=>[]},workspaceFiles:{stat:async()=>{authorized++},list:async()=>({path:'',entries:(await readdir(root)).map(name=>({name,type:'file'})),truncated:false})},connection:{fetch:{register:r=>routes.set(r.path,r)}},tools:{register:r=>registered.set(r.name,r)}};
  feature.installContractComparison(ctx);
  async function call(route,body,headers={}){return routes.get('/api/qx-compare/'+route).fetch(new Request('http://localhost/api/qx-compare/'+route,{method:'POST',headers:{'content-type':'application/json','x-qx-compare':'1',...headers},body:JSON.stringify(body)}));}
  assert.equal((await call('compare',{sessionId:'s',before:'a.txt',after:'b.txt'},{origin:'https://hostile.invalid'})).status,403);
  const response=await call('compare',{sessionId:'s',before:'a.txt',after:'b.txt'});assert.equal(response.status,200);const result=await response.json();assert.equal(result.equal,false);assert.equal(authorized,2);
  assert.equal((await call('locate',{sessionId:'s',reference:result.changes[0].before.reference})).status,200);
  assert.equal((await call('compare',{sessionId:'missing',before:'a.txt',after:'b.txt'})).status,404);
  const tool=registered.get('contract_compare');assert.ok(tool);const output=JSON.parse(await tool.execute({before:'a.txt',after:'b.txt'},{agent:{session:{id:'s'}}}));assert.equal(output.equal,false);
  cwd=join(root,'other');await mkdir(cwd);await writeFile(join(cwd,'a.txt'),'甲方支付100元');await writeFile(join(cwd,'b.txt'),'甲方支付300元');
  assert.equal((await call('locate',{sessionId:'s',reference:result.changes[0].before.reference})).status,409);
  const moved=await (await call('compare',{sessionId:'s',before:'a.txt',after:'b.txt'})).json();assert.equal(moved.changes[0].after.text,'甲方支付300元');
});
