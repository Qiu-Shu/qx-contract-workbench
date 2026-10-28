// Local preparation has no model permit; an uncertain POST is recovered by GET only.
export function businessWorkflow(state) {
  const explicit={client_reply:'sales',material_organize:'case',contract_review:'contract',mock_trial:'court'}[state.skill];
  if(explicit)return explicit;
  if(state.skill || state.context?.selected?.length)return null;
  const value=state.text||'',matches=[];
  if(/客户咨询|接待客户|客户的咨询|客户诉求|销售接待/.test(value))matches.push('sales');
  if(/整理案件|整理这个案件|整理材料|整理证据|时间线|事实线索|起草起诉状|起草答辩状/.test(value))matches.push('case');
  if(/审查合同|审查这个合同|审阅合同|审查这份合同|合同审查|重新审查/.test(value)||
      /我是[甲乙]方|代表[甲乙]方/.test(value)&&/审查|审阅|修改/.test(value))matches.push('contract');
  if(/模拟法庭|模拟开庭|模拟对方律师|法官角度|对方律师和法官|庭审准备/.test(value))matches.push('court');
  if(matches.length)return matches.length===1?matches[0]:'clarify';
  if(state.materials?.items?.length)return 'continue';
  return state.business?.selectedTask || (/继续|补充|这次任务|这个任务|上述|刚才/.test(value) &&
    state.business?.items?.some(item=>item.task_id))?'continue':null;
}

export function createBusinessController(api,host) {
  const {state,readonly,uuid,notify}=host;
  let epoch=0,work=null,pending=null,accepted=null,acceptedContent='',explicitSelection=false;
  const initial=()=>({phase:'idle',canSend:false,active:false,items:[],error:null,selectedTask:null});
  state.business=initial();
  const token=()=>({epoch,host:host.token(),cid:state.id});
  const current=t=>t.epoch===epoch && host.current(t.host) && (!t.cid || t.cid===state.id);
  const usable=()=>!readonly&&!state.loading&&!state.conflict&&!host.blocked()&&
    !['saving','revoked','readonly','error'].includes(state.status)&&!!state.text.trim();
  function sync(){
    state.business.active=Boolean(api.submitBusiness&&(pending||businessWorkflow(state)));
    state.business.canSend=state.business.active&&!work&&!pending&&usable();
  }
  function selectOnlyTask(){
    const tasks=new Set(state.business.items.map(item=>item.task_id).filter(Boolean));
    if(!explicitSelection)state.business.selectedTask=tasks.size===1?[...tasks][0]:null;
    else if(!tasks.has(state.business.selectedTask)){state.business.selectedTask=null;explicitSelection=false;}
  }
  function failed(error,t){
    if(!current(t))return false;
    if(error.status===401||error.status===403)return host.fail(error,t.host);
    state.business.error={code:error.code||'REQUEST_FAILED',status:error.status||0};
    state.business.phase=pending?'unknown':'error';notify();return false;
  }
  function perform(action){
    if(work)return work;
    const t=token();
    work=Promise.resolve().then(()=>action(t)).catch(error=>failed(error,t)).finally(()=>{
      work=null;if(current(t)){sync();notify();}
    });
    notify();return work;
  }
  async function accept(result,t){
    const action=pending;
    if(!current(t))return false;
    if(!result||result.request_id!==action.body.request_id||result.scope?.conversation_id!==action.cid||
        result.scope.input_revision!==action.body.expected_scope.input_revision+1)throw {code:'INVALID_RESPONSE'};
    host.accept(action.body,{scope:result.scope},state.text===action.body.content);
    pending=null;state.business.phase='idle';state.business.error=null;
    accepted=result;acceptedContent=action.body.content;
    state.business.items=[...state.business.items.filter(item=>item.run_id!==result.run_id),result];
    if(explicitSelection)state.business.selectedTask=result.task_id||null;
    selectOnlyTask();
    await host.refreshDraft();return true;
  }
  async function recover(t){
    const result=await api.findBusiness(pending.cid,pending.body.request_id);
    if(!current(t))return false;
    if(!result){state.business.phase='unknown';return false;}
    return accept(result,t);
  }
  function send(){
    if(pending)return perform(recover);
    if(!api.submitBusiness||!usable()||!businessWorkflow(state))return Promise.resolve(false);
    return perform(async t=>{
      if(!await host.saveDraft()||!current(t))return false;
      const route=businessWorkflow(state),workflow=['sales','case','contract','court'].includes(route)?route:null;
      const fresh=/重新审查|新建任务|开始新任务/.test(state.text);
      let selected=state.business.items.find(item=>item.task_id===state.business.selectedTask);
      if(!selected&&route==='continue'&&!fresh){
        const candidates=new Map(state.business.items.filter(item=>item.task_id).map(item=>[item.task_id,item]));
        if(candidates.size===1)selected=candidates.values().next().value;
      }
      const task=route!=='clarify'&&selected&&(!workflow||selected.workflow===workflow)&&!fresh?selected.task_id:null;
      pending={cid:state.id,body:{request_id:uuid(),expected_scope:{...state.view.scope},
        expected_composer_revision:state.view.composer_revision,content:state.text,workflow,
        ...(task?{task_id:task}:{}),...(fresh?{new_task:true}:{})}};
      state.business.phase='submitting';notify();
      try{return await accept(await api.submitBusiness(pending.cid,pending.body),t);}
      catch(error){if(error.status>=400&&error.status<500){pending=null;state.business.phase='error';}throw error;}
    });
  }
  function refresh(){
    if(pending)return perform(recover);
    if(!api.getBusinessHistory||!state.id)return Promise.resolve(true);
    return perform(async t=>{
      const items=await api.getBusinessHistory(state.id);
      if(!current(t))return false;
      if(!Array.isArray(items)||items.some(item=>item.scope?.conversation_id!==state.id))throw {code:'INVALID_RESPONSE'};
      state.business.items=items;selectOnlyTask();return true;
    });
  }
  return {sync,send,refresh,unknown:()=>Boolean(pending),blocked:()=>Boolean(work||pending),busy:()=>Boolean(work),
    select(id){
      if(work||pending||readonly)return;
      const item=state.business.items.find(item=>item.task_id===id);
      if(id&&!item)return;
      state.business.selectedTask=id||null;
      explicitSelection=Boolean(id);
      if(id&&!state.text.trim()){
        const last=state.business.items.at(-1);
        const message=last&&!last.task_id?state.view?.messages?.find(message=>message.id===last.message_id):null;
        if(message)state.text=message.content;
      }
      sync();notify();
    },
    wait:()=>work||Promise.resolve(),handles:()=>state.business.active,lastAccepted:()=>accepted,lastAcceptedContent:()=>acceptedContent,
    reset(){epoch++;work=null;pending=null;accepted=null;acceptedContent='';explicitSelection=false;state.business=initial();}};
}
