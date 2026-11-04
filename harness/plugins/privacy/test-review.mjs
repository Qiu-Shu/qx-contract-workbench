import assert from 'node:assert/strict';
import {mkdtemp,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {apply} from './index.mjs';
const root=await mkdtemp(join(tmpdir(),'qx-review-')),workspace=join(root,'workspace');
await mkdir(workspace);
const routes=new Map(),cleanup=[];
apply({connection:{fetch:{register:r=>routes.set(r.path,r.fetch)}},effect:fn=>cleanup.push(fn())},
  {workspace,python:process.env.QX_TEST_PYTHON||'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe'});
const req=(url,body,headers={})=>new Request('http://localhost'+url,{method:'POST',headers:{origin:'http://localhost','x-qx-privacy':'1',...headers},body});
try{
  assert.equal((await routes.get('/api/qx-privacy/prepare')(req('/api/qx-privacy/prepare?name=old.txt','姓名：李明'))).status,409);
  const response=await routes.get('/api/qx-privacy/prepare')(req('/api/qx-privacy/prepare?name=private.txt&review=1','姓名：李明。金额8000元。'));
  assert.match(response.headers.get('content-type'),/application\/json/);
  const preview=await response.json();
  assert.ok(preview.original_text.includes('李明'));
  assert.ok(!preview.safe_text.includes('李明'));
  assert.ok(!JSON.stringify(preview).includes(root));
  assert.ok(preview.review_token&&preview.document_id);
  const confirm=routes.get('/api/qx-privacy/confirm');
  const payload={document_id:preview.document_id,review_token:preview.review_token,text:preview.safe_text+'\n修改后的附件',manual_replacements:[]};
  assert.equal((await confirm(req('/api/qx-privacy/confirm',JSON.stringify(payload),{origin:'https://evil.test'}))).status,403);
  assert.equal((await confirm(req('/api/qx-privacy/confirm',JSON.stringify({...payload,review_token:'wrong'})))).status,400);
  assert.equal((await confirm(req('/api/qx-privacy/confirm',JSON.stringify({...payload,document_id:'../other'})))).status,400);
  const done=await confirm(req('/api/qx-privacy/confirm',JSON.stringify(payload)));
  assert.equal(done.status,200,await done.clone().text());
  assert.equal(await done.text(),payload.text);
  assert.ok(done.headers.get('x-qx-reviewed'));
  assert.match(await (await routes.get('/api/qx-privacy/review.js')()).text(),/qxPrivacyReview/);
  console.log('Passed: private preview, exact reviewed bytes, origin/token/path rejection, review UI route');
}finally{for(const fn of cleanup)fn?.();await rm(root,{recursive:true,force:true});}
