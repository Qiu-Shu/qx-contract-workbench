import {isAuthorizationError} from './assistant-generation.mjs';

const keys=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
const sameScope=(a,b)=>keys.every(key=>a?.[key]===b?.[key]);
const invalid=()=>Object.assign(Error('Invalid context response'),{code:'INVALID_RESPONSE'});
const active=run=>['queued','preparing','routing','retrieving','generating','persisting','awaiting_input'].includes(run?.state);

// Enumerate citations saved by this conversation's own searches; memory only, never a draft.
export function savedCitations(state) {
  const found=new Map();
  for(const item of state.research?.items || []) {
    for(const receipt of item.research?.receipts || []) {
      const page=receipt.result?.result?.page,ids=receipt.result?.citation_ids;
      if(!page || !Array.isArray(page.citations) || !Array.isArray(ids) || page.citations.length!==ids.length)continue;
      page.citations.forEach((citation,index)=>{
        if(found.has(ids[index]))return;
        found.set(ids[index],{id:ids[index],title:citation.title||'未命名资料',
          kind:citation.kind,line_start:citation.line_start,line_end:citation.line_end});
      });
    }
  }
  return [...found.values()];
}

// Selection, deterministic preview and one source-bound send; grants live on the desktop bridge.
export function createContextController(api,host) {
  const {state,notify,readonly,uuid}=host;
  let epoch=0,edits=0,work=null,pending=null;
  const initial=()=>({selected:[],preview:null,phase:'idle',canSend:false,canPreview:false,error:null,requestId:null});
  state.context=initial();
  const available=()=>api.submitContextPreview && api.submitContextGeneration && api.findGenerationRequest;
  const bridged=()=>typeof host.nativeContextAuthorization==='function';
  const current=stamp=>stamp.epoch===epoch && host.current(stamp.host);
  const selectedSet=()=>new Set(state.context.selected);
  const known=()=>new Set(savedCitations(state).map(citation=>citation.id));
  const chosen=()=>!readonly && !state.loading && !state.conflict && state.status!=='revoked' &&
    !state.skill && !state.materials?.items?.length && Boolean(state.text.trim()) &&
    state.context.selected.length>=1 && !host.blocked();
  const stampOf=()=>({scope:state.view?.scope,revision:state.view?.composer_revision,
    text:state.savedText,selected:[...state.context.selected],edits,requestId:state.context.requestId});
  const sameStamp=value=>value && edits===value.edits && state.savedText===value.text &&
    state.view?.composer_revision===value.revision && sameScope(value.scope,state.view?.scope) &&
    value.selected.join(',')===state.context.selected.join(',') && value.requestId===state.context.requestId;

  function sync() {
    const preview=state.context.preview;
    if(preview && !sameStamp(preview.stamp))state.context.preview=null;
    state.context.canPreview=Boolean(available() && !work && !pending && chosen());
    state.context.canSend=Boolean(state.context.canPreview && bridged() &&
      state.context.preview?.response?.state==='ready' && sameStamp(state.context.preview.stamp) &&
      !active(state.view?.latest_run));
  }
  function failed(error,stamp) {
    if(!current(stamp))return false;
    if(isAuthorizationError(error))return host.fail(error,stamp.host);
    state.context.error={code:error?.code||'REQUEST_FAILED',status:error?.status||0};
    state.context.phase=pending && !pending.result?'unknown':'error';notify();return false;
  }
  function perform(action) {
    if(work)return work;
    const stamp={epoch,host:host.token()};
    const task=Promise.resolve().then(()=>action(stamp)).catch(error=>failed(error,stamp)).finally(()=>{
      if(work===task)work=null;
      if(current(stamp)){
        if(['checking','confirming','submitting'].includes(state.context.phase))
          state.context.phase=pending?'unknown':active(state.view?.latest_run)?'tracking':'idle';
        notify();
      }
    });
    work=task;notify();return task;
  }
  function checkedPreview(response,body) {
    if(!response || response.sending_enabled!==false || !sameScope(response.scope,body.expected_scope) ||
        response.composer_revision!==body.expected_composer_revision ||
        !['not_configured','ready','input_too_large'].includes(response.state))throw invalid();
    const sources=response.manifest?.sources;
    if(response.manifest?.question!==state.savedText || !Array.isArray(sources) ||
        sources.length!==body.citation_ids.length ||
        !sources.every((source,index)=>source?.saved_citation_id===body.citation_ids[index]))throw invalid();
    const basis=response.send_basis;
    if(response.state==='ready') {
      if(!basis || basis.request_id!==body.request_id || !sameScope(basis.expected_scope,body.expected_scope) ||
          basis.expected_composer_revision!==body.expected_composer_revision ||
          basis.input_format!=='library-context-v1' || !Array.isArray(basis.source_bindings) ||
          basis.source_bindings.length!==body.citation_ids.length ||
          !basis.source_bindings.every((binding,index)=>binding?.saved_citation_id===body.citation_ids[index]) ||
          basis.manifest_sha256!==response.manifest_sha256 || basis.wire_sha256!==response.wire_sha256)
        throw invalid();
    } else if(basis!==null && basis!==undefined)throw invalid();
    return response;
  }
  function checkedRegistration(attempt,body) {
    if(!attempt?.id || !attempt.run_id || !sameScope(attempt.scope,
        {...body.expected_scope,input_revision:body.expected_scope.input_revision+1}))throw invalid();
    return attempt;
  }
  async function acknowledge(stamp) {
    const action=pending;
    if(!action.result){
      const result=await api.findGenerationRequest(action.id,action.body.request_id);
      if(!current(stamp))return false;
      if(!result){state.context.phase='unknown';return false;}
      action.result=checkedRegistration(result,action.body);
    }
    const attempt=checkedRegistration(action.result,action.body);
    host.accept(action.body,attempt,edits===action.edits && state.text===action.body.content);
    pending=null;state.context.error=null;state.context.phase='tracking';
    return await host.refreshDraft() && current(stamp);
  }
  function preview() {
    if(work)return work;
    if(!available() || !host.current(host.token()) || !chosen())return Promise.resolve(false);
    const clicked={text:state.text,edits};
    state.context.phase='checking';state.context.error=null;
    return perform(async stamp=>{
      if(!await host.saveDraft() || !current(stamp))return false;
      if(clicked.edits!==edits || clicked.text!==state.text)return failed({code:'INPUT_CHANGED',status:409},stamp);
      if(!chosen())return false;
      // Mint the request identity only when a preview is actually requested.
      if(!state.context.requestId)state.context.requestId=uuid();
      const body=Object.freeze({expected_scope:Object.freeze({...state.view.scope}),
        expected_composer_revision:state.view.composer_revision,
        citation_ids:Object.freeze([...state.context.selected]),max_rounds:1,
        request_id:state.context.requestId});
      const response=await api.submitContextPreview(state.id,body);
      if(!current(stamp))return false;
      checkedPreview(response,body);
      if(clicked.edits!==edits || clicked.text!==state.savedText)return false;
      state.context.preview={response,stamp:stampOf()};
      state.context.phase='idle';state.context.error=null;notify();return true;
    });
  }
  function send() {
    if(work)return work;
    if(pending)return refresh();
    if(!available() || !host.current(host.token()) || !chosen() || !bridged() ||
        !sameStamp(state.context.preview?.stamp) || state.context.preview.response.state!=='ready')
      return Promise.resolve(false);
    const clicked={text:state.text,edits},requestId=state.context.requestId;
    const selection=Object.freeze([...state.context.selected]);
    state.context.phase='checking';state.context.error=null;
    return perform(async stamp=>{
      if(!await host.saveDraft() || !current(stamp))return false;
      if(clicked.edits!==edits || clicked.text!==state.text)
        return failed({code:'INPUT_CHANGED',status:409},stamp);
      if(!chosen() || !sameStamp(state.context.preview?.stamp))return false;
      const body=Object.freeze({request_id:requestId,expected_scope:Object.freeze({...state.view.scope}),
        expected_composer_revision:state.view.composer_revision,content:clicked.text,
        citation_ids:selection});
      state.context.phase='confirming';notify();
      let approval;
      try{
        approval=await host.nativeContextAuthorization(Object.freeze({conversation_id:state.id,
          request_id:requestId,expected_scope:body.expected_scope,
          expected_composer_revision:body.expected_composer_revision,citation_ids:selection}));
      }catch{return failed({code:'NATIVE_CONFIRMATION_FAILED',status:0},stamp);}
      if(!current(stamp))return false;
      if(clicked.edits!==edits || clicked.text!==state.text || state.context.requestId!==requestId ||
          state.context.selected.join(',')!==selection.join(','))
        return failed({code:'INPUT_CHANGED',status:409},stamp);
      if(approval?.canceled===true && approval.ok===false){state.context.phase='idle';notify();return false;}
      if(approval?.ok!==true || approval.canceled===true)
        return failed({code:'NATIVE_CONFIRMATION_FAILED',status:0},stamp);
      pending={id:state.id,body,edits:clicked.edits,result:null};
      state.context.phase='submitting';notify();
      try{
        const result=await api.submitContextGeneration(pending.id,body);
        if(!current(stamp))return false;
        pending.result=checkedRegistration(result,body);
      }catch(error){
        if(!current(stamp))return false;
        if(error.status>=400 && error.status<500 && !['NETWORK_UNKNOWN','NETWORK_ERROR','INVALID_RESPONSE'].includes(error.code))pending=null;
        if(error.code==='VERSION_CONFLICT')await host.readConflict();
        return failed(error,stamp);
      }
      return acknowledge(stamp);
    });
  }
  function refresh() {
    if(!available() || !host.current(host.token()) || !state.id || !state.view || state.loading ||
        state.status==='revoked' || host.busy())return Promise.resolve(false);
    if(pending)return perform(acknowledge);
    if(state.context.phase==='tracking')return perform(async stamp=>{
      if(!await host.refreshDraft() || !current(stamp))return false;
      if(!active(state.view?.latest_run)){state.context.phase='idle';notify();}
      return true;
    });
    return Promise.resolve(false);
  }
  return {preview,send,refresh,sync,
    toggle(id){
      if(readonly || state.loading || state.status==='revoked' || state.conflict || !known().has(id))return;
      const selected=state.context.selected,index=selected.indexOf(id);
      if(index>=0)selected.splice(index,1);
      else {if(selected.length>=8)return;selected.push(id);}
      edits++;state.context.requestId=null;state.context.preview=null;state.context.error=null;
      if(!['tracking','unknown'].includes(state.context.phase))state.context.phase='idle';
      notify();
    },
    changed(){edits++;state.context.requestId=null;state.context.preview=null;state.context.error=null;},
    reset(){epoch++;work=pending=null;state.context=initial();},
    busy:()=>Boolean(work),blocked:()=>Boolean(work||pending),unknown:()=>Boolean(pending),
    wait:()=>work||Promise.resolve(false)};
}
