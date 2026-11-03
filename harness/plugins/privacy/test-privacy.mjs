import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {apply} from './index.mjs';

const temp=await mkdtemp(join(tmpdir(),'qx-privacy-api-')),workspace=join(temp,'workspace');
await mkdir(workspace);
const routes=new Map(),cleanup=[];
apply({connection:{fetch:{register(route){routes.set(route.path,route.fetch);}}},effect(fn){cleanup.push(fn());}},{workspace,python:process.env.QX_TEST_PYTHON||'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe'});
const prepare=routes.get('/api/qx-privacy/prepare');
const request=(name,body,extra={})=>new Request('http://localhost/api/qx-privacy/prepare?name='+encodeURIComponent(name),{method:'POST',headers:{origin:'http://localhost','x-qx-privacy':'1',...extra},body});
try{
  assert.equal((await prepare(request('a.txt','secret',{origin:'https://attacker.test'}))).status,403);
  assert.equal((await prepare(request('a.zip','secret'))).status,400);
  const bridged=await prepare(new Request('http://dsh.internal/api/qx-privacy/prepare?name=carrier.txt',{method:'POST',headers:{host:'127.0.0.1:3080',origin:'http://127.0.0.1:3080','x-qx-privacy':'1'},body:'电话：13800138000'}));
  assert.equal(bridged.status,200,await bridged.clone().text());
  const response=await prepare(request('张三合同.txt','姓名：张三\n电话：13800138000\n邮箱：zhang@example.com\n应付10000元。',{'x-qx-terms':encodeURIComponent(JSON.stringify(['张三']))}));
  assert.equal(response.status,200,await response.clone().text());
  const body=await response.text();assert.ok(!body.includes('张三'));assert.ok(!body.includes('13800138000'));assert.ok(!body.includes('zhang@example.com'));assert.ok(body.includes('10000'));
  assert.ok(!decodeURIComponent(response.headers.get('x-qx-safe-name')).includes('张三'));
  assert.ok(Number(response.headers.get('x-qx-replacements'))>=3);
  assert.ok(!body.includes(temp));
  const empty=await prepare(request('empty.txt',''));assert.equal(empty.status,400);
  const script=await routes.get('/api/qx-privacy/client.js')();assert.match(await script.text(),/window.qxPrivacy/);
  console.log(JSON.stringify({passed:true,checks:['owner origin','unsupported format','real local text masking','no raw identifiers or vault path','amount retained','empty input fail closed','client route']}));
}finally{for(const fn of cleanup)fn?.();await rm(resolve(temp),{recursive:true,force:true});}
