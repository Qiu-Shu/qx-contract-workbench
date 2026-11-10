import {isAuthorizationError} from './assistant-generation.mjs';

const keys=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
const sameScope=(a,b)=>keys.every(key=>a?.[key]===b?.[key]);
const historicalScope=(a,b)=>a?.workspace_id===b?.workspace_id && a?.conversation_id===b?.conversation_id &&
  a.binding_revision<=b.binding_revision && (a.binding_revision<b.binding_revision ||
    ['scope_kind','scope_ref'].every(key=>a[key]===b[key]));
const active=run=>['queued','preparing','routing','retrieving','generating','persisting','awaiting_input'].includes(run.state);
const invalid=()=>Object.assign(Error('Invalid research response'),{code:'INVALID_RESPONSE'});

// Only explicit local keyword searches. Draft persistence and navigation belong to the shared host.
export function createResearchController(api,host) {
  const {state,notify,readonly,uuid}=host;
  let epoch=0,edits=0,work=null,pending=null;
  const initial=()=>({phase:'idle',canSend:false,items:[],error:null});
  state.research=initial();
  const available=()=>api.submitResearch && api.findResearchRequest && api.getResearchHistory;
  const current=stamp=>stamp.epoch===epoch && host.current(stamp.host);
  const allowed=()=>!readonly && !state.loading && !state.conflict && state.status!=='revoked' &&
    state.skill==='legal_research' && !state.materials?.items?.length &&
    Boolean(state.text.trim()) && [...state.text].length<=200 && !host.blocked();
  const tracking=()=>state.research.items.some(item=>active(item.research.run));
  function sync(){state.research.canSend=Boolean(available() && !work && !pending && allowed() && !tracking());}
  function checked(result,scope) {
    if(!result?.run?.id || result.run.requested_skill!=='legal_research' ||
        !historicalScope(result.run.scope,scope) || !Array.isArray(result.receipts) || result.receipts.length>8)throw invalid();
    for(const receipt of result.receipts) {
      const page=receipt.result?.result?.page;
      if(receipt.run_id!==result.run.id || !sameScope(receipt.scope,result.run.scope) ||
          !sameScope(receipt.result?.result?.scope,result.run.scope) || receipt.handler_id!=='legal_library.search' ||
          !page || !Array.isArray(page.citations) || page.citations.length>8 ||
          !Array.isArray(receipt.result.citation_ids) || page.citations.length!==receipt.result.citation_ids.length)throw invalid();
    }
    return result;
  }
  function registration(result,body) {
    checked(result,{...body.expected_scope,input_revision:body.expected_scope.input_revision+1});
    if(result.run.request_id!==body.request_id || !sameScope(result.run.scope,
        {...body.expected_scope,input_revision:body.expected_scope.input_revision+1}))throw invalid();
    return result;
  }
  function failed(error,stamp) {
    if(!current(stamp))return false;
    if(isAuthorizationError(error))return host.fail(error,stamp.host);
    state.research.error={code:error?.code||'REQUEST_FAILED',status:error?.status||0};
    state.research.phase=pending&&!pending.result?'unknown':'error';notify();return false;
  }
  function perform(action) {
    if(work)return work;
    const stamp={epoch,host:host.token()};
    const task=Promise.resolve().then(()=>action(stamp)).catch(error=>failed(error,stamp)).finally(()=>{
      if(work===task)work=null;
      if(current(stamp)){
        if(['checking','submitting'].includes(state.research.phase))state.research.phase=pending?'unknown':tracking()?'tracking':'idle';
        notify();
      }
    });
    work=task;notify();return task;
  }
  async function acknowledge(stamp) {
    const action=pending;
    if(!action.result){
      const result=await api.findResearchRequest(action.id,action.body.request_id);
      if(!current(stamp))return false;
      if(!result){state.research.phase='unknown';return false;}
      action.result=registration(result,action.body);
    }
    const result=registration(action.result,action.body);
    host.accept(action.body,result.run,edits===action.edits && state.text===action.body.content);
    pending=null;state.research.error=null;
    return await host.refreshDraft() && current(stamp);
  }
  async function read(stamp) {
    if(pending && !await acknowledge(stamp))return false;
    if(!current(stamp))return false;
    state.research.phase='checking';notify();
    const view=state.view,id=state.id,ids=[...new Set(view.messages.map(message=>message.id))],items=[];
    for(let offset=0;offset<ids.length;offset+=50){
      const batch=ids.slice(offset,offset+50),result=await api.getResearchHistory(id,batch);
      if(!current(stamp) || !sameScope(view.scope,state.view?.scope))return false;
      if(!sameScope(result?.scope,view.scope) || !Array.isArray(result.items) || result.items.length>batch.length)throw invalid();
      const seen=new Set();
      for(const item of result.items){
        if(!batch.includes(item.message_id) || seen.has(item.message_id) || item.research?.run?.message_id!==item.message_id)throw invalid();
        seen.add(item.message_id);checked(item.research,view.scope);items.push(item);
      }
    }
    if(!current(stamp) || !sameScope(view.scope,state.view?.scope) ||
        ids.join(',')!==[...new Set(state.view.messages.map(message=>message.id))].join(','))return false;
    state.research.items=items;state.research.phase=tracking()?'tracking':'idle';state.research.error=null;notify();return true;
  }
  function refresh(){
    if(!available() || !host.current(host.token()) || !state.id || !state.view || state.loading ||
        state.status==='revoked' || host.busy())return Promise.resolve(false);
    return perform(read);
  }
  function send(){
    if(work)return work;
    if(pending)return refresh();
    if(!available() || !host.current(host.token()) || !allowed() || tracking())return Promise.resolve(false);
    const clicked={text:state.text,edits};state.research.phase='submitting';state.research.error=null;
    return perform(async stamp=>{
      if(!await host.saveDraft() || !current(stamp))return false;
      if(clicked.edits!==edits || clicked.text!==state.text)return failed({code:'INPUT_CHANGED'},stamp);
      if(!allowed())return false;
      const body=Object.freeze({request_id:uuid(),expected_scope:Object.freeze({...state.view.scope}),
        expected_composer_revision:state.view.composer_revision,content:clicked.text,
        requested_skill:'legal_research',attachment_ids:Object.freeze([])});
      pending={id:state.id,body,edits:clicked.edits,result:null};notify();
      try{
        const result=await api.submitResearch(pending.id,body);
        if(!current(stamp))return false;
        pending.result=registration(result,body);
      }catch(error){
        if(!current(stamp))return false;
        if(error.status>=400 && error.status<500 && !['NETWORK_UNKNOWN','NETWORK_ERROR','INVALID_RESPONSE'].includes(error.code))pending=null;
        if(error.code==='VERSION_CONFLICT')await host.readConflict();
        return failed(error,stamp);
      }
      return read(stamp);
    });
  }
  return {send,refresh,sync,changed(){edits++;},reset(){epoch++;work=pending=null;state.research=initial();},
    busy:()=>Boolean(work),blocked:()=>Boolean(work||pending),unknown:()=>Boolean(pending),wait:()=>work||Promise.resolve(false)};
}
