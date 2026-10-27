const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const desktop=path.resolve(__dirname,'..');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};

function page() {
  const html=fs.readFileSync(path.join(desktop,'setup.html'),'utf8'),elements=new Map(),listeners=new Map(),calls=[];
  class Element {
    constructor(tag){this.tag=tag;this.value='';this.hidden=false;this.disabled=false;this.listeners={};this.textContent='';}
    addEventListener(name,listener){this.listeners[name]=listener;}focus(){}setAttribute(name,value){this[name]=value;}
  }
  for(const match of html.matchAll(/<(\w+)\b[^>]*\bid="([^"]+)"/g))elements.set('#'+match[2],new Element(match[1]));
  const document={querySelector:selector=>elements.get(selector),querySelectorAll:selector=>selector==='button'
    ?[...elements.values()].filter(value=>value.tag==='button'):[]};
  let onState;
  const api={onState:fn=>onState=fn,state:async()=>({mode:'setup'}),chooseLibrary(){},start(){},maintenance(){},
    resume:async()=>calls.push(['resume'])};
  for(const prefix of ['model','judge']) {
    api[prefix+'Status']=async()=>{calls.push([prefix+'Status']);return {status:'empty'};};
    api[prefix+'Save']=async secret=>{calls.push([prefix+'Save',secret]);return {status:'saved'};};
    api[prefix+'Remove']=async()=>{calls.push([prefix+'Remove']);return {status:'empty'};};
    api[prefix+'RuntimeStatus']=async()=>{calls.push([prefix+'RuntimeStatus']);return {ok:true,runtime:{state:'unconfigured',model:null}};};
    api[prefix+'Configure']=async model=>{calls.push([prefix+'Configure',model]);return {ok:true,runtime:{state:'configured',model}};};
    api[prefix+'Disable']=async()=>{calls.push([prefix+'Disable']);return {ok:true,runtime:{state:'unconfigured',model:null}};};
  }
  const window={desktopSetup:api,addEventListener:(name,fn)=>listeners.set(name,fn)};
  const context=vm.createContext({document,window,console});
  vm.runInContext(fs.readFileSync(path.join(desktop,'setup-model.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(desktop,'setup.js'),'utf8'),context);
  return {api,calls,listeners,at:id=>elements.get('#'+id),state:value=>onState(value),html};
}

test('optional Jev credentials and runtime have separate explicit actions and no automatic configuration',async()=>{
  const f=page();await tick();
  assert.ok(f.at('judge-settings'),'Jev settings area is missing');
  f.state({mode:'model-settings'});await tick();
  assert.deepEqual(f.calls,[['modelStatus'],['modelRuntimeStatus'],['judgeStatus'],['judgeRuntimeStatus']]);
  assert.equal(f.at('judge-settings').hidden,false);
  assert.equal(f.at('judge-id').value,'jev-1.13.0');
  assert.match(f.at('judge-status').textContent,/尚未保存/);
  assert.match(f.at('judge-runtime-status').textContent,/未配置.*未批准/);
  assert.equal(f.at('judge-configure').disabled,true);
  f.calls.length=0;
  f.at('judge-secret').value='synthetic-typesafe-secret';
  const pending=f.at('judge-settings').listeners.submit({preventDefault(){}});
  assert.equal(f.at('judge-secret').value,'');await pending;
  assert.deepEqual(f.calls,[['judgeSave','synthetic-typesafe-secret'],['judgeRuntimeStatus']]);
  assert.match(f.at('judge-status').textContent,/已保存/);
  assert.match(f.at('judge-save').textContent,/替换/);
  assert.equal(f.at('judge-configure').disabled,false);
  await f.at('judge-configure').listeners.click();
  assert.deepEqual(f.calls.at(-1),['judgeConfigure','jev-1.13.0']);
  assert.match(f.at('judge-runtime-status').textContent,/本次运行已配置.*尚未批准发送/);
  assert.doesNotMatch(f.at('judge-runtime-status').textContent,/已连接|免费/);
  await f.at('judge-disable').listeners.click();
  assert.match(f.at('judge-runtime-status').textContent,/未配置/);
  assert.match(f.at('judge-status').textContent,/已保存/);
  await f.at('judge-remove').listeners.click();
  assert.match(f.at('judge-status').textContent,/已移除/);
  assert.equal(f.at('judge-configure').disabled,true);
});

test('disabled credential actions do not dispatch and rechecking restores an unavailable Jev section',async()=>{
  const f=page();await tick();
  f.api.judgeStatus=async()=>({status:'unavailable',code:'CREDENTIAL_STORAGE_UNAVAILABLE'});
  f.state({mode:'model-settings'});await tick();f.calls.length=0;
  assert.equal(f.at('judge-save').disabled,true);
  assert.equal(f.at('judge-recheck').disabled,false);
  f.at('judge-secret').value='synthetic-forced-input';
  await f.at('judge-settings').listeners.submit({preventDefault(){}});
  assert.equal(f.at('judge-secret').value,'');assert.deepEqual(f.calls,[]);
  f.api.judgeStatus=async()=>({status:'empty'});
  await f.at('judge-recheck').listeners.click();
  assert.equal(f.at('judge-save').disabled,false);
  assert.equal(f.at('judge-remove').disabled,true);f.calls.length=0;
  await f.at('judge-remove').listeners.click();assert.deepEqual(f.calls,[]);
});

test('initial reads hold one shared lock and never overlap the private control channel',async()=>{
  const f=page();await tick();const gate=deferred();
  f.api.modelStatus=async()=>{f.calls.push(['modelStatus']);await gate.promise;return {status:'saved'};};
  f.state({mode:'model-settings'});await tick();
  assert.deepEqual(f.calls,[['modelStatus']]);
  for(const prefix of ['model','judge']) {
    for(const id of ['save','remove','configure','disable','recheck','secret','id'])assert.equal(f.at(prefix+'-'+id).disabled,true,id);
    assert.equal(f.at(prefix+'-settings')['aria-busy'],'true');
  }
  assert.equal(f.at('resume').disabled,true);
  await f.at('judge-recheck').listeners.click();await f.at('resume').listeners.click();
  f.state({mode:'model-settings'});assert.deepEqual(f.calls,[['modelStatus']]);
  gate.resolve();await tick();
  assert.deepEqual(f.calls,[['modelStatus'],['modelRuntimeStatus'],['judgeStatus'],['judgeRuntimeStatus']]);
  assert.equal(f.at('resume').disabled,false);
});

for(const prefix of ['model','judge'])test(`${prefix} operation locks both providers and return without queuing duplicate actions`,async()=>{
  const f=page();await tick();
  f.api.modelStatus=f.api.judgeStatus=async()=>({status:'saved'});
  f.state({mode:'model-settings'});await tick();f.calls.length=0;
  const gate=deferred(),other=prefix==='model'?'judge':'model';
  f.api[prefix+'Save']=async secret=>{f.calls.push([prefix+'Save',secret]);await gate.promise;return {status:'saved'};};
  f.at(prefix+'-secret').value='synthetic-save-secret';f.at(other+'-secret').value='synthetic-unsent-secret';
  const pending=f.at(prefix+'-settings').listeners.submit({preventDefault(){}});
  assert.equal(f.at('model-secret').value,'');assert.equal(f.at('judge-secret').value,'');
  await f.at(other+'-configure').listeners.click();await f.at(other+'-remove').listeners.click();
  await f.at(other+'-recheck').listeners.click();await f.at('resume').listeners.click();
  f.state({mode:'model-settings'});
  assert.equal(f.at('resume').disabled,true);
  assert.deepEqual(f.calls,[[prefix+'Save','synthetic-save-secret']]);
  gate.resolve();await pending;
  assert.deepEqual(f.calls,[[prefix+'Save','synthetic-save-secret'],[prefix+'RuntimeStatus']]);
  assert.equal(f.at('resume').disabled,false);assert.equal(f.at(other+'-configure').disabled,false);
});

for(const phase of ['save','runtime','configure'])test(`late Jev ${phase} response cannot revive settings or clear new input`,async()=>{
  const f=page();await tick();f.api.judgeStatus=async()=>({status:'saved'});
  f.state({mode:'model-settings'});await tick();const gate=deferred();
  let pending;
  if(phase==='save') {
    f.api.judgeSave=()=>gate.promise;f.at('judge-secret').value='synthetic-old-secret';
    pending=f.at('judge-settings').listeners.submit({preventDefault(){}});
  } else if(phase==='runtime') {
    f.api.judgeRuntimeStatus=()=>gate.promise;pending=f.at('judge-recheck').listeners.click();await tick();
  } else {
    f.api.judgeConfigure=()=>gate.promise;pending=f.at('judge-configure').listeners.click();
  }
  f.state({mode:'error',message:'固定错误状态'});
  assert.equal(f.at('judge-settings').hidden,true);assert.equal(f.at('model-settings').hidden,true);
  f.api.judgeRuntimeStatus=async()=>({ok:true,runtime:{state:'unconfigured',model:null}});
  f.state({mode:'model-settings'});await tick();
  f.at('judge-secret').value='synthetic-new-judge';f.at('model-secret').value='synthetic-new-main';
  gate.resolve(phase==='save'?{status:'saved'}:{ok:true,runtime:{state:'configured',model:'jev-1.13.0'}});await pending;
  assert.equal(f.at('judge-secret').value,'synthetic-new-judge');assert.equal(f.at('model-secret').value,'synthetic-new-main');
  assert.match(f.at('judge-runtime-status').textContent,/未配置/);
  f.listeners.get('pagehide')();
  assert.equal(f.at('judge-secret').value,'');assert.equal(f.at('model-secret').value,'');
  f.calls.length=0;await f.at('judge-configure').listeners.click();assert.deepEqual(f.calls,[]);
});

test('Jev rejects a model from the other provider even without a selection change event',async()=>{
  const f=page();await tick();f.api.judgeStatus=async()=>({status:'saved'});
  f.state({mode:'model-settings'});await tick();f.calls.length=0;
  f.at('judge-id').value='deepseek-flash';
  await f.at('judge-configure').listeners.click();assert.deepEqual(f.calls,[]);
  f.at('judge-id').listeners.change();assert.equal(f.at('judge-configure').disabled,true);
});

test('Jev error projection has no private text and corrupt storage remains replaceable',async()=>{
  const f=page();await tick();
  f.api.judgeStatus=async()=>({status:'invalid',code:'CREDENTIAL_CORRUPT',secret:'synthetic-private'});
  f.api.judgeRuntimeStatus=async()=>({ok:false,runtime:{state:'unavailable',model:null},code:'synthetic-private'});
  f.state({mode:'model-settings'});await tick();
  assert.match(f.at('judge-status').textContent,/需要处理/);
  assert.equal(f.at('judge-save').disabled,false);assert.equal(f.at('judge-remove').disabled,false);
  assert.equal(f.at('judge-configure').disabled,true);
  assert.doesNotMatch(f.at('judge-runtime-validation').textContent,/synthetic/);
  f.api.judgeSave=async()=>{throw Error('synthetic-private');};
  f.at('judge-secret').value='synthetic-secret';await f.at('judge-settings').listeners.submit({preventDefault(){}});
  assert.equal(f.at('judge-secret').value,'');assert.doesNotMatch(f.at('judge-validation').textContent,/synthetic/);
  f.api.judgeStatus=async()=>({status:'saved'});
  f.api.judgeRuntimeStatus=async()=>({ok:true,runtime:{state:'configured',model:'deepseek-flash',secret:'synthetic-private'}});
  await f.at('judge-recheck').listeners.click();
  assert.doesNotMatch(f.at('judge-runtime-status').textContent,/已配置|synthetic|DeepSeek/);
  assert.equal(f.at('judge-configure').disabled,true);
});

test('return and document exit clear both unsubmitted passwords',async()=>{
  const f=page();await tick();f.state({mode:'model-settings'});await tick();
  f.at('model-secret').value='synthetic-main';f.at('judge-secret').value='synthetic-judge';
  await f.at('resume').listeners.click();
  assert.equal(f.at('model-secret').value,'');assert.equal(f.at('judge-secret').value,'');
  assert.deepEqual(f.calls.at(-1),['resume']);
  f.state({mode:'model-settings'});await tick();
  f.at('model-secret').value='synthetic-main';f.at('judge-secret').value='synthetic-judge';
  f.listeners.get('beforeunload')();
  assert.equal(f.at('model-secret').value,'');assert.equal(f.at('judge-secret').value,'');
});

test('preload exposes only the six fixed Jev operations with isolated channels',()=>{
  const seen=[],exposed={};
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'preload.cjs'),'utf8'),{require:()=>({
    contextBridge:{exposeInMainWorld:(name,value)=>exposed[name]=value},
    ipcRenderer:{invoke:(...args)=>seen.push(args),on(){}}
  })});
  const api=exposed.desktopSetup;
  assert.deepEqual(Object.keys(api).filter(key=>key.startsWith('judge')).sort(),
    ['judgeConfigure','judgeDisable','judgeRemove','judgeRuntimeStatus','judgeSave','judgeStatus']);
  api.judgeStatus();api.judgeSave('synthetic-typesafe');api.judgeRemove();api.judgeRuntimeStatus();api.judgeConfigure('jev-1.13.0');api.judgeDisable();
  assert.deepEqual(seen,[['desktop:judge-status'],['desktop:judge-save','synthetic-typesafe'],['desktop:judge-remove'],
    ['desktop:judge-runtime-status'],['desktop:judge-configure','jev-1.13.0'],['desktop:judge-disable']]);
  assert.equal(Object.isFrozen(api),true);assert.deepEqual(Object.keys(exposed.desktopAssistant).sort(),['authorizeContext','authorizeGeneration','authorizeMaterial','authorizeProfile','modelStatus','modelSwitch']);
});

test('Jev copy and initial controls describe optional configuration without claiming permission or a network test',()=>{
  const f=page(),area=f.html.slice(f.html.indexOf('<form id="judge-settings"'),f.html.indexOf('<button id="resume"'));
  assert.match(area,/Jev 辅助判断.*可选/);assert.match(area,/TypeSafe（api.typesafe.ai）/);
  assert.match(area,/尚未接入对话发送/);assert.match(area,/不会批准发送资料/);
  assert.doesNotMatch(area,/已连接|免费|最高收费|测试连接|联网测试/);
  assert.match(area,/<input id="judge-secret"[^>]*type="password"[^>]*autocomplete="off"[^>]*disabled/);
  assert.equal([...area.matchAll(/<option\b/g)].length,1);assert.match(area,/value="jev-1.13.0"/);
  assert.doesNotMatch(fs.readFileSync(path.join(desktop,'setup-model.js'),'utf8'),/localStorage|sessionStorage|fetch\(|XMLHttpRequest/);
});
