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

function createModelSession({store,getBackend,onFailure=()=>{}}) {
  let metadata=null,active=false,unsafe=false;
  const retired=new WeakSet();
  const current=()=>{try{return getBackend() || null;}catch{return null;}};
  const healthy=backend=>Boolean(backend && typeof backend.configureModel==='function' &&
    typeof backend.disableModel==='function' && typeof backend.stop==='function' && !backend.closing &&
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
    try{result=await backend.disableModel();}catch{return terminate(backend,guard);}
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
    if(!healthy(backend) || retired.has(backend))return terminate(backend,guard);
    return clear(backend,guard);
  });
  return Object.freeze({
    status:()=>({ok:true,runtime:active ? {state:'unavailable',model:null} : view()}),
    configure:(model,guard=()=>true)=>run(async()=>{
      if(!check(guard))return rejected('STATE_CONFLICT');
      const backend=current();
      if(unsafe || !healthy(backend) || retired.has(backend))return rejected();
      // Clear known old authority even if reading the replacement credential fails.
      const cleared=await clear(backend,guard);
      if(!cleared.ok)return cleared;
      if(typeof model!=='string' || !MODELS.has(model))return rejected();
      let attempted=false,ack,credential,stale=false;
      try{
        credential=await store.withSecret(async secret=>{
          if(!matches(backend,guard)){stale=true;return;}
          attempted=true;
          ack=await backend.configureModel({config:configuration(model),secret});
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
    beforeCredentialChange:disable
  });
}

module.exports={createModelSession};
