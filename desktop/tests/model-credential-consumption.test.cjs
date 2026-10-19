const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {createModelCredentialStore} = require('../model-credentials.cjs');
const secret = 'SYNTHETIC_PRIVATE_CONSUMPTION_NOT_A_REAL_KEY_12345';

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'qx-model-consume-'));
  const key = crypto.randomBytes(32);
  const safeStorage = {
    async isAsyncEncryptionAvailable() { return true; },
    async encryptStringAsync(value) {
      const iv = crypto.randomBytes(12), cipher = crypto.createCipheriv('aes-256-gcm',key,iv);
      const ciphertext = Buffer.concat([cipher.update(value,'utf8'),cipher.final()]);
      return Buffer.concat([iv,cipher.getAuthTag(),ciphertext]);
    },
    async decryptStringAsync(bytes) {
      const decipher = crypto.createDecipheriv('aes-256-gcm',key,bytes.subarray(0,12));
      decipher.setAuthTag(bytes.subarray(12,28));
      return {result:Buffer.concat([decipher.update(bytes.subarray(28)),decipher.final()]).toString('utf8'),
        shouldReEncrypt:false};
    }
  };
  t.after(() => {
    assert.equal(path.dirname(root),path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith('qx-model-consume-'));
    fs.rmSync(root,{recursive:true,force:true});
  });
  return {root,safeStorage,file:path.join(root,'model-credentials','deepseek.bin'),
    store:createModelCredentialStore({dataParent:root,safeStorage,platform:'win32'})};
}

test('trusted secret consumer receives plaintext once but its returned value is never exposed', async t => {
  const f = fixture(t);
  assert.deepEqual(await f.store.save(secret),{status:'saved'});
  let calls = 0;
  assert.deepEqual(await f.store.withSecret(async value => {
    calls++;
    assert.equal(value,secret);
    return {secret:value};
  }),{status:'saved'});
  assert.equal(calls,1);
  assert.equal(fs.readFileSync(f.file).includes(Buffer.from(secret)),false);
});

test('missing credentials and invalid consumers never invoke a callback', async t => {
  const f=fixture(t);
  let called=false;
  assert.deepEqual(await f.store.withSecret(() => { called=true; }),{status:'empty'});
  await f.store.save(secret);
  for (const callback of [undefined,null,'read',{},42]) {
    assert.deepEqual(await f.store.withSecret(callback),{status:'invalid',code:'CREDENTIAL_INPUT_INVALID'});
  }
  assert.equal(called,false);
  assert.deepEqual(await f.store.status(),{status:'saved'});
});

test('unavailable protection, corrupt bytes and rotation requirements block trusted consumption', async t => {
  const f=fixture(t);
  await f.store.save(secret);
  const decrypt=f.safeStorage.decryptStringAsync;
  let called=false;
  const consume=() => { called=true; };
  f.safeStorage.isAsyncEncryptionAvailable=async () => false;
  assert.deepEqual(await f.store.withSecret(consume),{status:'unavailable',code:'CREDENTIAL_STORAGE_UNAVAILABLE'});
  f.safeStorage.isAsyncEncryptionAvailable=async () => true;
  f.safeStorage.decryptStringAsync=async bytes => ({...await decrypt(bytes),shouldReEncrypt:true});
  const before=fs.readFileSync(f.file);
  assert.deepEqual(await f.store.withSecret(consume),{status:'unavailable',code:'CREDENTIAL_ROTATION_REQUIRED'});
  assert.deepEqual(fs.readFileSync(f.file),before);
  f.safeStorage.decryptStringAsync=async () => { throw new Error(secret); };
  assert.deepEqual(await f.store.withSecret(consume),{status:'invalid',code:'CREDENTIAL_CORRUPT'});
  assert.equal(called,false);
});

test('a changed path during decrypt prevents the callback from receiving stale plaintext', async t => {
  const f=fixture(t);
  await f.store.save(secret);
  const decrypt=f.safeStorage.decryptStringAsync;
  f.safeStorage.decryptStringAsync=async bytes => {
    const result=await decrypt(bytes);
    fs.unlinkSync(f.file);
    return result;
  };
  let called=false;
  assert.deepEqual(await f.store.withSecret(() => { called=true; }),
    {status:'invalid',code:'CREDENTIAL_PATH_UNSAFE'});
  assert.equal(called,false);
});

test('linked credentials are not decrypted or handed to a trusted callback', async t => {
  const f=fixture(t);
  await f.store.save(secret);
  fs.linkSync(f.file,path.join(f.root,'other.bin'));
  let calls=0;
  f.safeStorage.decryptStringAsync=async () => { calls++; return {result:secret,shouldReEncrypt:false}; };
  assert.deepEqual(await f.store.withSecret(() => { calls++; }),
    {status:'invalid',code:'CREDENTIAL_PATH_UNSAFE'});
  assert.equal(calls,0);
});

test('trusted consumption occupies the existing serial queue and drain until its callback settles', async t => {
  const f=fixture(t);
  await f.store.save(secret);
  let release,enter;
  const entered=new Promise(resolve => { enter=resolve; });
  const gate=new Promise(resolve => { release=resolve; });
  t.after(() => release());
  const consuming=f.store.withSecret(async value => { assert.equal(value,secret); enter(); await gate; return value; });
  const removing=f.store.remove();
  let drained=false;
  const drain=f.store.drain().then(() => { drained=true; });
  await entered;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(drained,false);
  assert.equal(fs.existsSync(f.file),true);
  release();
  assert.deepEqual(await consuming,{status:'saved'});
  assert.deepEqual(await removing,{status:'empty'});
  await drain;
  assert.equal(drained,true);
});

test('consumer exceptions never expose plaintext and do not poison later store operations', async t => {
  const f=fixture(t);
  await f.store.save(secret);
  assert.deepEqual(await f.store.withSecret(async () => { throw new Error(secret+f.file); }),
    {status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'});
  assert.deepEqual(await f.store.status(),{status:'saved'});
  assert.deepEqual(await f.store.withSecret(value => value),{status:'saved'});
  assert.deepEqual(await f.store.remove(),{status:'empty'});
});
