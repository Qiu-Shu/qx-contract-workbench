// Independent synthetic session-boundary probes; no Electron or provider request.
const assert=require('node:assert/strict');
const path=require('node:path');
const {createModelSession}=require(path.join(process.cwd(),'desktop/model-session.cjs'));
const id='11111111-2222-4333-8444-555555555555';
const basis={request_id:id,expected_scope:{workspace_id:id,conversation_id:id,
  scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0},
  expected_composer_revision:0,content_sha256:'a'.repeat(64),purpose:'primary_intent'};
const gates=()=>{let resolve;return {promise:new Promise(done=>resolve=done),resolve};};
async function fixture(budget){
  const calls=[];
  const old={control:{ready:true,enabled:true,judgeEnabled:true,judgeAuthorizationEnabled:true},closing:false,
    async configureJudge(){return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:id};},
    async disableJudge(){return {ok:true,status:'disabled'};},
    async authorizeJudge(){calls.push('authorize');return {ok:true,status:'authorized'};},
    async revokeJudge(){calls.push('revoke');return {ok:true,status:'revoked'};},
    async stop(){calls.push('stop-old');this.closing=true;}};
  let current=old;
  const runtime=createModelSession({kind:'judge',judgeBudget:budget,getBackend:()=>current,
    store:{async withSecret(consume){await consume('synthetic-probe-key');return {status:'saved'};}}});
  await runtime.configure('jev-1.13.0');
  return {runtime,old,calls,replace(value){current=value;}};
}
(async()=>{
  const reports=[];
  {
    const f=await fixture(null);let callbacks=0;
    const result=await f.runtime.withAuthorization(f.old,()=>true,async lease=>{
      callbacks++;assert.equal(lease,null);return {ok:true};
    });
    assert.deepEqual(result,{ok:true});assert.equal(callbacks,1);assert.deepEqual(f.calls,[]);
    reports.push({case:'default-closed-budget',callbacks,result,calls:f.calls});
  }
  for(const outcome of ['known-denial','unknown-ack']){
    const f=await fixture('0.02'),gate=gates();let callbacks=0;
    f.old.authorizeJudge=async()=>{f.calls.push('authorize');return gate.promise;};
    const resultPromise=f.runtime.withAuthorization(f.old,()=>true,async lease=>{
      callbacks++;void lease.authorize({session_token:'synthetic-session',basis});return {ok:true};
    });
    gate.resolve(outcome==='known-denial'?{ok:false,code:'STATE_CONFLICT'}:{ok:true,status:'unrecognized'});
    const result=await resultPromise;
    assert.equal(result.ok,outcome==='known-denial');assert.equal(callbacks,1);
    assert.deepEqual(f.calls,outcome==='known-denial'?['authorize']:['authorize','stop-old']);
    reports.push({case:'unawaited-'+outcome,callbacks,result,calls:f.calls});
  }
  {
    const f=await fixture('0.02'),gate=gates();
    f.old.authorizeJudge=async()=>{f.calls.push('authorize');return gate.promise;};
    const resultPromise=f.runtime.withAuthorization(f.old,()=>true,async lease=>{
      return lease.authorize({session_token:'synthetic-session',basis});
    });
    f.replace({stop(){f.calls.push('stop-new');}});
    gate.resolve({ok:true,status:'authorized'});
    const result=await resultPromise;
    assert.equal(result.ok,false);assert.deepEqual(f.calls,['authorize','revoke']);
    reports.push({case:'late-ack-replacement',result,calls:f.calls});
  }
  console.log(JSON.stringify({independent_probe_count:reports.length,reports},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
