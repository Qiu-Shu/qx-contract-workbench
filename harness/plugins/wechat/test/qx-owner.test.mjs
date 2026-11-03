import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {ownerAccepts, workspaceFile, publicLogin} from '../qx-owner.js';
test('only the scanned owner in a direct inbound message is accepted',()=>{
  const account={userId:'own@im.wechat'};
  assert.equal(ownerAccepts(account,{from_user_id:account.userId,message_type:1}),true);
  for(const message of [
    {from_user_id:'other',message_type:1},
    {from_user_id:account.userId,message_type:2},
    {from_user_id:account.userId,group_id:'group'},
    {from_user_id:account.userId,session_id:'x@chatroom'},
  ]) assert.equal(ownerAccepts(account,message),false);
  assert.equal(ownerAccepts({}, {from_user_id:'first-stranger'}),false);
});
test('outgoing files must really live in the configured workspace',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'qx-wechat-test-'));
  const workspace=join(dir,'workspace');await mkdir(workspace);
  await writeFile(join(workspace,'out.docx'),'synthetic');await writeFile(join(dir,'secret'),'synthetic');
  assert.equal(await workspaceFile(workspace,join(workspace,'out.docx')),await realpath(join(workspace,'out.docx')));
  await assert.rejects(workspaceFile(workspace,join(workspace,'..','secret')),/工作区/);
});
test('login status does not expose token or verification digits',()=>{
  const status=publicLogin({id:'id',status:'wait',token:'secret',verifyCode:'123',qrPayload:'https://example.test',userId:'own'});
  assert.equal(JSON.stringify(status).includes('secret'),false);
  assert.equal(JSON.stringify(status).includes('123'),false);
});
