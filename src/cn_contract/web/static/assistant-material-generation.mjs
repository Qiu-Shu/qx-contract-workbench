// This entry only sends after a native, per-request disclosure confirmation.
export function createMaterialGenerationController(api,host){
  const {state,readonly,uuid,notify,nativeMaterialAuthorization}=host;
  let epoch=0,work=null,pending=null;
  const initial=()=>({phase:'idle',error:null,available:typeof nativeMaterialAuthorization==='function'&&!!api.submitMaterialGeneration});
  state.materialGeneration=initial();
  const token=()=>({epoch,host:host.token(),cid:state.id});
  const current=t=>t.epoch===epoch&&host.current(t.host)&&t.cid===state.id;
  const stamp=()=>JSON.stringify([state.view?.scope,state.view?.composer_revision,state.text,state.business?.selectedTask]);
  const usable=()=>!readonly&&state.materialGeneration.available&&state.id&&state.view&&!state.loading&&!state.conflict&&
    !host.blocked()&&!['revoked','readonly','error'].includes(state.status);
  function perform(action){
    if(work)return work;
    const t=token();
    work=Promise.resolve().then(()=>action(t)).catch(error=>{
      if(!current(t))return false;
      if(error.status===401||error.status===403&&error.code==='CROSS_MATTER_DENIED')return host.fail(error,t.host);
      state.materialGeneration.error={code:error.code||'REQUEST_FAILED'};
      state.materialGeneration.phase=pending?'unknown':'error';return false;
    }).finally(()=>{work=null;if(current(t))notify();});
    notify();return work;
  }
  async function accept(result,t){
    if(!current(t))return false;
    const action=pending;
    if(!result||result.input_format!=='material-business-v1'||result.scope?.conversation_id!==action.cid||
        result.scope.input_revision!==action.body.expected_scope.input_revision+1)throw {code:'INVALID_RESPONSE'};
    host.accept(action.body,result,false);
    pending=null;state.materialGeneration.phase='idle';state.materialGeneration.error=null;
    await host.refreshDraft();
    if(current(t))await host.refreshHistory();
    return true;
  }
  function refresh(){
    if(!pending)return Promise.resolve(true);
    return perform(async t=>{
      const result=await api.findGenerationRequest(pending.cid,pending.body.request_id);
      if(!current(t))return false;
      if(!result){state.materialGeneration.phase='unknown';return false;}
      return accept(result,t);
    });
  }
  function send(parent){
    if(pending)return refresh();
    if(work||!usable())return Promise.resolve(false);
    const item=state.business?.items?.find(x=>x.run_id===parent&&x.task_id&&x.workflow);
    if(!item||item.scope.materials_revision!==state.view.scope.materials_revision||
        item.workflow!=='sales'&&!state.materials?.items?.length)return Promise.resolve(false);
    return perform(async t=>{
      // Save edits first; the selected parent question stays explicit in the native preview.
      if(!await host.saveDraft()||!current(t))return false;
      const baseline=stamp(),body={request_id:uuid(),expected_scope:{...state.view.scope},
        expected_composer_revision:state.view.composer_revision,parent_business_run_id:parent};
      state.materialGeneration.phase='confirming';notify();
      const approved=await nativeMaterialAuthorization({conversation_id:state.id,...body});
      if(!current(t))return false;
      if(approved?.ok!==true){state.materialGeneration.phase='idle';return false;}
      if(stamp()!==baseline)throw {code:'INPUT_CHANGED'};
      pending={cid:state.id,body};state.materialGeneration.phase='submitting';notify();
      try{return await accept(await api.submitMaterialGeneration(state.id,body),t);}
      catch(error){if(error.status>=400&&error.status<500)pending=null;throw error;}
    });
  }
  return {send,refresh,sync(){},unknown:()=>!!pending,blocked:()=>!!work||!!pending,busy:()=>!!work,
    wait:()=>work||Promise.resolve(),reset(){epoch++;work=pending=null;state.materialGeneration=initial();}};
}
