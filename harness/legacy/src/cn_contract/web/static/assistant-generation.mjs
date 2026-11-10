// Registration, draft persistence and receipt reads have separate outcomes.
const scopeKeys = ['workspace_id','conversation_id','scope_kind','scope_ref',
  'binding_revision','input_revision','materials_revision'];
const sameScope = (left,right) => scopeKeys.every(key=>left?.[key]===right?.[key]);
const sameConversation = (left,right) => Boolean(left?.conversation_id &&
  scopeKeys.slice(0,5).every(key=>left[key]===right?.[key]));
const active = attempt => ['reserved','sending'].includes(attempt.state);
const errorValue = error => ({code:error?.code || 'REQUEST_FAILED',status:error?.status || 0});
const invalid = () => Object.assign(new Error('Invalid generation response'),{code:'INVALID_RESPONSE',status:0});
export const isAuthorizationError = error => error?.status===401 || (error?.status===403 &&
  ['AUTHORIZATION_REQUIRED','CROSS_MATTER_DENIED'].includes(error.code));

async function digest(text) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))]
    .map(value=>value.toString(16).padStart(2,'0')).join('');
}

export function createGenerationController(api,host) {
  const {state,readonly,uuid,notify,nativeAuthorization,nativeProfileAuthorization}=host;
  const profileMode=typeof nativeProfileAuthorization==='function' &&
    typeof api.submitProfilePreview==='function' && typeof api.submitProfileGeneration==='function';
  const nativeConfirmation=profileMode || typeof nativeAuthorization==='function';
  let epoch=0, edits=0, work=null, workKind=null, pending=null, capabilityBasis=null;
  const initial=()=>({phase:'idle',capability:null,canSend:false,items:[],error:null,nativeConfirmation,profileMode});
  state.generation=initial();
  const available = () => api.getGenerationCapability &&
    (profileMode?api.submitProfileGeneration:api.submitGeneration) && api.findGenerationRequest;
  const token = () => ({epoch,host:host.token()});
  const current = value => value.epoch===epoch && host.current(value.host);
  const allowed = () => !readonly && !state.loading && state.status!=='revoked' && !state.conflict &&
    !state.skill && !state.materials?.items?.length && Boolean(state.text.trim()) && !host.blocked() &&
    (!profileMode || !state.materials?.attachments?.length && !state.context?.selected?.length &&
      (!state.view?.latest_run || ['completed','cancelled','failed','interrupted','blocked'].includes(state.view.latest_run.state)));
  const basis = () => ({scope:{...state.view?.scope},revision:state.view?.composer_revision,text:state.savedText,edits});
  const sameBasis = value => value && edits===value.edits && state.text===value.text &&
    state.savedText===value.text && state.view?.composer_revision===value.revision && sameScope(value.scope,state.view?.scope);
  const tracking = () => state.generation.items.some(item=>active(item.attempt));
  const sendable = cap => cap?.state==='ready' || nativeConfirmation &&
    ['unapproved','budget_exhausted'].includes(cap?.state);

  function sync() {
    if(capabilityBasis && !sameBasis(capabilityBasis)) {
      capabilityBasis=null;state.generation.capability=null;
    }
    state.generation.canSend=Boolean(available() && !work && !pending && allowed() &&
      sameBasis(capabilityBasis) && sendable(state.generation.capability));
  }
  function reset() {
    epoch++;work=null;workKind=null;pending=null;capabilityBasis=null;
    state.generation=initial();
  }
  function changed() {
    edits++;capabilityBasis=null;state.generation.capability=null;state.generation.canSend=false;
  }
  function failed(error,value) {
    if(!current(value))return false;
    if(isAuthorizationError(error))return host.fail(error,value.host);
    capabilityBasis=null;state.generation.capability=null;state.generation.canSend=false;
    state.generation.error=errorValue(error);
    state.generation.phase=pending && !pending.result?'unknown':'error';
    notify();return false;
  }
  function run(action,kind='read') {
    if(work)return work;
    const value=token();
    const task=Promise.resolve().then(()=>action(value)).catch(error=>failed(error,value)).finally(()=>{
      if(work===task) {work=null;workKind=null;}
      if(current(value)) {
        if(['checking','confirming','submitting'].includes(state.generation.phase))state.generation.phase=
          pending?(pending.result?'tracking':'unknown'):(tracking()?'tracking':'idle');
        notify();
      }
    });
    work=task;workKind=kind;notify();return task;
  }
  async function capability(value) {
    const stamp=basis(),id=state.id;
    const [cap,hash]=await Promise.all([api.getGenerationCapability(id),digest(stamp.text)]);
    if(!current(value) || id!==state.id)return null;
    if(!cap || cap.basis!=='saved_draft' || !sameScope(cap.scope,stamp.scope) ||
        cap.composer_revision!==stamp.revision || cap.content_sha256!==(stamp.text.trim()?hash:null))throw invalid();
    if(!sameBasis(stamp))return null;
    capabilityBasis=stamp;state.generation.capability=cap;return cap;
  }
  function checkedAttempt(attempt,scope) {
    if(!attempt?.id || !attempt.run_id || !sameConversation(attempt.scope,scope))throw invalid();
    if(attempt.output && (!sameConversation(attempt.output.scope,scope) || attempt.output.run_id!==attempt.run_id))throw invalid();
    return attempt;
  }
  function checkedRegistration(attempt,body) {
    checkedAttempt(attempt,body.expected_scope);
    if(!sameScope(attempt.scope,{...body.expected_scope,input_revision:body.expected_scope.input_revision+1}) ||
        body.project_intake===true && attempt.input_format!=='profile-text-v1')throw invalid();
    return attempt;
  }
  function checkedProfilePreview(preview,selection,hash) {
    const fields=['input_format','template_version','purpose','handler_id','handler_version','request_id',
      'expected_scope','expected_composer_revision','content_sha256','base_profile_revision','expected_intake_id',
      'expected_intake_revision','project_intake','system_sha256','config_sha256','wire_sha256','wire_bytes'];
    const integer=(value,min=0)=>Number.isSafeInteger(value) && value>=min;
    const uuidValue=value=>typeof value==='string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
    if(!preview || Object.keys(preview).length!==fields.length || !fields.every(field=>Object.hasOwn(preview,field)) ||
        preview.input_format!=='profile-text-v1' || preview.template_version!=='profile-text-system-v1' ||
        preview.purpose!=='reply_and_profile_draft' || preview.handler_id!=='profile.save' || preview.handler_version!=='1' ||
        preview.request_id!==selection.request_id || !sameScope(preview.expected_scope,selection.expected_scope) ||
        preview.expected_composer_revision!==selection.expected_composer_revision || preview.content_sha256!==hash ||
        preview.project_intake!==true || !integer(preview.base_profile_revision) || !integer(preview.wire_bytes,1) ||
        preview.wire_bytes>262144 || !['system_sha256','config_sha256','wire_sha256'].every(field=>
          typeof preview[field]==='string' && /^[0-9a-f]{64}$/.test(preview[field])) ||
        (preview.expected_intake_id===null ? preview.expected_intake_revision!==null :
          !uuidValue(preview.expected_intake_id) || !integer(preview.expected_intake_revision,1)) ||
        selection.expected_scope.scope_kind==='intake' && preview.expected_intake_id!==selection.expected_scope.scope_ref)
      throw invalid();
  }
  async function history(value) {
    const view=state.view,id=state.id;
    const ids=[...new Set(view.messages.map(message=>message.id))],found=[];
    if(!api.getGenerationHistory)return true;
    for(let offset=0;offset<ids.length;offset+=50) {
      const batch=ids.slice(offset,offset+50),result=await api.getGenerationHistory(id,batch);
      if(!current(value) || id!==state.id || !sameScope(view.scope,state.view?.scope))return false;
      if(!sameScope(result?.scope,view.scope) || !Array.isArray(result.items))throw invalid();
      const seen=new Set();
      for(const item of result.items) {
        if(!batch.includes(item.message_id) || seen.has(item.message_id))throw invalid();
        seen.add(item.message_id);checkedAttempt(item.attempt,view.scope);found.push(item);
      }
    }
    if(!current(value) || id!==state.id || !sameScope(view.scope,state.view?.scope))return false;
    // A page appended during these reads needs its own authorized history read.
    if(ids.join(',')!==[...new Set(state.view.messages.map(message=>message.id))].join(','))return false;
    state.generation.items=found;return true;
  }
  async function acknowledged(value) {
    const action=pending;
    if(!action.result) {
      const result=await api.findGenerationRequest(action.id,action.body.request_id);
      if(!current(value))return false;
      if(!result) {state.generation.phase='unknown';notify();return false;}
      action.result=checkedRegistration(result,action.body);
    }
    const attempt=checkedRegistration(action.result,action.body);
    host.accept(action.body,attempt,edits===action.edits && state.text===action.body.content);
    // Once registration is proven, readback failures must not lock newer drafts.
    pending=null;
    state.generation.phase='tracking';state.generation.error=null;
    if(!await host.refreshDraft() || !current(value))return false;
    return true;
  }
  async function read(value) {
    if(pending && !await acknowledged(value))return false;
    if(!current(value))return false;
    state.generation.phase='checking';notify();
    await capability(value);
    if(!current(value) || !await history(value))return false;
    state.generation.phase=tracking()?'tracking':'idle';state.generation.error=null;notify();return true;
  }
  function refresh() {
    if(!available() || !host.current(host.token()) || !state.id || !state.view || state.loading ||
        state.status==='revoked' || host.busy())return Promise.resolve(false);
    if(!work && !pending)state.generation.phase='checking';
    return run(read);
  }
  function send() {
    if(workKind==='send')return work;
    if(work) {
      const value=token(),clicked={text:state.text,edits};
      return work.then(()=>current(value) && clicked.edits===edits && clicked.text===state.text ? send() : false);
    }
    if(pending)return refresh();
    if(!available() || !host.current(host.token()) || !allowed())return Promise.resolve(false);
    const clicked={text:state.text,edits};
    state.generation.phase='checking';state.generation.error=null;
    return run(async value=>{
      if(!await host.saveDraft() || !current(value))return false;
      if(clicked.edits!==edits || clicked.text!==state.text) {
        return failed({code:'INPUT_CHANGED',status:409},value);
      }
      if(!allowed())return false;
      const cap=await capability(value);
      if(!current(value))return false;
      if(!cap || clicked.edits!==edits || clicked.text!==state.text) {
        return failed({code:'INPUT_CHANGED',status:409},value);
      }
      if(!sendable(cap) || !allowed()) {state.generation.phase='idle';notify();return false;}
      const body=Object.freeze({request_id:uuid(),expected_scope:Object.freeze({...state.view.scope}),
        expected_composer_revision:state.view.composer_revision,content:clicked.text,
        requested_skill:null,attachment_ids:Object.freeze([]),...(profileMode?{project_intake:true}:{})});
      let existing=false;
      if(nativeConfirmation) {
        const stamp=basis(),id=state.id;
        const selection=profileMode?Object.freeze({request_id:body.request_id,expected_scope:body.expected_scope,
          expected_composer_revision:body.expected_composer_revision,project_intake:true}):null;
        if(profileMode) {
          const preview=await api.submitProfilePreview(id,selection);
          if(!current(value))return false;
          checkedProfilePreview(preview,selection,cap.content_sha256);
          if(!sameBasis(stamp) || id!==state.id || !allowed())return failed({code:'INPUT_CHANGED',status:409},value);
        }
        state.generation.phase='confirming';notify();
        let approval;
        try {
          approval=profileMode?await nativeProfileAuthorization(Object.freeze({conversation_id:id,...selection})):
            await nativeAuthorization(Object.freeze({conversation_id:id,request_id:body.request_id,
            expected_scope:body.expected_scope,expected_composer_revision:body.expected_composer_revision,
            content_sha256:cap.content_sha256}));
        } catch {return failed({code:'NATIVE_CONFIRMATION_FAILED',status:0},value);}
        if(!current(value))return false;
        if(!sameBasis(stamp) || id!==state.id || !allowed())return failed({code:'INPUT_CHANGED',status:409},value);
        if(approval?.canceled===true && approval.ok===false) {
          state.generation.phase='idle';notify();return false;
        }
        if(approval?.ok!==true || approval.canceled===true || profileMode &&
            (Object.keys(approval).length!==2 || !['authorized','existing'].includes(approval.status)))
          return failed({code:'NATIVE_CONFIRMATION_FAILED',status:0},value);
        existing=profileMode && approval.status==='existing';
      }
      pending={id:state.id,body,edits:clicked.edits,result:null};
      state.generation.phase='submitting';state.generation.capability=null;capabilityBasis=null;notify();
      try {
        if(!existing) {
          const result=profileMode?await api.submitProfileGeneration(pending.id,body):await api.submitGeneration(pending.id,body);
          if(!current(value))return false;
          pending.result=checkedRegistration(result,body);
        }
      } catch(error) {
        if(!current(value))return false;
        const definite=error.status>=400 && error.status<500 && !['NETWORK_UNKNOWN','NETWORK_ERROR','INVALID_RESPONSE'].includes(error.code);
        if(definite)pending=null;
        if(error.status===409 && error.code==='VERSION_CONFLICT')await host.readConflict();
        return failed(error,value);
      }
      if(!await acknowledged(value))return false;
      return read(value);
    },'send');
  }
  return {send,refresh,sync,reset,changed,
    busy:()=>Boolean(work),blocked:()=>Boolean(work || pending),unknown:()=>Boolean(pending),
    wait:()=>work || Promise.resolve(false)};
}
