const test=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {generateKeyPairSync,sign,createHash}=require('node:crypto');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const integrity=require('./update-integrity.cjs');
const {createUpdateController}=require('./updates.cjs');
test('rejected installation cannot release the key-settings operation lock',async()=>{
  const {createInstallHandoff}=require('./updates.cjs');
  let starting=true,stopped=0,recovered=0;
  const handoff=createInstallHandoff({isStarting:()=>starting,setStarting:value=>{starting=value},stop:async()=>{stopped++},restore:async()=>{recovered++}});
  await assert.rejects(handoff.prepare());await handoff.recover();
  assert.equal(starting,true);assert.equal(stopped,0);assert.equal(recovered,0);
  starting=false;await handoff.prepare();assert.equal(starting,true);
  await handoff.recover();assert.equal(starting,false);assert.equal(stopped,1);assert.equal(recovered,1);
});
const {publicKey,privateKey}=generateKeyPairSync('ed25519');
const pem=publicKey.export({type:'spki',format:'pem'});
const bytes=Buffer.from('synthetic installer, never executed');
function release(version='0.2.4'){
  const info={version,files:[{url:`Qunxing-Workbench-${version}-Setup.exe`,size:bytes.length,sha512:createHash('sha512').update(bytes).digest('base64')}],releaseNotes:'修复与改进'};
  info.qxSignature=sign(null,integrity.releasePayload(info),privateKey).toString('base64');return info;
}
test('signed release rejects tampered hashes, unsafe paths and unsigned releases',()=>{
  const info=release();assert.equal(integrity.verifyRelease(info,pem).version,'0.2.4');
  assert.throws(()=>integrity.verifyRelease({...info,version:'0.2.5'},pem));
  assert.throws(()=>integrity.verifyRelease({...info,qxSignature:''},pem));
  assert.throws(()=>integrity.verifyRelease({...info,files:[{...info.files[0],url:'../evil.exe'}]},pem));
  assert.throws(()=>integrity.verifyRelease({...info,releaseNotes:'changed'},pem));
});
async function fixture(t,overrides={}){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'qx-update-'));
  t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const installer=path.join(dir,'installer.exe');await fs.writeFile(installer,bytes);
  const updater=new EventEmitter();let downloads=0,installs=0,stops=0;
  updater.checkForUpdates=async()=>({updateInfo:release()});
  updater.downloadUpdate=async()=>{downloads++;return [installer]};
  updater.quitAndInstall=()=>{installs++};
  Object.assign(updater,overrides);
  const controller=createUpdateController({updater,version:'0.2.3',publicKey:pem,
    prepareInstall:async()=>{stops++},confirmInstall:async()=>true});
  return {controller,updater,installer,counts:()=>({downloads,installs,stops})};
}
test('installer launch rejection is awaited and the old host is recovered',async t=>{
  let recovered=0;
  const f=await fixture(t,{quitAndInstall:async()=>{throw Error('spawn failed')}});
  const c=createUpdateController({updater:f.updater,version:'0.2.3',publicKey:pem,
    confirmInstall:async()=>true,prepareInstall:async()=>{},recoverInstall:async()=>{recovered++}});
  await c.check();await c.download();await c.install();
  assert.equal(c.state().phase,'error');assert.equal(recovered,1);
});
test('checks do not download, user download verifies bytes, install stops host once',async t=>{
  const f=await fixture(t);await f.controller.check();
  assert.equal(f.controller.state().phase,'available');assert.equal(f.counts().downloads,0);
  assert.equal(f.updater.autoDownload,false);assert.equal(f.updater.autoInstallOnAppQuit,false);
  await f.controller.download();assert.equal(f.controller.state().phase,'downloaded');
  await Promise.all([f.controller.install(),f.controller.install()]);
  assert.deepEqual(f.counts(),{downloads:1,installs:1,stops:1});
});
test('corrupt download never becomes installable',async t=>{
  const f=await fixture(t);await f.controller.check();await fs.writeFile(f.installer,'corrupted');
  await f.controller.download();assert.equal(f.controller.state().phase,'error');
  await f.controller.install();assert.equal(f.counts().installs,0);
});
test('tampering after download is detected before stopping the host',async t=>{
  const f=await fixture(t);await f.controller.check();await f.controller.download();
  await fs.writeFile(f.installer,'tampered');await f.controller.install();
  assert.equal(f.controller.state().phase,'error');assert.equal(f.counts().stops,0);assert.equal(f.counts().installs,0);
});
test('downgrade and same version do not offer an update',async t=>{
  for(const version of ['0.2.2','0.2.3']){
    const f=await fixture(t,{checkForUpdates:async()=>({updateInfo:release(version)})});
    await f.controller.check();assert.equal(f.controller.state().phase,'idle');
    await f.controller.download();assert.equal(f.counts().downloads,0);
  }
});
test('check failure leaves old app usable and exposes no raw error or URL',async t=>{
  const f=await fixture(t,{checkForUpdates:async()=>{throw Error('SECRET https://example.invalid/?token=secret')}});
  await f.controller.check();assert.equal(f.controller.state().phase,'error');
  assert.doesNotMatch(JSON.stringify(f.controller.state()),/SECRET|token=/);
  assert.equal(f.counts().stops,0);
});
test('unsigned new release is never offered or downloaded',async t=>{
  const f=await fixture(t,{checkForUpdates:async()=>({updateInfo:{...release(),qxSignature:'wrong'}})});
  await f.controller.check();await f.controller.download();assert.equal(f.counts().downloads,0);
});
test('host stop failure prevents installation',async t=>{
  const f=await fixture(t);
  const controller=createUpdateController({updater:f.updater,version:'0.2.3',publicKey:pem,
    prepareInstall:async()=>{throw Error('busy')},confirmInstall:async()=>true});
  await controller.check();await controller.download();await controller.install();
  assert.equal(controller.state().phase,'error');assert.equal(f.counts().installs,0);
});
test('declining install keeps downloaded update and host untouched',async t=>{
  const f=await fixture(t);let stopped=false;
  const controller=createUpdateController({updater:f.updater,version:'0.2.3',publicKey:pem,
    prepareInstall:async()=>{stopped=true},confirmInstall:async()=>false});
  await controller.check();await controller.download();await controller.install();
  assert.equal(controller.state().phase,'downloaded');assert.equal(stopped,false);
});
test('cancel does not allow an immediately repeated download before cleanup',async t=>{
  let finish,token;
  const f=await fixture(t,{downloadUpdate:value=>{token=value;return new Promise(resolve=>{finish=resolve})}});
  await f.controller.check();const pending=f.controller.download();f.controller.cancel();
  assert.equal(token.cancelled,true);assert.equal(f.controller.state().phase,'cancelling');
  await f.controller.download();finish([f.installer]);await pending;
  assert.equal(f.controller.state().phase,'available');assert.equal(f.controller.state().ready,false);
});

test('full fallback resets progress and remains cancellable without making a file installable',async t=>{
  const f=await fixture(t);let finish;
  f.updater.downloadUpdate=()=>new Promise(resolve=>{finish=resolve});
  await f.controller.check();const pending=f.controller.download();
  f.updater.emit('download-progress',{percent:87,transferred:31,total:36});
  f.updater.emit('qx-download-mode',{mode:'full',total:590});
  assert.equal(f.controller.state().progress,0);assert.equal(f.controller.state().transferred,0);
  assert.equal(f.controller.state().downloadMode,'full');assert.equal(f.controller.state().total,590);
  f.controller.cancel();finish([f.installer]);await pending;
  assert.equal(f.controller.state().ready,false);assert.equal(f.controller.state().phase,'available');
});

test('disk and integrity errors are not reported as network failures',async t=>{
  for(const code of ['ENOSPC','EACCES','ERR_CHECKSUM_MISMATCH']){
    const f=await fixture(t,{downloadUpdate:async()=>{throw Object.assign(Error('private path'),{code})}});
    await f.controller.check();await f.controller.download();
    assert.doesNotMatch(f.controller.state().error,/网络|连接|private path/);
    assert.equal(f.controller.state().ready,false);
  }
});
