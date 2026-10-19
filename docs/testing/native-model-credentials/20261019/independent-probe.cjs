const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {createModelCredentialStore}=require('../../desktop/model-credentials.cjs');
const area=path.resolve(__dirname);
const root=path.join(area,'independent-fixture-'+crypto.randomUUID());
fs.mkdirSync(root);
const secret='synthetic-independent-review-20261019';
const checks=[];
function fixture(name){
  const dataParent=path.join(root,name),directory=path.join(dataParent,'model-credentials'),file=path.join(directory,'deepseek.bin');
  let available=true;
  const safeStorage={isAsyncEncryptionAvailable:async()=>available,
    encryptStringAsync:async()=>Buffer.from('synthetic opaque ciphertext'),
    decryptStringAsync:async()=>({result:secret,shouldReEncrypt:false})};
  return {dataParent,directory,file,safeStorage,setAvailable:value=>available=value,
    store:createModelCredentialStore({dataParent,safeStorage,platform:'win32'})};
}
(async()=>{
  const first=fixture('recover');
  first.setAvailable(false);
  assert.equal((await first.store.status()).code,'CREDENTIAL_STORAGE_UNAVAILABLE');
  first.setAvailable(true);
  assert.equal((await first.store.status()).status,'empty');
  assert.equal((await first.store.save(secret)).status,'saved');
  const before=fs.readFileSync(first.file);
  first.safeStorage.encryptStringAsync=async()=>{throw Object.assign(new Error('synthetic failure'),{isTemporarilyUnavailable:true});};
  assert.equal((await first.store.save(secret+'-replace')).code,'CREDENTIAL_STORAGE_UNAVAILABLE');
  assert.deepEqual(fs.readFileSync(first.file),before);
  assert.equal((await first.store.status()).status,'saved');
  checks.push('transient protection failure recovers; failed replacement preserves prior bytes');

  const second=fixture('decrypt-race');
  assert.equal((await second.store.save(secret)).status,'saved');
  const moved=path.join(root,'decrypt-race-moved'),outside=path.join(root,'decrypt-race-outside');
  fs.mkdirSync(outside);
  fs.writeFileSync(path.join(outside,'deepseek.bin'),'outside sentinel');
  second.safeStorage.decryptStringAsync=async()=>{
    fs.renameSync(second.directory,moved);
    fs.symlinkSync(outside,second.directory,'junction');
    return {result:secret,shouldReEncrypt:false};
  };
  assert.equal((await second.store.status()).code,'CREDENTIAL_PATH_UNSAFE');
  assert.equal(fs.readFileSync(path.join(outside,'deepseek.bin'),'utf8'),'outside sentinel');
  fs.unlinkSync(second.directory);
  checks.push('directory junction swap during awaited decryption is rejected without touching target');

  // Deliberately inject a concurrent filesystem mutation immediately before the
  // path-based unlink syscall. This describes the untrusted same-user-process
  // boundary, not a normal UI action or a measured real-process race rate.
  const third=fixture('sync-race');
  assert.equal((await third.store.save(secret)).status,'saved');
  const raceMoved=path.join(root,'sync-race-moved'),raceOutside=path.join(root,'sync-race-outside');
  fs.mkdirSync(raceOutside);
  const sentinel=path.join(raceOutside,'deepseek.bin');
  fs.writeFileSync(sentinel,'outside sentinel');
  const originalUnlink=fs.unlinkSync;
  let swapped=false;
  try{
    fs.unlinkSync=function(target,...args){
      if(target===third.file&&!swapped){
        swapped=true;fs.renameSync(third.directory,raceMoved);
        fs.symlinkSync(raceOutside,third.directory,'junction');
      }
      return originalUnlink.call(fs,target,...args);
    };
    assert.equal((await third.store.remove()).status,'empty');
  }finally{fs.unlinkSync=originalUnlink;}
  assert.equal(swapped,true);
  assert.equal(fs.existsSync(sentinel),false);
  assert.equal(fs.existsSync(path.join(raceMoved,'deepseek.bin')),true);
  fs.unlinkSync(third.directory);
  checks.push('observed documented residual: a deliberately injected post-check junction swap can redirect path-based unlink');
  console.log(JSON.stringify({status:'completed',platform:process.platform,node:process.version,
    normal_and_async_guard_groups:2,residual_boundary_probes:1,checks},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{
  const resolved=path.resolve(root);
  assert.equal(path.dirname(resolved),area);
  assert.ok(path.basename(resolved).startsWith('independent-fixture-'));
  fs.rmSync(resolved,{recursive:true,force:true});
});
