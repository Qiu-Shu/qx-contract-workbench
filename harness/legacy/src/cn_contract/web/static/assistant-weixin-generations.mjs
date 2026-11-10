import {errorText} from './assistant-render.mjs';

const fields=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
const hashPattern=/^[a-f0-9]{64}$/;
const sameScope=(a,b)=>!!a&&!!b&&fields.every(field=>a[field]===b[field]);
const safeScope=value=>value&&typeof value.workspace_id==='string'&&typeof value.conversation_id==='string'&&
  ['conversation','matter','intake'].includes(value.scope_kind)&&
  ['binding_revision','input_revision','materials_revision'].every(field=>Number.isSafeInteger(value[field])&&value[field]>=0);
async function scopeHash(scope){
  const raw=JSON.stringify(Object.fromEntries([...fields].sort().map(field=>[field,scope[field]])));
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw));
  return [...new Uint8Array(bytes)].map(value=>value.toString(16).padStart(2,'0')).join('');
}

export function bindWeixinGenerations({controller,api,root=document,readonly=false,uuid=()=>crypto.randomUUID(),
  getAuthorization=()=>null,isBlocked=()=>false,onActivityChange=()=>{},onSaved=async()=>{}}={}){
  const el=name=>root.getElementById('weixin-generation-'+name);
  const endpoint=id=>'/api/assistant/conversations/'+encodeURIComponent(id);
  let cid=null,epoch=0,reading=0,selection=0,signature='',head=null,choices=[],cursor=null;
  let prepared=null,pending=null,busy=false,loading=false,closed=false,revoked=false;
  const active=()=>!closed&&!revoked;
  const token=()=>({cid,epoch});
  const valid=key=>active()&&key.cid===cid&&key.epoch===epoch;
  const base=()=>endpoint(cid)+'/weixin-authorization/generations';
  const stable=()=>!controller.state.loading&&!controller.state.dirty&&!controller.state.conflict&&
    !controller.state.materialAction&&!['saving','error','revoked'].includes(controller.state.status);
  const writable=()=>active()&&!!cid&&!readonly&&!busy&&!loading&&!pending&&!isBlocked()&&stable()&&!!head&&
    ['current','refresh_required','target_changed'].includes(getAuthorization()?.state);
  const dirty=()=>!!el('target').value||!!el('reason').value;
  const currentPlan=plan=>plan.signature===signature&&stable()&&!readonly&&!isBlocked()&&
    ['current','refresh_required','target_changed'].includes(getAuthorization()?.state);
  const tell=text=>{el('notice').textContent=text;};
  const bindingMatches=(value,target)=>value&&typeof value.id==='string'&&value.id.length>0&&
    value.conversation_id===target&&value.channel==='synthetic';
  function render(){
    el('state').textContent=!active()?'当前权限不可用。':head?
      `当前目标历史：${head.generation} 代；收件仍暂停。`:cid?'尚未读取目标历史，或本对话尚未绑定本机收件。':'打开已有对话后可核对目标历史。';
    el('read').disabled=!active()||!cid||busy||!!pending;
    el('more').hidden=!cursor;el('more').disabled=!active()||busy||loading||!!pending;
    for(const name of ['target','reason'])el(name).disabled=!writable();
    el('prepare').disabled=!writable()||!el('target').value||!el('reason').value.trim()||el('reason').value.trim().length>200;
    el('save').disabled=!writable()||!prepared;
    el('save').textContent=busy?'正在保存历史…':'保存目标历史';
    el('clear').disabled=!active()||busy||!!pending||!dirty();
    el('find').hidden=!pending;el('find').disabled=!active()||busy||loading||!pending;
    el('panel').setAttribute('aria-busy',String(busy||loading));
  }
  function update(){render();onActivityChange();}
  function clearForm(){++selection;prepared=null;el('target').value='';el('reason').value='';el('preview').textContent='';}
  function clear(){++epoch;++reading;head=null;choices=[];cursor=null;pending=null;busy=false;loading=false;
    clearForm();el('target').replaceChildren();update();}
  function failure(error){
    if(controller.revoke(error)){revoked=true;clear();tell('当前权限已变化，请重新打开对话后核对。');}
    else{prepared=null;el('preview').textContent='';if(error.status===409)head=null;
      tell(error.status===409?'记录或目标已变化，未重新提交。请重新读取并核对目标。':errorText(error));}
  }
  function options(){
    const selected=el('target').value;
    const empty=root.createElement('option');empty.value='';empty.textContent='请选择新的目标对话';
    el('target').replaceChildren(empty);
    for(const view of choices){
      const item=root.createElement('option');item.value=view.scope.conversation_id;
      item.textContent=view.display_title+' · 输入'+view.scope.input_revision+'版 / 材料'+view.scope.materials_revision+'版';
      el('target').append(item);
    }
    el('target').value=choices.some(view=>view.scope.conversation_id===selected)?selected:'';
  }
  async function page(append,key,read){
    const result=await api.listConversations(append?cursor:null);
    if(!valid(key)||read!==reading)return;
    if(!Array.isArray(result?.items))throw {code:'STATE_CONFLICT'};
    const views=append?[...choices,...result.items]:result.items;
    choices=views.filter((view,index)=>safeScope(view.scope)&&!view.archived_at&&
      view.scope.workspace_id===controller.state.view?.scope.workspace_id&&view.scope.conversation_id!==cid&&
      view.scope.conversation_id!==head?.scope.conversation_id&&
      views.findIndex(other=>other.scope?.conversation_id===view.scope.conversation_id)===index);
    cursor=result.next_cursor;options();
  }
  async function refresh(){
    if(!active()||!cid||busy||pending)return false;
    const key=token(),read=++reading;++selection;loading=true;prepared=null;el('preview').textContent='';update();
    try{
      const result=await api.request(base()+'/head');
      if(!valid(key)||read!==reading)return false;
      if(result!==null){
        if(result?.mode!=='synthetic'||result.state!=='history_only'||!Number.isSafeInteger(result.generation)||result.generation<0||
          !Number.isSafeInteger(result.checkpoint_revision)||result.checkpoint_revision<0||!safeScope(result.scope)||
          result.scope.workspace_id!==controller.state.view?.scope.workspace_id||
          (result.generation===0?result.generation_sha256!==null||result.scope.conversation_id!==cid:!hashPattern.test(result.generation_sha256))||
          await scopeHash(result.scope)!==result.scope_sha256)throw {code:'STATE_CONFLICT'};
      }
      if(!valid(key)||read!==reading)return false;
      head=result;choices=[];cursor=null;options();
      if(head)await page(false,key,read);
      return true;
    }catch(error){if(valid(key)&&read===reading){head=null;failure(error);}return false;}
    finally{if(valid(key)&&read===reading){loading=false;update();}}
  }
  async function prepare(){
    if(!writable())return false;
    const target=el('target').value,reason=el('reason').value.trim();
    if(!choices.some(view=>view.scope.conversation_id===target)||!reason||reason.length>200)return false;
    const key=token(),chosen=++selection,read=reading;loading=true;prepared=null;update();
    try{
      const view=await api.getConversation(target);
      if(!valid(key)||chosen!==selection)return false;
      if(!safeScope(view?.scope)||view.scope.conversation_id!==target||view.scope.workspace_id!==head.scope.workspace_id||view.archived_at)
        throw {code:'STATE_CONFLICT'};
      const tasks=await api.request(endpoint(target)+'/task-drafts');
      if(!valid(key)||chosen!==selection)return false;
      if(tasks.binding!==null&&!bindingMatches(tasks.binding,target))throw {code:'STATE_CONFLICT'};
      prepared={head:structuredClone(head),scope:structuredClone(view.scope),reason,binding:tasks.binding,title:view.display_title,signature};
      el('preview').textContent=`目标：${view.display_title}；输入${view.scope.input_revision}版，材料${view.scope.materials_revision}版。理由：${reason}。仅保存历史，收件仍暂停。`;
      return true;
    }catch(error){if(valid(key)&&chosen===selection)failure(error);return false;}
    finally{if(valid(key)&&read===reading){loading=false;update();}}
  }
  async function receiptMatches(value,operation){
    const body=operation.body;
    return value?.mode==='synthetic'&&value.state==='history_only'&&value.request_id===body.request_id&&
      value.generation===body.expected_generation+1&&value.previous_generation_sha256===body.expected_previous_generation_sha256&&
      value.previous_scope_sha256===body.expected_previous_scope_sha256&&value.checkpoint_revision===body.expected_checkpoint_revision&&
      sameScope(value.scope,body.expected_scope)&&hashPattern.test(value.generation_sha256||'')&&
      typeof value.created_at==='string'&&/(Z|\+00:00)$/.test(value.created_at)&&Number.isFinite(Date.parse(value.created_at))&&
      value.scope_sha256===await scopeHash(body.expected_scope);
  }
  async function success(key){
    pending=null;clearForm();let updated=true;
    try{updated=await onSaved()!==false;}catch(error){updated=false;if(controller.revoke(error)){revoked=true;clear();}}
    if(!valid(key))return;
    busy=false;const refreshed=await refresh();
    if(valid(key))tell('已保存目标历史；收件仍暂停，不会自动启动微信或审查。'+
      (!updated||!refreshed?'当前状态未完整更新，请重新读取后核对。':''));
  }
  async function save(){
    if(!writable()||!prepared)return false;
    const key=token(),plan=structuredClone(prepared);busy=true;update();
    try{
      if(!plan.binding){
        pending={kind:'binding',plan};
        const bound=await api.request(endpoint(plan.scope.conversation_id)+'/task-bindings',{method:'POST'});
        if(!valid(key))return false;
        if(!bindingMatches(bound,plan.scope.conversation_id))throw {code:'NETWORK_UNKNOWN'};
        plan.binding=bound;prepared.binding=bound;pending=null;
      }
      if(!currentPlan(plan)){
        head=null;prepared=null;el('preview').textContent='';
        tell('目标绑定已确认，但页面状态已变化，尚未保存目标历史。请重新读取并核对。');return false;
      }
      const operation={kind:'generation',path:base(),body:{request_id:uuid(),expected_generation:plan.head.generation,
        expected_previous_generation_sha256:plan.head.generation_sha256,expected_previous_scope_sha256:plan.head.scope_sha256,
        expected_checkpoint_revision:plan.head.checkpoint_revision,task_binding_id:plan.binding.id,expected_scope:plan.scope,reason:plan.reason}};
      pending=operation;
      const result=await api.request(operation.path,{method:'POST',body:operation.body});
      if(!valid(key))return false;
      if(!await receiptMatches(result,operation))throw {code:'NETWORK_UNKNOWN'};
      if(!valid(key))return false;
      await success(key);return true;
    }catch(error){if(valid(key)){
      if(error.code==='NETWORK_UNKNOWN')tell('保存结果尚未确认。请查找本次结果，不会自动重发或继续写入。');
      else{pending=null;failure(error);}
    }return false;}
    finally{if(valid(key)){busy=false;update();}}
  }
  async function find(){
    if(!active()||!pending||busy||loading)return false;
    const key=token(),operation=pending;busy=true;update();
    try{
      if(operation.kind==='binding'){
        const result=await api.request(endpoint(operation.plan.scope.conversation_id)+'/task-drafts');
        if(!valid(key)||pending!==operation)return false;
        if(!bindingMatches(result?.binding,operation.plan.scope.conversation_id)){
          tell('尚未确认目标绑定。保留本次操作，可稍后再次查找。');return false;}
        pending=null;
        if(!currentPlan(operation.plan)){
          head=null;prepared=null;el('preview').textContent='';
          tell('已确认本机目标绑定，但页面状态已变化。请重新读取并核对后再保存目标历史。');return true;
        }
        prepared={...operation.plan,binding:result.binding};
        tell('已确认本机目标绑定。请核对预览后再次明确保存目标历史。');return true;
      }
      const result=await api.request(operation.path+'/by-request/'+encodeURIComponent(operation.body.request_id));
      if(!valid(key)||pending!==operation)return false;
      if(!result||!await receiptMatches(result,operation)){
        tell('尚未查到匹配的历史回执。保留了本次请求，可稍后再次查找。');return false;}
      if(!valid(key)||pending!==operation)return false;
      await success(key);return true;
    }catch(error){if(valid(key))failure(error);return false;}
    finally{if(valid(key)){busy=false;update();}}
  }
  el('read').addEventListener('click',refresh);
  el('prepare').addEventListener('click',prepare);el('save').addEventListener('click',save);el('find').addEventListener('click',find);
  el('more').addEventListener('click',async()=>{
    if(!active()||!cursor||busy||loading||pending)return;
    const key=token(),read=++reading;loading=true;update();
    try{await page(true,key,read);}catch(error){if(valid(key))failure(error);}
    finally{if(valid(key)&&read===reading){loading=false;update();}}
  });
  for(const [name,event] of [['target','change'],['reason','input']])el(name).addEventListener(event,()=>{
    if(busy||pending)return;++selection;prepared=null;el('preview').textContent='';update();
  });
  el('clear').addEventListener('click',()=>{if(!active()||busy||pending)return;clearForm();tell('');update();});
  el('panel').addEventListener('toggle',()=>{if(el('panel').open&&!head&&!loading)void refresh();});
  render();
  return {refresh,updateControls:render,hasPending:()=>active()&&(busy||!!pending||dirty()),
    state(state){
      if(closed)return;
      if(state.status==='revoked'){revoked=true;cid=null;clear();return;}
      if(state.id!==cid){clear();cid=state.id;signature='';tell('');}
      const next=JSON.stringify([cid,state.view?.scope,state.materials?.scope]);
      if(signature&&signature!==next&&!pending&&!busy){head=null;prepared=null;el('preview').textContent='';}
      signature=next;render();
    },dispose(){closed=true;clear();}};
}
