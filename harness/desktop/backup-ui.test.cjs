const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');

function loadController(){
  const module={exports:{}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'backup.js'),'utf8'),{module,console});
  return module.exports.createBackupController;
}
function fixture(overrides={}){
  let state={data:'C:/synthetic/current',previousData:null,maintenance:false,busy:false,engineReady:true,selected:{},...overrides};
  const calls=[],renders=[];
  const api={state:async()=>state,choose:async kind=>{calls.push(['choose',kind]);state={...state,selected:{...state.selected,[kind]:'C:/synthetic/chosen'}};},
    act:async(action,input)=>{calls.push([action,input]);return {ok:true};}};
  const controller=loadController()({api,onState:value=>renders.push(value)});
  return {controller,calls,renders,api,setState:value=>{state=value;}};
}
test('no privileged action runs before state is loaded or maintenance is confirmed',async()=>{
  const f=fixture();
  await f.controller.act('backup',{password:'synthetic-password',passwordConfirm:'synthetic-password'});
  assert.equal(f.calls.length,0);
  await f.controller.refresh();await f.controller.act('pause',{confirm:false});
  assert.equal(f.calls.length,0);
  await f.controller.act('pause',{confirm:true});
  assert.equal(f.calls[0][0],'pause');assert.equal(f.calls[0][1].confirm,true);
});
test('backup checks password confirmation and sends no directory or executable supplied by the page',async()=>{
  const f=fixture({maintenance:true,selected:{backupParent:'C:/synthetic/backups'}});await f.controller.refresh();
  await f.controller.act('backup',{password:'synthetic-password',passwordConfirm:'different-password'});assert.equal(f.calls.length,0);
  await f.controller.act('backup',{password:'synthetic-password',passwordConfirm:'synthetic-password',python:'C:/untrusted.exe',backupParent:'C:/untrusted'});
  assert.equal(f.calls.length,1);assert.deepEqual(Object.keys(f.calls[0][1]).sort(),['password','passwordConfirm']);
});
test('pending work needs an explicit decision for every item before preparing a separate activation copy',async()=>{
  const f=fixture({maintenance:true,selected:{activationParent:'C:/synthetic/activation'},review:{reviewToken:'review-1',pending:[{id:'a'},{id:'b'}]}});await f.controller.refresh();
  await f.controller.act('prepare',{reviewToken:'review-1',applySettings:false,decisions:{a:'hold'}});assert.equal(f.calls.length,0);
  await f.controller.act('prepare',{reviewToken:'stale',applySettings:false,decisions:{a:'hold',b:'draft'}});assert.equal(f.calls.length,0);
  await f.controller.act('prepare',{reviewToken:'review-1',applySettings:false,decisions:{a:'hold',b:'draft'}});
  assert.equal(f.calls[0][0],'prepare');assert.equal(f.calls[0][1].decisions.b,'draft');
});
test('activation and rollback require their matching state and an explicit confirmation',async()=>{
  const f=fixture({maintenance:true});await f.controller.refresh();
  await f.controller.act('activate',{confirm:true});await f.controller.act('rollback',{confirm:true});assert.equal(f.calls.length,0);
  f.setState({maintenance:true,engineReady:true,selected:{},prepared:{destination:'C:/synthetic/prepared'},previousData:'C:/synthetic/original'});await f.controller.refresh();
  await f.controller.act('activate',{confirm:false});assert.equal(f.calls.length,0);
  await f.controller.act('activate',{confirm:true});await f.controller.act('rollback',{confirm:true});assert.deepEqual(f.calls.map(c=>c[0]),['activate','rollback']);
});
test('a pending operation prevents duplicate submission and folder changes',async()=>{
  const f=fixture({maintenance:true,selected:{reviewRoot:'C:/synthetic/restored'}});await f.controller.refresh();
  let finish;f.api.act=(action,input)=>{f.calls.push([action,input]);return new Promise(resolve=>{finish=resolve;});};
  const pending=f.controller.act('review');await f.controller.act('review');await f.controller.choose('reviewRoot');
  assert.equal(f.calls.length,1);assert.equal(f.renders.at(-1).busy,true);
  finish({ok:true});await pending;assert.equal(f.renders.at(-1).busy,false);
});
test('a failed operation keeps the page usable, refreshes state, and never displays exception text',async()=>{
  const f=fixture({maintenance:true,selected:{reviewRoot:'C:/synthetic/restored'}});await f.controller.refresh();
  f.api.act=async()=>{throw Error('synthetic-secret-must-not-leak');};
  await f.controller.act('review');assert.equal(f.renders.at(-1).busy,false);
  assert.match(f.renders.at(-1).error,/重试/);assert.doesNotMatch(JSON.stringify(f.renders),/synthetic-secret-must-not-leak/);
  await f.controller.choose('reviewRoot');assert.equal(f.calls.length,1);
});
test('missing engine and unselected restore paths never start recovery',async()=>{
  const f=fixture({maintenance:true,engineReady:false,selected:{bundle:'C:/synthetic/backup',restoreParent:'C:/synthetic/restore'}});await f.controller.refresh();
  await f.controller.act('restore',{password:'synthetic-password'});assert.equal(f.calls.length,0);
  await f.controller.act('prepareEngine');assert.equal(f.calls[0][0],'prepareEngine');
});
test('entering maintenance without a confirmed stop keeps backup blocked and permits a stop retry',async()=>{
  const f=fixture({maintenance:true,stopped:false,selected:{backupParent:'C:/synthetic/backups'}});await f.controller.refresh();
  await f.controller.act('backup',{password:'synthetic-password',passwordConfirm:'synthetic-password'});assert.equal(f.calls.length,0);
  await f.controller.act('pause',{confirm:true});assert.equal(f.calls[0][0],'pause');
});
test('preload exposes only the three backup channels and rejects unknown actions and folder kinds',async()=>{
  const calls=[];let exposed;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'backup-preload.cjs'),'utf8'),{require:name=>{
    assert.equal(name,'electron');return {contextBridge:{exposeInMainWorld:(name,api)=>{assert.equal(name,'qxBackup');exposed=api;}},ipcRenderer:{invoke:(...args)=>{calls.push(args);return Promise.resolve(null);}}};}});
  await exposed.state();await exposed.choose('reviewRoot');await exposed.act('review');await exposed.choose('exe');await exposed.act('runShell');
  assert.deepEqual(calls.map(c=>c[0]),['qx:backup-state','qx:backup-choose','qx:backup-action']);
  assert.equal(Object.isFrozen(exposed),true);
});
