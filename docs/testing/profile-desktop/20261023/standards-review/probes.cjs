const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const root=path.resolve(__dirname,'../../..');
const {ModelControl}=require(path.join(root,'desktop/model-control.cjs'));
const {createModelSession}=require(path.join(root,'desktop/model-session.cjs'));
const {canonicalProfileBasis}=require(path.join(root,'desktop/profile-basis.cjs'));
const ID='11111111-2222-4333-8444-555555555555',TOKEN='INDEPENDENT_SYNTHETIC_PROFILE_TOKEN';
const protocol='qx-model-control-v1',nonce='1'.repeat(32);
const basis=()=>({input_format:'profile-text-v1',template_version:'profile-text-system-v1',purpose:'reply_and_profile_draft',handler_id:'profile.save',handler_version:'1',request_id:ID,expected_scope:{workspace_id:ID,conversation_id:ID,scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0},expected_composer_revision:1,content_sha256:'a'.repeat(64),base_profile_revision:0,expected_intake_id:null,expected_intake_revision:null,project_intake:false,system_sha256:'b'.repeat(64),config_sha256:'c'.repeat(64),wire_sha256:'d'.repeat(64),wire_bytes:123});
const value=()=>({session_token:TOKEN,expected_config_version:ID,basis:basis(),max_total_usd:'0.024576',valid_for_seconds:120});
const frame=value=>Buffer.from(JSON.stringify(value)+'\n');
function channel(t,timeoutMs=100){
 const writes=[],fatal=[];
 const control=new ModelControl({nonce,timeoutMs,write:line=>writes.push(line),onReady(){},onFatal:code=>fatal.push(code)});
 t.after(()=>control.close());control.feed(frame({event:'ready',port:18392,nonce,control_protocol:protocol}));
 return {control,writes,fatal,ack(change={}){control.feed(frame({event:'model-control-result',protocol,nonce,sequence:control.sequence,ok:true,status:'authorized',...change}));}};
}
for(const [key,change] of Object.entries({nonce:{nonce:'2'.repeat(32)},sequence:{sequence:2},status:{status:'configured'}})){
 test('profile wire rejects mismatched '+key+' and cannot recover on a later valid ACK',async t=>{
  const c=channel(t),pending=c.control.request('authorize_profile',value());
  const rejected=assert.rejects(pending,/BACKEND_PROTOCOL/);c.ack(change);await rejected;
  c.ack();assert.equal(c.control.failed,true);assert.equal(c.fatal.length,1);
  assert.equal((await c.control.request('authorize_profile',value())).ok,false);assert.equal(c.writes.length,1);
 });
}
test('profile timeout clears its request and late ACK never reopens the channel',async t=>{
 const c=channel(t,5);await assert.rejects(c.control.request('authorize_profile',value()),/BACKEND_CONTROL_TIMEOUT/);
 assert.equal(c.control.pending,null);c.ack();assert.equal(c.control.failed,true);assert.deepEqual(c.fatal,['BACKEND_CONTROL_TIMEOUT']);
 assert.equal((await c.control.request('authorize_profile',value())).ok,false);assert.equal(c.writes.length,1);
});
async function session(){
 const calls=[];
 const b={closing:false,async configureModel(){return {ok:true,status:'configured',config_sha256:'c'.repeat(64),config_version:ID};},async disableModel(){return {ok:true,status:'disabled'};},async authorizeModel(){throw Error('wrong purpose');},async authorizeProfileModel(){return {ok:true,status:'authorized'};},async revokeModel(){calls.push('revoke');return {ok:true,status:'revoked'};},async stop(){calls.push('stop-old');this.closing=true;}};
 let current=b;
 const runtime=createModelSession({store:{async withSecret(fn){await fn('synthetic_key_for_independent_review');return {status:'saved'};}},getBackend:()=>current});
 assert.equal((await runtime.configure('deepseek-flash')).ok,true);
 return {b,runtime,calls,replace(next){current=next;}};
}
test('late fresh ACK after backend replacement revokes only captured backend and closes it if revoke fails',async()=>{
 const f=await session();let resolve,entered;const started=new Promise(r=>entered=r),gate=new Promise(r=>resolve=r);
 f.b.authorizeProfileModel=async()=>{entered();return gate;};
 f.b.revokeModel=async()=>{f.calls.push('revoke');throw Error('synthetic old pipe dead');};
 const fresh={async stop(){throw Error('must not stop replacement');}};
 const pending=f.runtime.withAuthorization(f.b,()=>true,lease=>lease.authorizeProfile({session_token:TOKEN,basis:basis()}));
 await started;f.replace(fresh);resolve({ok:true,status:'authorized'});
 assert.equal((await pending).ok,false);assert.deepEqual(f.calls,['revoke','stop-old']);
});
test('unawaited inner request is still awaited and callback cannot upgrade an existing ACK',async()=>{
 const f=await session();let resolve,inner;
 f.b.authorizeProfileModel=()=>new Promise(r=>resolve=r);
 let settled=false;
 const pending=f.runtime.withAuthorization(f.b,()=>true,lease=>{inner=lease.authorizeProfile({session_token:TOKEN,basis:basis()});return {ok:true,status:'authorized'};}).then(result=>{settled=true;return result;});
 await new Promise(r=>setImmediate(r));assert.equal(settled,false);resolve({ok:true,status:'existing'});
 assert.deepEqual(await pending,{ok:true,status:'existing'});assert.deepEqual(await inner,{ok:true,status:'existing'});assert.deepEqual(f.calls,[]);
});
test('native rejection cannot be papered over by callback and releases the configuration lock',async()=>{
 const f=await session();let held;
 f.b.authorizeProfileModel=async()=>({ok:false,code:'VERSION_CONFLICT'});
 const result=await f.runtime.withAuthorization(f.b,()=>true,async lease=>{held=lease;await lease.authorizeProfile({session_token:TOKEN,basis:basis()});return {ok:true,status:'existing'};});
 assert.equal(result.ok,false);assert.equal((await held.authorizeProfile({session_token:TOKEN,basis:basis()})).ok,false);
 assert.equal((await f.runtime.configure('deepseek-v4-pro')).ok,true);assert.deepEqual(f.calls,[]);
});
test('canonical scope rejects invisible own additions and never shares caller references',()=>{
 for(const target of ['basis','scope']){
  const x=basis(),o=target==='basis'?x:x.expected_scope;
  Object.defineProperty(o,'extra',{value:true,enumerable:false});assert.equal(canonicalProfileBasis(x),null);
  delete o.extra;
 }
 const x=basis();x.expected_scope[Symbol('extra')]=true;assert.equal(canonicalProfileBasis(x),null);
 const y=basis(),copy=canonicalProfileBasis(y);y.expected_scope.input_revision=99;
 assert.equal(copy.expected_scope.input_revision,0);
});
test('new profile runtime modules and their local dependencies are explicit package entries',()=>{
 const p=JSON.parse(fs.readFileSync(path.join(root,'desktop/package.json'),'utf8')),files=new Set(p.build.files);
 for(const name of ['profile-basis.cjs','profile-approval.cjs','model-approval.cjs','model-approval-window.cjs','model-session.cjs','model-control.cjs']){
  assert.ok(files.has(name),name);
  const source=fs.readFileSync(path.join(root,'desktop',name),'utf8');
  for(const match of source.matchAll(/require\(['"]\.\/([^'"]+)['"]\)/g))assert.ok(files.has(match[1]),name+' -> '+match[1]);
 }
 assert.equal(p.version,'0.4.1');
});
