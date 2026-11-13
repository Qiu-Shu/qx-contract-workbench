const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createBackupController}=require('./backup-controller.cjs');
function fixture(t,overrides={}){
 const anchor=fs.mkdtempSync(path.join(os.tmpdir(),'qx-controller-'));t.after(()=>fs.rmSync(anchor,{recursive:true,force:true}));let maintenance=false;const calls=[];
 const controller=createBackupController({anchor,data:anchor,payload:anchor,credentialStatus:async()=>({status:'missing'}),engineReady:()=>true,
 setMaintenance:value=>{maintenance=value;},stop:async()=>calls.push('stop'),resume:async()=>calls.push('resume'),relaunch:()=>calls.push('relaunch'),
 pick:async()=>anchor,prepareEngine:async()=>{},backup:async options=>{calls.push(options);return {fileCount:1};},
 inspect:async()=>({reviewToken:'checked',pending:[{id:'pending'}]}),prepare:async options=>({destination:options.destination}),
 initialize:async()=>calls.push('initialize'),select:()=>calls.push('select'),rollback:()=>calls.push('rollback'),openDrafts:async()=>{},...overrides});
 return {anchor,controller,calls,isMaintenance:()=>maintenance};
}
test('maintenance is required and runtime paths cannot be injected from renderer',async t=>{
 const {controller,calls}=fixture(t);
 assert.equal((await controller.act('backup',{password:'synthetic-secret'})).ok,false);assert.equal(calls.length,0);
 await controller.act('pause',{confirm:true});await controller.choose('backupParent');
 await controller.act('backup',{password:'synthetic-secret',passwordConfirm:'synthetic-secret',data:'C:/victim',bundle:'C:/victim',restic:'C:/evil.exe'});
 const request=calls.find(item=>typeof item==='object');assert.ok(request.bundle.includes('backup-'));assert.notEqual(request.data,'C:/victim');assert.notEqual(request.restic,'C:/evil.exe');
 assert.ok(!JSON.stringify(await controller.state()).includes('synthetic-secret'));
});
test('pause closes startup gate before stop; failures keep maintenance closed and expose stable errors',async t=>{
 let controller,gate=false;const f=fixture(t,{setMaintenance:value=>gate=value,stop:async()=>{assert.equal(gate,true);throw Error('secret-value');}});controller=f.controller;
 assert.equal((await controller.act('pause',{confirm:true})).ok,false);assert.equal(gate,true);const state=await controller.state();assert.equal(state.maintenance,true);assert.ok(!JSON.stringify(state).includes('secret-value'));
});
test('prepare requires explicit current decisions and activate initializes before selecting/relaunching',async t=>{
 const {controller,calls}=fixture(t);await controller.act('pause',{confirm:true});await controller.choose('reviewRoot');await controller.choose('activationParent');await controller.act('review');
 assert.equal((await controller.act('prepare',{reviewToken:'checked',decisions:{}})).ok,false);
 await controller.act('prepare',{reviewToken:'checked',decisions:{pending:'hold'},applySettings:false});
 assert.equal((await controller.act('activate',{confirm:false})).ok,false);await controller.act('activate',{confirm:true});
 assert.deepEqual(calls.slice(-3),['initialize','select','relaunch']);
});
test('concurrent operations are refused and a failed operation can be retried',async t=>{
 let release;const {controller,calls}=fixture(t,{backup:async()=>{await new Promise(resolve=>release=resolve);return {fileCount:1};}});
 await controller.act('pause',{confirm:true});await controller.choose('backupParent');
 const pending=controller.act('backup',{password:'synthetic-secret',passwordConfirm:'synthetic-secret'});
 assert.equal((await controller.act('resume')).ok,false);release();await pending;assert.equal((await controller.state()).busy,false);await controller.act('resume');assert.equal(calls.at(-1),'resume');
});
test('a missing active copy still rolls back to the recorded previous copy, not the installation anchor',async t=>{
 const {anchor}=fixture(t),locations=require('./data-location.cjs');
 const parent=fs.mkdtempSync(path.join(os.tmpdir(),'qx-previous-copies-'));t.after(()=>fs.rmSync(parent,{recursive:true,force:true}));
 const second=path.join(parent,'second'),third=path.join(parent,'third');
 for(const data of [second,third]){fs.mkdirSync(path.join(data,'.local'),{recursive:true});fs.writeFileSync(path.join(data,'.local/restore-activation.json'),JSON.stringify({schema:1,phase:'ready',data}));fs.writeFileSync(path.join(data,'.local/initialized-payload.json'),JSON.stringify({schema:2,data}));}
 locations.selectDataLocation(anchor,second);locations.selectDataLocation(anchor,third);fs.renameSync(third,third+'-moved');
 const controller=createBackupController({anchor,data:anchor,payload:anchor,selectionError:'LOCATION_MISSING',credentialStatus:async()=>({status:'unavailable'}),engineReady:()=>false,setMaintenance:()=>{},stop:async()=>{},relaunch:()=>{}});
 assert.equal((await controller.state()).previousData,second);await controller.act('pause',{confirm:true});assert.equal((await controller.act('rollback',{confirm:true})).ok,true);assert.equal(locations.resolveDataLocation(anchor).data,second);
});
