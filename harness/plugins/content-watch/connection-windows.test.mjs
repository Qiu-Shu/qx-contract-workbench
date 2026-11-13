import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createConnectionStore} from './connection.mjs';

test('Windows system credentials round-trip Unicode and quotes without plaintext or corrupt-record replacement',
  {skip:process.platform!=='win32',timeout:45000},async t=>{
    const stateDir=await mkdtemp(join(tmpdir(),'qx-content-dpapi-'));
    t.after(()=>rm(stateDir,{recursive:true,force:true}));
    const token='synthetic-中文-"quote"-\'single\'-$literal';
    const store=await createConnectionStore({stateDir});
    await store.save({provider:'justone',token});
    const file=join(stateDir,'connection.json'),saved=await readFile(file,'utf8');
    assert.equal(store.status().secretStorage,'dpapi');
    assert.ok(!saved.includes(token));
    assert.ok(!saved.includes('synthetic-'));
    assert.ok(!saved.includes('中文'));
    assert.ok(JSON.parse(saved).token.startsWith('dpapi:'));
    const reopened=await createConnectionStore({stateDir});
    assert.equal(reopened.token(),token);
    assert.ok(!JSON.stringify(reopened.status()).includes(token));
    const damaged=JSON.stringify({provider:'justone',token:'dpapi:invalid-synthetic-ciphertext'});
    await writeFile(file,damaged);
    await assert.rejects(createConnectionStore({stateDir}),error=>{
      assert.match(error.message,/连接设置无法读取/);
      assert.ok(!error.message.includes('synthetic'));
      assert.ok(!error.message.includes(token));
      return true;
    });
    assert.equal(await readFile(file,'utf8'),damaged);
  });
