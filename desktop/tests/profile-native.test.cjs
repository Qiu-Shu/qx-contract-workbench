const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ModelControl}=require('../model-control.cjs');
const {Backend}=require('../backend.cjs');
const {createModelSession}=require('../model-session.cjs');
const VERSION='11111111-2222-4333-8444-555555555555';
const REQUEST='aaaaaaaa-2222-4333-8444-555555555555';
const INTAKE='bbbbbbbb-2222-4333-8444-555555555555';
const TOKEN='SYNTHETIC_PROFILE_SESSION_20261023';
const protocol='qx-model-control-v1',nonce='a'.repeat(32);
const frame=value=>Buffer.from(JSON.stringify(value)+'\n');
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));

function basis(){return {input_format:'profile-text-v1',template_version:'profile-text-system-v1',
  purpose:'reply_and_profile_draft',handler_id:'profile.save',handler_version:'1',request_id:REQUEST,
  expected_scope:{workspace_id:VERSION,conversation_id:VERSION,scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0},expected_composer_revision:1,
  content_sha256:'a'.repeat(64),base_profile_revision:0,expected_intake_id:null,expected_intake_revision:null,
  project_intake:true,system_sha256:'b'.repeat(64),config_sha256:'c'.repeat(64),wire_sha256:'d'.repeat(64),wire_bytes:512};}
function payload(){return {session_token:TOKEN,expected_config_version:VERSION,basis:basis(),
  max_total_usd:'0.024576',valid_for_seconds:120};}
function channel(t){
  const writes=[],fatal=[];
  const control=new ModelControl({nonce,write:line=>writes.push(JSON.parse(line)),onReady(){},onFatal:code=>fatal.push(code)});
  t.after(()=>control.close());
  control.feed(frame({event:'ready',port:19022,nonce,control_protocol:protocol}));
  return {control,writes,fatal,reply(values){control.feed(frame({event:'model-control-result',protocol,nonce,
    sequence:control.sequence,ok:true,status:'authorized',...values}));}};
}
async function sessionFixture(){
  const calls=[],sent=[];
  const backend={control:{ready:true,enabled:true,closed:false,failed:false},closing:false,
    async configureModel(){return {ok:true,status:'configured',config_sha256:'c'.repeat(64),config_version:VERSION};},
    async disableModel(){return {ok:true,status:'disabled'};},
    async authorizeModel(){calls.push('plain');return {ok:true,status:'authorized'};},
    async authorizeContextModel(){calls.push('context');return {ok:true,status:'authorized'};},
    async authorizeProfileModel(value){calls.push('profile');sent.push(value);return {ok:true,status:'authorized'};},
    async revokeModel(value){calls.push('revoke');sent.push(value);return {ok:true,status:'revoked'};},
    async stop(){calls.push('stop');this.closing=true;}};
  let current=backend;
  const runtime=createModelSession({store:{async withSecret(fn){await fn('synthetic_secret');return {status:'saved'};}},
    getBackend:()=>current});
  await runtime.configure('deepseek-flash');
  return {runtime,backend,calls,sent,replace(value){current=value;}};
}
const authorize=lease=>{
  assert.equal(typeof lease.authorizeProfile,'function','profile lease entry is required');
  return lease.authorizeProfile({session_token:TOKEN,basis:basis()});
};

test('private profile request uses its explicit five-field operation and trusted ACK',async t=>{
  const f=channel(t),value=payload(),pending=f.control.request('authorize_profile',value);
  assert.equal(f.writes.length,1,'valid profile authorization must reach the existing private pipe');
  assert.equal(f.writes[0].operation,'authorize_profile');
  assert.deepEqual(f.writes[0].payload,value);
  f.reply();assert.deepEqual(await pending,{ok:true,status:'authorized'});
  const second=f.control.request('authorize_profile',value);f.reply({status:'existing'});
  assert.deepEqual(await second,{ok:true,status:'existing'});
});

test('backend profile entry delegates to its current private control only',async()=>{
  const backend=new Backend('unused');
  assert.equal(typeof backend.authorizeProfileModel,'function');
  assert.deepEqual(await backend.authorizeProfileModel(payload()),{ok:false,code:'BLOCKED_LIVE'});
  const calls=[];backend.control={request:async(...args)=>{calls.push(args);return {ok:true,status:'existing'};}};
  assert.deepEqual(await backend.authorizeProfileModel(payload()),{ok:true,status:'existing'});
  assert.deepEqual(calls,[['authorize_profile',payload()]]);
});

test('canonical profile basis validates all 17 fields and returns an independent ordered copy',()=>{
  const {validProfileBasis,canonicalProfileBasis}=require('../profile-basis.cjs');
  const value=basis(),reversed=Object.fromEntries(Object.entries(value).reverse());
  reversed.expected_scope=Object.fromEntries(Object.entries(value.expected_scope).reverse());
  assert.equal(validProfileBasis(value),true);assert.equal(Object.keys(value).length,17);
  const canonical=canonicalProfileBasis(reversed);
  assert.equal(JSON.stringify(canonical),JSON.stringify(canonicalProfileBasis(value)));
  value.expected_scope.input_revision=8;reversed.expected_scope.binding_revision=9;
  assert.equal(canonical.expected_scope.input_revision,0);assert.equal(canonical.expected_scope.binding_revision,1);
  const intake=basis();intake.expected_scope.scope_kind='intake';intake.expected_scope.scope_ref=INTAKE;
  intake.expected_intake_id=INTAKE;intake.expected_intake_revision=2;
  assert.equal(validProfileBasis(intake),true);
});

const invalidBasis={
  extra:value=>{value.extra=true;},missing:value=>{delete value.purpose;},
  format:value=>{value.input_format='plain-text-v1';},template:value=>{value.template_version='other';},
  purpose:value=>{value.purpose='primary_intent';},handler:value=>{value.handler_id='other';},
  handlerVersion:value=>{value.handler_version=1;},request:value=>{value.request_id='invalid';},
  digest:value=>{value.config_sha256='A'.repeat(64);},boolean:value=>{value.project_intake='true';},
  integer:value=>{value.base_profile_revision=true;},unsafe:value=>{value.expected_composer_revision=2**53;},
  wire:value=>{value.wire_bytes=262145;},emptyWire:value=>{value.wire_bytes=0;},
  scopeExtra:value=>{value.expected_scope.extra=1;},scopeRef:value=>{value.expected_scope.scope_ref=INTAKE;},
  scopeKind:value=>{value.expected_scope.scope_kind='other';},scopeId:value=>{value.expected_scope.workspace_id='invalid';},
  scopeRevision:value=>{value.expected_scope.binding_revision=0;},negative:value=>{value.expected_scope.input_revision=-1;},
  pairedId:value=>{value.expected_intake_id=INTAKE;},pairedRevision:value=>{value.expected_intake_revision=1;},
  intakeScope:value=>{value.expected_scope.scope_kind='intake';value.expected_scope.scope_ref=INTAKE;},
};
for(const [name,mutate] of Object.entries(invalidBasis))test(`profile basis rejects ${name} without a pipe request`,async t=>{
  const value=payload();mutate(value.basis);
  const {validProfileBasis,canonicalProfileBasis}=require('../profile-basis.cjs');
  assert.equal(validProfileBasis(value.basis),false);assert.equal(canonicalProfileBasis(value.basis),null);
  const f=channel(t);assert.deepEqual(await f.control.request('authorize_profile',value),{ok:false,code:'BLOCKED_LIVE'});
  assert.deepEqual(f.writes,[]);
});

for(const [name,mutate] of Object.entries({extra:value=>{value.max_rounds=1;},missing:value=>{delete value.session_token;},
  token:value=>{value.session_token='has whitespace';},version:value=>{value.expected_config_version=true;},
  budget:value=>{value.max_total_usd=1;},duration:value=>{value.valid_for_seconds='120';}}))
  test(`private profile payload rejects ${name}`,async t=>{
    const f=channel(t),value=payload();mutate(value);
    assert.deepEqual(await f.control.request('authorize_profile',value),{ok:false,code:'BLOCKED_LIVE'});
    assert.deepEqual(f.writes,[]);
  });

test('profile lease retains the trusted status through callback and outer authorization',async()=>{
  for(const status of ['authorized','existing']){
    const f=await sessionFixture();let inner;
    f.backend.authorizeProfileModel=async value=>{f.calls.push('profile');f.sent.push(value);return {ok:true,status};};
    const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
      inner=await authorize(lease);
      inner.status=status==='existing'?'authorized':'existing';
      return {ok:true,status:inner.status};
    });
    assert.deepEqual(result,{ok:true,status});
    assert.deepEqual(f.sent,[payload()]);assert.deepEqual(f.calls,['profile']);
  }
});

test('callback success cannot invent a profile acknowledgement or override rejection',async()=>{
  const f=await sessionFixture();
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async()=>({ok:true,status:'existing'})),
    {ok:false,code:'BLOCKED_LIVE'});
  f.backend.authorizeProfileModel=async()=>({ok:false,code:'VERSION_CONFLICT'});
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    assert.deepEqual(await authorize(lease),{ok:false,code:'VERSION_CONFLICT'});return {ok:true,status:'authorized'};
  }),{ok:false,code:'BLOCKED_LIVE'});
  assert.deepEqual(f.calls,[]);
});

for(const failure of ['cancel','throw','navigation','explicit'])test(`existing profile ACK on ${failure} never revokes another grant`,async()=>{
  const f=await sessionFixture();let current=true;
  f.backend.authorizeProfileModel=async()=>{f.calls.push('profile');if(failure==='navigation')current=false;
    return {ok:true,status:'existing'};};
  const result=await f.runtime.withAuthorization(f.backend,()=>current,async lease=>{
    const ack=await authorize(lease);
    if(failure==='throw')throw new Error('synthetic callback failure');
    if(failure==='explicit'){await lease.revoke();return {ok:true,status:'authorized'};}
    return failure==='cancel'?{ok:false,canceled:true}:ack;
  });
  assert.equal(result.ok,false);assert.deepEqual(f.calls,['profile']);
});

test('new profile grant is revoked when post-confirmation guard changes',async()=>{
  const f=await sessionFixture();let current=true;
  f.backend.authorizeProfileModel=async()=>{f.calls.push('profile');current=false;return {ok:true,status:'authorized'};};
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>current,authorize),{ok:false,code:'STATE_CONFLICT'});
  assert.deepEqual(f.calls,['profile','revoke']);assert.deepEqual(f.sent,[{session_token:TOKEN}]);
});

test('profile lease is single use, holds the configuration lock, and snapshots caller data',async()=>{
  const f=await sessionFixture(),gate=deferred();let lease;
  f.backend.authorizeProfileModel=async value=>{f.calls.push('profile');f.sent.push(value);return gate.promise;};
  const value={session_token:TOKEN,basis:basis()};
  const pending=f.runtime.withAuthorization(f.backend,()=>true,async current=>{
    lease=current;assert.equal(typeof lease.authorizeProfile,'function');
    const call=lease.authorizeProfile(value);value.basis.project_intake=false;value.session_token='synthetic_changed';
    assert.equal((await lease.authorize(value)).ok,false);return call;
  });
  await tick();assert.equal((await f.runtime.configure('deepseek-flash')).code,'STATE_CONFLICT');
  assert.deepEqual(f.sent,[payload()]);gate.resolve({ok:true,status:'authorized'});
  assert.deepEqual(await pending,{ok:true,status:'authorized'});
  assert.equal((await lease.authorizeProfile(value)).ok,false);assert.deepEqual(f.calls,['profile']);
});

for(const ack of [{ok:true,status:'pending'},{ok:true,status:'authorized',extra:1},null])
  test(`malformed profile acknowledgement ${JSON.stringify(ack)} stops its captured backend`,async()=>{
    const f=await sessionFixture();f.backend.authorizeProfileModel=async()=>ack;
    assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,authorize)).ok,false);
    assert.deepEqual(f.calls,['stop']);
  });

test('plain and context success shapes remain unchanged',async()=>{
  for(const method of ['authorize','authorizeContext']){
    const f=await sessionFixture();
    assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,
      lease=>lease[method]({session_token:TOKEN,basis:{}})),{ok:true});
  }
});
