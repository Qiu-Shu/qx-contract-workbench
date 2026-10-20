const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createModelSession}=require('../model-session.cjs');
const VERSION='11111111-2222-4333-8444-555555555555';
const TOKEN='synthetic_judge_session';
const basis={request_id:'aaaaaaaa-2222-4333-8444-555555555555',expected_scope:{
  workspace_id:VERSION,conversation_id:VERSION,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:0},expected_composer_revision:0,
  content_sha256:'a'.repeat(64),purpose:'primary_intent'};
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const tick=()=>new Promise(done=>setImmediate(done));
async function fixture({judgeBudget='0.02',configure=true,options={}}={}) {
  const calls=[],failures=[];
  const backend={control:{ready:true,enabled:true,judgeEnabled:true,judgeAuthorizationEnabled:true,
    closed:false,failed:false},closing:false,
    async configureJudge(value){calls.push(['configureJudge',value]);return {ok:true,status:'configured',
      config_sha256:'b'.repeat(64),config_version:VERSION};},
    async disableJudge(){calls.push(['disableJudge']);return {ok:true,status:'disabled'};},
    async authorizeJudge(value){calls.push(['authorizeJudge',value]);return {ok:true,status:'authorized'};},
    async revokeJudge(value){calls.push(['revokeJudge',value]);return {ok:true,status:'revoked'};},
    async authorizeModel(){assert.fail('Judge cannot grant Main authority');},
    async revokeModel(){assert.fail('Judge cannot revoke Main authority');},
    async stop(){calls.push(['stop']);this.closing=true;}};
  let current=backend;
  const constructor={kind:'judge',judgeBudget,store:{async withSecret(fn){await fn('synthetic_judge_key');return {status:'saved'};}},
    getBackend:()=>current,onFailure:value=>failures.push(value),...options};
  const runtime=createModelSession(constructor);
  if(configure)assert.equal((await runtime.configure('jev-1.13.0')).ok,true);
  calls.length=0;
  return {runtime,backend,calls,failures,constructor,replace(value){current=value;}};
}
const names=f=>f.calls.map(value=>value[0]);
const authorize=lease=>lease.authorize({session_token:TOKEN,basis});

test('Judge exposes an optional lease but its default budget cannot grant authority',async()=>{
  const f=await fixture({judgeBudget:undefined});let called=0;
  // Remove the test fixture's explicit budget; the product constructor defaults to closed.
  const options={...f.constructor};delete options.judgeBudget;
  const runtime=createModelSession(options);await runtime.configure('jev-1.13.0');f.calls.length=0;
  assert.equal(typeof runtime.withAuthorization,'function');
  assert.deepEqual(await runtime.withAuthorization(f.backend,()=>true,async lease=>{
    called++;assert.equal(lease,null);return {ok:true};
  }),{ok:true});
  assert.equal(called,1);assert.deepEqual(f.calls,[]);
  assert.equal(runtime.status().runtime.state,'configured');
});

test('trusted synthetic Judge budget and captured configuration use separate authorization methods',async()=>{
  const f=await fixture();let details;
  assert.equal(typeof f.runtime.withAuthorization,'function');
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    details={model:lease.model,max_total_usd:lease.max_total_usd};return authorize(lease);
  }),{ok:true});
  assert.deepEqual(details,{model:'jev-1.13.0',max_total_usd:'0.02'});
  assert.deepEqual(f.calls,[['authorizeJudge',{session_token:TOKEN,expected_config_version:VERSION,
    basis,max_total_usd:'0.02',valid_for_seconds:120}]]);
});

test('Judge budget rejects noncanonical, nonpositive, over-limit and nonstring amounts',()=>{
  for(const judgeBudget of [0.02,0,'', '0','0.0','-1','+1','01','1.0','0.020','1e-2','.02',' 0.02',
    '0.0200000000001','1000000.000000000001','1000001','999999999999999999999999',{},new String('0.02')]){
    assert.throws(()=>createModelSession({kind:'judge',judgeBudget}),{name:'TypeError'},String(judgeBudget));
  }
  assert.throws(()=>createModelSession({judgeBudget:'0.02'}),{name:'TypeError'});
});

test('Judge budget accepts its exact supported boundaries without floating point conversion',async()=>{
  for(const judgeBudget of ['0.000000000001','999999.999999999999','1000000']){
    const f=await fixture({judgeBudget});
    assert.equal(typeof f.runtime.withAuthorization,'function');
    assert.equal((await f.runtime.withAuthorization(f.backend,()=>true,authorize)).ok,true);
    assert.equal(f.calls[0][1].max_total_usd,judgeBudget);
  }
});

test('optional admission failures invoke the callback with null once without changing the backend',async()=>{
  for(const reason of ['null-budget','unconfigured','legacy','missing-authorize','missing-revoke','replaced','guard','failed']){
    const f=await fixture({judgeBudget:reason==='null-budget'?null:'0.02',configure:reason!=='unconfigured'});
    if(reason==='legacy')f.backend.control.judgeAuthorizationEnabled=false;
    if(reason==='missing-authorize')delete f.backend.authorizeJudge;
    if(reason==='missing-revoke')delete f.backend.revokeJudge;
    if(reason==='replaced')f.replace(null);
    if(reason==='failed')f.backend.control.failed=true;
    let called=0;
    assert.equal(typeof f.runtime.withAuthorization,'function');
    assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>reason!=='guard',async lease=>{
      called++;assert.equal(lease,null,reason);return {ok:true};
    }),{ok:true},reason);
    assert.equal(called,1,reason);assert.deepEqual(f.calls,[],reason);
  }
});

test('optional null callback failures are not retried or mistaken for authorization',async()=>{
  const f=await fixture({judgeBudget:null});let called=0;
  assert.equal(typeof f.runtime.withAuthorization,'function');
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    called++;assert.equal(lease,null);throw new Error('synthetic consumer failure');
  }),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(called,1);assert.deepEqual(f.calls,[]);
});

test('an available Judge lease can be declined without disabling the successful Main flow',async()=>{
  const f=await fixture();let called=0;
  assert.equal(typeof f.runtime.withAuthorization,'function');
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    called++;assert.equal(lease.model,'jev-1.13.0');return {ok:true};
  }),{ok:true});
  assert.equal(called,1);assert.deepEqual(f.calls,[]);
});

test('a known Judge denial can continue once without a grant or revocation',async()=>{
  const f=await fixture();let called=0;
  f.backend.authorizeJudge=async()=>{f.calls.push(['authorizeJudge']);return {ok:false,code:'BUDGET_EXCEEDED'};};
  assert.equal(typeof f.runtime.withAuthorization,'function');
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    called++;assert.deepEqual(await authorize(lease),{ok:false,code:'BUDGET_EXCEEDED'});return {ok:true};
  }),{ok:true});
  assert.equal(called,1);assert.deepEqual(names(f),['authorizeJudge']);
});

test('Judge refuses a Main basis or another purpose without dispatching authority',async()=>{
  for(const purpose of [undefined,'material_type','primary_intent ']){
    const f=await fixture();let denial;
    assert.equal(typeof f.runtime.withAuthorization,'function');
    assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
      const supplied={...basis};if(purpose===undefined)delete supplied.purpose;else supplied.purpose=purpose;
      denial=await lease.authorize({session_token:TOKEN,basis:supplied});return {ok:true};
    }),{ok:true});
    assert.equal(denial.ok,false);assert.deepEqual(f.calls,[]);
  }
});

test('an open Judge lease locks configuration and a competing callback only receives null',async()=>{
  const f=await fixture(),gate=deferred();let retained,second=0;
  assert.equal(typeof f.runtime.withAuthorization,'function');
  const pending=f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    retained=lease;await gate.promise;return {ok:false,canceled:true};
  });
  await tick();
  assert.equal((await f.runtime.configure('jev-1.13.0')).code,'STATE_CONFLICT');
  assert.equal((await f.runtime.beforeCredentialChange()).code,'STATE_CONFLICT');
  assert.deepEqual(f.runtime.status().runtime,{state:'unavailable',model:null});
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    second++;assert.equal(lease,null);return {ok:true};
  }),{ok:true});
  assert.equal(second,1);assert.equal(f.runtime.status().runtime.state,'unavailable');
  gate.resolve();assert.equal((await pending).canceled,true);
  assert.equal((await authorize(retained)).ok,false);assert.equal((await retained.revoke()).ok,false);
  assert.deepEqual(f.calls,[]);
});

test('Judge authorization is single-use and captures the original caller values through a late ACK',async()=>{
  const f=await fixture(),gate=deferred();let sent;
  f.backend.authorizeJudge=async value=>{sent=value;f.calls.push(['authorizeJudge']);return gate.promise;};
  const value={session_token:TOKEN,basis:structuredClone(basis)};
  assert.equal(typeof f.runtime.withAuthorization,'function');
  const pending=f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    const flight=lease.authorize(value);
    value.session_token='synthetic_replacement';value.basis.purpose='material_type';
    value.basis.expected_scope.input_revision=42;
    f.constructor.judgeBudget='100';
    assert.equal((await authorize(lease)).ok,false);
    await flight;return {ok:false};
  });
  await tick();gate.resolve({ok:true,status:'authorized'});assert.equal((await pending).ok,false);
  assert.deepEqual(sent,{session_token:TOKEN,expected_config_version:VERSION,basis,max_total_usd:'0.02',valid_for_seconds:120});
  assert.deepEqual(f.calls,[['authorizeJudge'],['revokeJudge',{session_token:TOKEN}]]);
});

test('unknown Judge ACK or control failure stops its captured backend instead of falling back',async()=>{
  for(const problem of ['throw','unknown','extra','failed']){
    const f=await fixture();let called=0;
    f.backend.authorizeJudge=async()=>{
      f.calls.push(['authorizeJudge']);
      if(problem==='throw')throw new Error('synthetic transport');
      if(problem==='failed')f.backend.control.failed=true;
      return problem==='unknown'?{ok:true,status:'unknown'}:problem==='extra'?
        {ok:true,status:'authorized',unexpected:true}:{ok:true,status:'authorized'};
    };
    assert.equal(typeof f.runtime.withAuthorization,'function');
    const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
      called++;assert.equal((await authorize(lease)).ok,false);return {ok:true};
    });
    assert.equal(result.ok,false,problem);assert.equal(called,1);
    assert.deepEqual(names(f),['authorizeJudge','stop']);assert.equal(f.runtime.status().runtime.state,'unavailable');
  }
});

test('post-grant callback failure or cancellation revokes only Judge authority',async()=>{
  for(const failure of ['throw','false','cancel']){
    const f=await fixture();
    assert.equal(typeof f.runtime.withAuthorization,'function');
    const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
      assert.equal((await authorize(lease)).ok,true);
      if(failure==='throw')throw new Error('synthetic consumer');
      return failure==='cancel'?{ok:false,canceled:true}:{ok:false,code:'STATE_CONFLICT'};
    });
    assert.equal(result.ok,false);assert.equal(result.canceled,failure==='cancel'?true:undefined);
    assert.deepEqual(f.calls.map(value=>value[0]),['authorizeJudge','revokeJudge']);
    assert.deepEqual(f.calls[1][1],{session_token:TOKEN});
  }
});

test('late Judge grants after navigation or backend replacement revoke the old session only',async()=>{
  for(const changed of ['guard','backend','capability']){
    const f=await fixture(),gate=deferred();let current=true,newStopped=false;
    f.backend.authorizeJudge=async()=>{f.calls.push(['authorizeJudge']);return gate.promise;};
    assert.equal(typeof f.runtime.withAuthorization,'function');
    const pending=f.runtime.withAuthorization(f.backend,()=>current,authorize);
    await tick();
    if(changed==='guard')current=false;
    if(changed==='backend')f.replace({stop(){newStopped=true;}});
    if(changed==='capability')f.backend.control.judgeAuthorizationEnabled=false;
    gate.resolve({ok:true,status:'authorized'});
    assert.equal((await pending).ok,false);assert.deepEqual(names(f),['authorizeJudge','revokeJudge']);
    assert.equal(newStopped,false);
  }
});

test('existing Judge requests do not invent a new grant to revoke',async()=>{
  for(const okay of [true,false]){
    const f=await fixture();f.backend.authorizeJudge=async()=>{f.calls.push(['authorizeJudge']);return {ok:true,status:'existing'};};
    assert.equal(typeof f.runtime.withAuthorization,'function');
    const result=await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
      assert.equal((await authorize(lease)).ok,true);return {ok:okay};
    });
    assert.equal(result.ok,okay);assert.deepEqual(names(f),['authorizeJudge']);
  }
});

test('failed Judge revocation waits for the owned backend shutdown and keeps its lock',async()=>{
  const f=await fixture(),gate=deferred();let settled=false;
  f.backend.revokeJudge=async()=>{f.calls.push(['revokeJudge']);return {ok:false,code:'BLOCKED_LIVE'};};
  f.backend.stop=async()=>{f.calls.push(['stop']);await gate.promise;f.backend.closing=true;};
  assert.equal(typeof f.runtime.withAuthorization,'function');
  const pending=f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    await authorize(lease);return {ok:false};
  }).then(value=>{settled=true;return value;});
  await tick();assert.equal(settled,false);assert.equal(f.runtime.status().runtime.state,'unavailable');
  assert.equal((await f.runtime.beforeCredentialChange()).code,'STATE_CONFLICT');
  assert.deepEqual(names(f),['authorizeJudge','revokeJudge','stop']);
  gate.resolve();assert.equal((await pending).ok,false);
});

test('an active Judge configuration cannot lend or lose its lock through the optional callback',async()=>{
  const f=await fixture({configure:false}),gate=deferred();let called=0;
  f.backend.configureJudge=async()=>gate.promise;
  const pending=f.runtime.configure('jev-1.13.0');await tick();f.calls.length=0;
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    called++;assert.equal(lease,null);throw new Error('synthetic optional consumer');
  }),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(called,1);assert.equal(f.runtime.status().runtime.state,'unavailable');
  assert.equal((await f.runtime.disable()).code,'STATE_CONFLICT');assert.deepEqual(f.calls,[]);
  gate.resolve({ok:true,status:'configured',config_sha256:'b'.repeat(64),config_version:VERSION});
  assert.equal((await pending).ok,true);assert.equal(f.runtime.status().runtime.state,'configured');
});

test('a callback failure waits for its in-flight Judge grant before revoking once',async()=>{
  const f=await fixture(),gate=deferred();let settled=false;
  f.backend.authorizeJudge=async()=>{f.calls.push(['authorizeJudge']);return gate.promise;};
  const pending=f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    authorize(lease);throw new Error('synthetic early callback failure');
  }).then(value=>{settled=true;return value;});
  await tick();assert.equal(settled,false);assert.deepEqual(names(f),['authorizeJudge']);
  gate.resolve({ok:true,status:'authorized'});assert.equal((await pending).ok,false);
  assert.deepEqual(f.calls,[['authorizeJudge'],['revokeJudge',{session_token:TOKEN}]]);
});

test('explicitly dropping Judge authority allows Main to continue and does not revoke twice',async()=>{
  const f=await fixture();
  assert.deepEqual(await f.runtime.withAuthorization(f.backend,()=>true,async lease=>{
    lease.max_total_usd='1000000';
    assert.equal(lease.max_total_usd,'0.02');
    assert.equal((await authorize(lease)).ok,true);
    assert.deepEqual(await lease.revoke(),{ok:true});
    assert.deepEqual(await lease.revoke(),{ok:true});
    return {ok:true};
  }),{ok:true});
  assert.deepEqual(names(f),['authorizeJudge','revokeJudge']);
  assert.equal(f.calls[0][1].max_total_usd,'0.02');
});
