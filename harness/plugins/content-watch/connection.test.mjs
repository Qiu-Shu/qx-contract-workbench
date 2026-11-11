import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createConnectionStore} from './connection.mjs';

async function fixture(t,protector={available:false}){
  const stateDir=await mkdtemp(join(tmpdir(),'qx-content-connection-'));
  t.after(()=>rm(stateDir,{recursive:true,force:true}));
  return {stateDir,store:await createConnectionStore({stateDir,protector}),protector};
}
test('starts with API disabled by missing credential; public view never returns token',async t=>{
  const {store,stateDir}=await fixture(t);
  assert.deepEqual(store.status(),{provider:'justone',tokenConfigured:false,secretStorage:'none'});
  await store.save({provider:'justone',token:' synthetic-token '});
  assert.equal(store.token(),'synthetic-token');assert.equal(store.status().secretStorage,'restricted-file');
  assert.ok(!JSON.stringify(store.status()).includes('synthetic-token'));
  await store.save({provider:'local-xhs'});await store.save({provider:'justone',token:''});
  assert.equal(store.token(),'synthetic-token');
  const reopened=await createConnectionStore({stateDir,protector:{available:false}});
  assert.equal(reopened.token(),'synthetic-token');
  await reopened.save({provider:'justone',clearToken:true});assert.equal(reopened.token(),'');
});
test('reuses Windows secret protector and fails without overwriting when protection fails',async t=>{
  const protector={available:true,protect:async v=>Buffer.from(v).toString('base64'),reveal:async v=>Buffer.from(v,'base64').toString()};
  const {store,stateDir}=await fixture(t,protector);
  await store.save({provider:'justone',token:'secret-synthetic'});
  const file=join(stateDir,'connection.json'),before=await readFile(file,'utf8');
  assert.ok(!before.includes('secret-synthetic'));assert.equal(store.status().secretStorage,'dpapi');
  const reopened=await createConnectionStore({stateDir,protector});assert.equal(reopened.token(),'secret-synthetic');
  protector.protect=async()=>{throw Error('contains secret');};
  await assert.rejects(store.save({provider:'justone',token:'replacement'}),/无法保存/);
  assert.equal(await readFile(file,'utf8'),before);assert.equal(store.token(),'secret-synthetic');
});
test('validates provider and preserves unreadable records for recovery',async t=>{
  const {store,stateDir}=await fixture(t);
  await assert.rejects(store.save({provider:'unknown',token:'synthetic'}),/采集方式/);
  await assert.rejects(store.save({provider:'justone',token:'x\nsecret'}),/Token/);
  const file=join(stateDir,'connection.json');await writeFile(file,'broken');
  await assert.rejects(createConnectionStore({stateDir}),/连接设置/);
  assert.equal(await readFile(file,'utf8'),'broken');
});
