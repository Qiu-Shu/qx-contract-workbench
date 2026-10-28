const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createModelSession}=require('../model-session.cjs');
const VERSION='11111111-2222-4333-8444-555555555555';
const TOKEN='synthetic_session_token';
const basis={request_id:'aaaaaaaa-2222-4333-8444-555555555555',expected_scope:{},
  expected_composer_revision:0,content_sha256:'a'.repeat(64)};
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const tick=()=>new Promise(done=>setImmediate(done));
async function fixture(model='deepseek-flash') {
  const calls=[];let authorized;
  const backend={control:{ready:true,enabled:true,closed:false,failed:false},closing:false,
    async configureModel(){return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:VERSION};},
    async disableModel(){calls.push('disable');return {ok:true,status:'disabled'};},
    async authorizeModel(value){calls.push('authorize');authorized=value;return {ok:true,status:'authorized'};},
    async revokeModel(){calls.push('revoke');return {ok:true,status:'revoked'};},
    async stop(){calls.push('stop');this.closing=true;}};
  let current=backend;
  const runtime=createModelSession({store:{async withSecret(fn){await fn('synthetic_secret');return {status:'saved'};}},
    getBackend:()=>current});
  await runtime.configure(model);calls.length=0;
  return {runtime,backend,calls,get authorized(){return authorized;},replace(value){current=value;}};
}
test('trusted authorization binds the private config version and exact bounded cost',async()=>{
  const f=await fixture();let details;
  const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    details={model:lease.model,max_total_usd:lease.max_total_usd};
    return lease.authorize({session_token:TOKEN,basis});
  });
  assert.deepEqual(result,{ok:true});
  assert.deepEqual(details,{model:'deepseek-flash',max_total_usd:'0.024576'});
  assert.equal(f.authorized.expected_config_version,VERSION);
  assert.equal(f.authorized.valid_for_seconds,120);
  assert.equal(f.authorized.max_total_usd,'0.024576');
  assert.equal(f.authorized.session_token===TOKEN,true);
  assert.deepEqual(f.calls,['authorize']);
});

test('the pro model uses an exact eight-place reservation without floating-point rounding',async()=>{
  const f=await fixture('deepseek-v4-pro');
  await f.runtime.withAuthorization(f.backend,()=>true,lease=>lease.authorize({session_token:TOKEN,basis}));
  assert.equal(f.authorized.max_total_usd,'0.10272768');
});

test('the longer Pro timeout still uses one lease and cancellation revokes without a second call',async()=>{
  const f=await fixture('deepseek-v4-pro');let retained;
  const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    retained=lease;
    assert.equal((await lease.authorize({session_token:TOKEN,basis})).ok,true);
    assert.equal((await lease.authorize({session_token:TOKEN,basis})).ok,false);
    return {ok:false,canceled:true};
  });
  assert.deepEqual(result,{ok:false,code:'APPROVAL_CANCELED',canceled:true});
  assert.equal(f.authorized.valid_for_seconds,120);
  assert.deepEqual(f.calls,['authorize','revoke']);
  assert.equal((await retained.authorize({session_token:TOKEN,basis})).ok,false);
  assert.deepEqual(f.calls,['authorize','revoke']);
});

test('the longer Pro timeout never retries an unknown authorization acknowledgement',async()=>{
  const f=await fixture('deepseek-v4-pro');
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');return {ok:true,status:'unknown'};};
  assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,
    lease=>lease.authorize({session_token:TOKEN,basis}))).ok,false);
  assert.deepEqual(f.calls,['authorize','stop']);
});

test('confirmation holds the config lock and a retained lease cannot authorize later',async()=>{
  const f=await fixture(),gate=deferred();let lease;
  const pending=f.runtime.withAuthorization(f.backend,()=>true,async value=>{lease=value;await gate.promise;return {ok:false,canceled:true};});
  await tick();
  assert.equal((await f.runtime.configure('deepseek-v4-pro')).code,'STATE_CONFLICT');
  assert.equal((await f.runtime.beforeCredentialChange()).code,'STATE_CONFLICT');
  assert.deepEqual(f.runtime.status().runtime,{state:'unavailable',model:null});
  gate.resolve();assert.equal((await pending).canceled,true);
  assert.equal((await lease.authorize({session_token:TOKEN,basis})).ok,false);
  assert.deepEqual(f.calls,[]);
});

test('a lease is single use and does not accept a second request basis',async()=>{
  const f=await fixture();let second;
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    const first=await lease.authorize({session_token:TOKEN,basis});
    second=await lease.authorize({session_token:TOKEN,basis:{...basis,request_id:VERSION}});
    return first;
  }),{ok:true});
  assert.equal(second.ok,false);assert.deepEqual(f.calls,['authorize']);
});

test('configuration loss before opening the trusted transaction rejects without executing the callback',async()=>{
  const f=await fixture();f.replace(null);
  let called=false;
  assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,async()=>{called=true;})).ok,false);
  assert.equal(called,false);assert.deepEqual(f.calls,[]);
});

test('an acknowledged grant whose document changed is revoked for the captured session',async()=>{
  const f=await fixture();let current=true,revoked;
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');current=false;return {ok:true,status:'authorized'};};
  f.backend.revokeModel=async value=>{f.calls.push('revoke');revoked=value;return {ok:true,status:'revoked'};};
  assert.equal((await f.runtime.withAuthorization(f.backend,()=>current,
    lease=>lease.authorize({session_token:TOKEN,basis}))).ok,false);
  assert.equal(revoked.session_token===TOKEN,true);assert.deepEqual(f.calls,['authorize','revoke']);
});

test('ambiguous authorization stops its backend without attempting automatic authorization again',async()=>{
  const f=await fixture();
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');throw new Error('synthetic transport failure');};
  assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,
    lease=>lease.authorize({session_token:TOKEN,basis}))).ok,false);
  assert.deepEqual(f.calls,['authorize','stop']);
  assert.equal(f.runtime.status().runtime.state,'unavailable');
});

test('unknown ACK and ACK plus terminal control failure both close the backend',async()=>{
  for(const unhealthy of [false,true]){
    const f=await fixture();
    f.backend.authorizeModel=async()=>{
      f.backend.control.failed=unhealthy;
      return unhealthy ? {ok:true,status:'authorized'} : {ok:true,status:'unexpected'};
    };
    assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,
      lease=>lease.authorize({session_token:TOKEN,basis}))).ok,false);
    assert.deepEqual(f.calls,['stop']);
  }
});

test('a confirmed authorization denial is never mistaken for consumer success',async()=>{
  const f=await fixture();f.backend.authorizeModel=async()=>({ok:false,code:'VERSION_CONFLICT'});
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,
    lease=>lease.authorize({session_token:TOKEN,basis})),{ok:false,code:'VERSION_CONFLICT'});
  assert.deepEqual(f.calls,[]);
});

test('a failed post-grant verification revokes and a denied revoke waits for owned backend shutdown',async()=>{
  const f=await fixture(),gate=deferred();let settled=false;
  f.backend.revokeModel=async()=>{f.calls.push('revoke');return {ok:false,code:'BLOCKED_LIVE'};};
  f.backend.stop=async()=>{f.calls.push('stop');await gate.promise;f.backend.closing=true;};
  const pending=f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    await lease.authorize({session_token:TOKEN,basis});throw new Error('synthetic changed cookie');
  }).then(value=>{settled=true;return value;});
  await tick();assert.equal(settled,false);assert.deepEqual(f.calls,['authorize','revoke','stop']);
  gate.resolve();assert.equal((await pending).ok,false);
});

test('existing request acknowledgement is accepted without a new authorization capability',async()=>{
  const f=await fixture();f.backend.authorizeModel=async()=>({ok:true,status:'existing'});
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,
    lease=>lease.authorize({session_token:TOKEN,basis})),{ok:true});
  assert.deepEqual(f.calls,[]);
});

test('a late authorization on a replaced backend revokes the old session only',async()=>{
  const f=await fixture(),gate=deferred();let newStopped=false;
  f.backend.authorizeModel=async()=>{f.calls.push('authorize');return gate.promise;};
  const pending=f.runtime.withAuthorization(f.backend,()=>true,
    lease=>lease.authorize({session_token:TOKEN,basis}));
  await tick();f.replace({stop:async()=>{newStopped=true;}});gate.resolve({ok:true,status:'authorized'});
  assert.equal((await pending).ok,false);assert.deepEqual(f.calls,['authorize','revoke']);assert.equal(newStopped,false);
});

test('failed post-grant verification plus a malformed revoke ACK closes the captured backend',async()=>{
  const f=await fixture();f.backend.revokeModel=async()=>{f.calls.push('revoke');return {ok:true,status:'unknown'};};
  assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    await lease.authorize({session_token:TOKEN,basis});return {ok:false,code:'STATE_CONFLICT'};
  })).ok,false);
  assert.deepEqual(f.calls,['authorize','revoke','stop']);
});
