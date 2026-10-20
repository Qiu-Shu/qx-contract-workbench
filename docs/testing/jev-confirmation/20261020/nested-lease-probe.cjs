// Read-only composition probe: two existing lease owners, synthetic in-memory ACKs.
const assert=require('node:assert/strict');
const path=require('node:path');
const {createModelSession}=require(path.join(process.cwd(),'desktop/model-session.cjs'));
const grants=new Set(),calls=[];
const backend={control:{ready:true,enabled:true,closed:false,failed:false},closing:false,
  async configureModel(){return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'11111111-2222-4333-8444-555555555555'};},
  async disableModel(){return {ok:true,status:'disabled'};},
  async authorizeModel(value){grants.add(value.session_token);calls.push('grant '+value.session_token);return {ok:true,status:'authorized'};},
  async revokeModel(value){grants.delete(value.session_token);calls.push('revoke '+value.session_token);return {ok:true,status:'revoked'};},
  async stop(){grants.clear();calls.push('stop');this.closing=true;}};
const options={getBackend:()=>backend,store:{async withSecret(fn){await fn('synthetic_secret');return {status:'saved'};}}};
(async()=>{
  const outer=createModelSession(options),inner=createModelSession(options);
  await outer.configure('deepseek-flash');await inner.configure('deepseek-flash');
  let armed=false;
  const guard=()=>!armed || inner.status().runtime.state==='unavailable';
  const result=await outer.withAuthorization(backend,guard,async main=>{
    await main.authorize({session_token:'synthetic_main',basis:{}});
    return inner.withAuthorization(backend,()=>true,async judge=>{
      const approved=await judge.authorize({session_token:'synthetic_inner',basis:{}});
      armed=true;return approved;
    });
  });
  assert.equal(result.ok,false);assert.deepEqual([...grants],['synthetic_inner']);
  console.log(JSON.stringify({probe:'nested-lease-outer-final-guard-failure',result,calls,
    remainingGrantCount:grants.size,limitation:'Synthetic guard transition and in-memory ACKs; not evidence of an ordinary Electron event-loop race.'},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
