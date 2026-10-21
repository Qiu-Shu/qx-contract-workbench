const MODELS=new Map([
  ['deepseek-flash',['0.3','1.2']],
  ['deepseek-v4-pro',['1.32','3.96']]
]);
const CREDENTIAL_CODES=new Set(['CREDENTIAL_INPUT_INVALID','CREDENTIAL_PATH_UNSAFE','CREDENTIAL_CORRUPT',
  'CREDENTIAL_STORAGE_UNAVAILABLE','CREDENTIAL_STORAGE_FAILED','CREDENTIAL_ROTATION_REQUIRED']);
const CONTROL_CODES=new Set(['BLOCKED_LIVE','VERSION_CONFLICT','STATE_CONFLICT',
  'BUDGET_EXCEEDED','CROSS_MATTER_DENIED']);
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const exact=(value,fields)=>value && typeof value==='object' && !Array.isArray(value) &&
  Object.keys(value).length===fields.length && fields.every(field=>Object.hasOwn(value,field));
const check=guard=>{try{return guard()===true;}catch{return false;}};
const okay=()=>({ok:true});
const rejected=(code='BLOCKED_LIVE')=>({ok:false,code});

function configuration(model) {
  const [input,output]=MODELS.get(model);
  return {enabled:true,protocol_version:'deepseek-chat-json-v1',provider:'deepseek',model,
    max_input_bytes:65536,max_output_tokens:4096,max_response_bytes:1048576,timeout_seconds:30,
    input_usd_per_million:input,output_usd_per_million:output,
    price_reference:'https://api-docs.deepseek.com/quick_start/pricing/ (2026-10-19; peak/cache-miss; USD)'};
}

function reservation(model) {
  const cents=value=>BigInt(value.split('.')[0])*100n+BigInt((value.split('.')[1] || '').padEnd(2,'0'));
  const [input,output]=MODELS.get(model);
  const amount=65536n*cents(input)+4096n*cents(output);
  const digits=amount.toString().padStart(9,'0');
  return digits.slice(0,-8)+'.'+digits.slice(-8).replace(/0+$/,'');
}

function createModelSession({store,getBackend,onFailure=()=>{},kind='main',judgeBudget=null}) {
  if(!['main','judge'].includes(kind))throw new TypeError('MODEL_KIND_INVALID');
  const judge=kind==='judge',configureMethod=judge?'configureJudge':'configureModel',disableMethod=judge?'disableJudge':'disableModel';
  if(judgeBudget!==null && (!judge || typeof judgeBudget!=='string' || judgeBudget==='0' ||
      !/^(?:(?:0|[1-9]\d{0,5})(?:\.\d{0,11}[1-9])?|1000000)$/.test(judgeBudget)))
    throw new TypeError('JUDGE_BUDGET_INVALID');
  const authorizeMethod=judge?'authorizeJudge':'authorizeModel',revokeMethod=judge?'revokeJudge':'revokeModel';
  const supports=backend=>!judge || backend?.control?.judgeEnabled===true;
  const allowedModel=model=>typeof model==='string' && (judge?model==='jev-1.13.0':MODELS.has(model));
  const configured=model=>judge?{enabled:true,protocol_version:'typesafe-systemone-v1',model:'jev-1.13.0',
    max_input_bytes:65536,max_response_bytes:262144,timeout_ms:2000}:configuration(model);
  let metadata=null,active=false,unsafe=false;
  const retired=new WeakSet();
  const current=()=>{try{return getBackend() || null;}catch{return null;}};
  const healthy=backend=>Boolean(backend && typeof backend[configureMethod]==='function' &&
    typeof backend[disableMethod]==='function' && supports(backend) && typeof backend.stop==='function' && !backend.closing &&
    (!backend.control || (backend.control.ready && backend.control.enabled &&
      !backend.control.closed && !backend.control.failed)));
  function view() {
    const backend=current();
    if(metadata && metadata.backend!==backend)metadata=null;
    if(unsafe || !healthy(backend) || retired.has(backend))return {state:'unavailable',model:null};
    return metadata ? {state:'configured',model:metadata.model} : {state:'unconfigured',model:null};
  }
  const matches=(backend,guard)=>!unsafe && !retired.has(backend) && healthy(backend) &&
    current()===backend && check(guard);
  const forget=backend=>{if(metadata?.backend===backend)metadata=null;};
  async function terminate(backend,guard) {
    forget(backend);retired.add(backend);
    try{await backend.stop();}catch{unsafe=true;}
    // An obsolete document cannot navigate a newly opened page to its error state.
    if(check(guard))try{await onFailure(backend);}catch{}
    return rejected();
  }
  async function clear(backend,guard) {
    let result;
    try{result=await backend[disableMethod]();}catch{return terminate(backend,guard);}
    if(!exact(result,['ok','status']) || result.ok!==true || result.status!=='disabled')
      return terminate(backend,guard);
    forget(backend);
    if(!healthy(backend))return terminate(backend,guard);
    return matches(backend,guard) ? okay() : rejected('STATE_CONFLICT');
  }
  async function run(operation) {
    if(active)return {ok:false,runtime:{state:'unavailable',model:null},code:'STATE_CONFLICT'};
    active=true;
    let result;
    try{result=await operation();}catch{result=rejected();}
    finally{active=false;}
    return {...result,runtime:view()};
  }
  const disable=(guard=()=>true)=>run(async()=>{
    if(!check(guard))return rejected('STATE_CONFLICT');
    if(unsafe)return rejected();
    const backend=current();
    if(!backend){metadata=null;return okay();}
    // A legacy child has never accepted Judge authority; saving its future credential need not stop Main.
    if(judge && !supports(backend) && !backend.closing && backend.control?.ready &&
        backend.control.enabled && !backend.control.closed && !backend.control.failed){metadata=null;return okay();}
    if(!healthy(backend) || retired.has(backend))return terminate(backend,guard);
    return clear(backend,guard);
  });
  async function withAuthorization(backend,guard,callback) {
    const captured=metadata;
    const supportsAuthorization=()=>!judge || (judgeBudget!==null && backend?.control?.judgeAuthorizationEnabled===true);
    if(active || !captured || captured.backend!==backend || !matches(backend,guard) ||
        !supportsAuthorization() || typeof backend[authorizeMethod]!=='function' || typeof backend[revokeMethod]!=='function'){
      if(!judge)return rejected(active?'STATE_CONFLICT':'BLOCKED_LIVE');
      try{return await callback(null);}catch{return rejected();}
    }
    active=true;
    let open=true,used=false,authorized=false,grantedToken=null,flight=null;
    const budget=judge?judgeBudget:reservation(captured.model);
    const valid=()=>open && metadata===captured && matches(backend,guard) && supportsAuthorization();
    async function revoke() {
      if(!grantedToken)return okay();
      const token=grantedToken;grantedToken=null;
      try{
        const ack=await backend[revokeMethod]({session_token:token});
        if(exact(ack,['ok','status']) && ack.ok===true && ack.status==='revoked' && healthy(backend))return okay();
      }catch{}
      return terminate(backend,guard);
    }
    const lease=Object.freeze({model:captured.model,max_total_usd:budget,
      authorize(value){
        if(used || !valid())return Promise.resolve(rejected('STATE_CONFLICT'));
        used=true;
        if(judge){
          try{value=structuredClone(value);}catch{return Promise.resolve(rejected());}
          if(value?.basis?.purpose!=='primary_intent')return Promise.resolve(rejected());
        }
        flight=(async()=>{
          let ack;
          try{
            ack=await backend[authorizeMethod]({session_token:value.session_token,
              expected_config_version:captured.config_version,basis:value.basis,
              max_total_usd:budget,valid_for_seconds:120});
          }catch{return terminate(backend,guard);}
          if(!healthy(backend))return terminate(backend,guard);
          if(exact(ack,['ok','code']) && ack.ok===false && CONTROL_CODES.has(ack.code))return rejected(ack.code);
          if(!exact(ack,['ok','status']) || ack.ok!==true || !['authorized','existing'].includes(ack.status))
            return terminate(backend,guard);
          authorized=true;
          if(ack.status==='authorized')grantedToken=value.session_token;
          if(!valid()){await revoke();return rejected('STATE_CONFLICT');}
          return okay();
        })();
        return flight;
      },
      authorizeContext(value){
        // One single-round library-context grant; the basis bytes were rebuilt by the server preview.
        if(judge || used || !valid() || typeof backend.authorizeContextModel!=='function')
          return Promise.resolve(rejected(judge?'BLOCKED_LIVE':'STATE_CONFLICT'));
        used=true;
        flight=(async()=>{
          let ack;
          try{
            ack=await backend.authorizeContextModel({session_token:value.session_token,
              expected_config_version:captured.config_version,basis:value.basis,
              max_total_usd:budget,valid_for_seconds:120,max_rounds:1});
          }catch{return terminate(backend,guard);}
          if(!healthy(backend))return terminate(backend,guard);
          if(exact(ack,['ok','code']) && ack.ok===false && CONTROL_CODES.has(ack.code))return rejected(ack.code);
          if(!exact(ack,['ok','status']) || ack.ok!==true || !['authorized','existing'].includes(ack.status))
            return terminate(backend,guard);
          authorized=true;
          if(ack.status==='authorized')grantedToken=value.session_token;
          if(!valid()){await revoke();return rejected('STATE_CONFLICT');}
          return okay();
        })();
        return flight;
      },
      async revoke(){
        if(!open)return rejected('STATE_CONFLICT');
        if(flight)await flight;
        authorized=false;return revoke();
      }});
    let result;
    try{
      result=await callback(lease);
      if(flight)await flight;
      if(!valid())result=rejected('STATE_CONFLICT');
      if(result?.ok!==true || (!judge && !authorized)){
        await revoke();
        return result?.canceled===true ? {ok:false,code:'APPROVAL_CANCELED',canceled:true} :
          rejected(CONTROL_CODES.has(result?.code)?result.code:'BLOCKED_LIVE');
      }
      return okay();
    }catch{
      if(flight)await flight;
      await revoke();return rejected();
    }finally{open=false;active=false;}
  }
  return Object.freeze({
    status:()=>({ok:true,runtime:active ? {state:'unavailable',model:null} : view()}),
    configure:(model,guard=()=>true)=>run(async()=>{
      if(!check(guard))return rejected('STATE_CONFLICT');
      const backend=current();
      if(unsafe || !healthy(backend) || retired.has(backend))return rejected();
      // Clear known old authority even if reading the replacement credential fails.
      const cleared=await clear(backend,guard);
      if(!cleared.ok)return cleared;
      if(!allowedModel(model))return rejected();
      let attempted=false,ack,credential,stale=false;
      try{
        credential=await store.withSecret(async secret=>{
          if(!matches(backend,guard)){stale=true;return;}
          attempted=true;
          ack=await backend[configureMethod]({config:configured(model),secret});
        });
      }catch{
        if(attempted)return terminate(backend,guard);
        return rejected('CREDENTIAL_STORAGE_FAILED');
      }
      if(stale)return rejected('STATE_CONFLICT');
      if(!attempted)return rejected(CREDENTIAL_CODES.has(credential?.code) ? credential.code : 'BLOCKED_LIVE');
      if(!exact(credential,['status']) || credential.status!=='saved')return terminate(backend,guard);
      if(!matches(backend,guard)){
        await terminate(backend,guard);return rejected('STATE_CONFLICT');
      }
      if(exact(ack,['ok','code']) && ack.ok===false)
        return rejected(CONTROL_CODES.has(ack.code) ? ack.code : 'BLOCKED_LIVE');
      if(!exact(ack,['ok','status','config_sha256','config_version']) || ack.ok!==true ||
          ack.status!=='configured' || typeof ack.config_sha256!=='string' ||
          !/^[0-9a-f]{64}$/.test(ack.config_sha256) || typeof ack.config_version!=='string' ||
          !UUID.test(ack.config_version))return terminate(backend,guard);
      metadata={backend,model,config_sha256:ack.config_sha256,config_version:ack.config_version};
      return okay();
    }),
    disable,
    beforeCredentialChange:disable,
    withAuthorization
  });
}

module.exports={createModelSession};
