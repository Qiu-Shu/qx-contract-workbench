import {errorText} from './assistant-render.mjs';

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const isId=value=>typeof value==='string'&&uuid.test(value);
const utc=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value)&&
  Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,19)===value.slice(0,19);
const exact=(value,fields)=>value&&typeof value==='object'&&!Array.isArray(value)&&
  Object.keys(value).length===fields.length&&fields.every(field=>Object.hasOwn(value,field));

export function bindWeixinPending({controller,api,root=document,readonly=false,getAuthorization=()=>null,
  isBlocked=()=>false,onActivityChange=()=>{},onDispatched=async()=>{}}={}){
  const el=name=>root.getElementById('weixin-pending-'+name);
  const node=(tag,text)=>{const value=root.createElement(tag);if(text!==undefined)value.textContent=text;return value;};
  let cid=null,epoch=0,reading=0,signature='',target='',choices=[],choiceCursor=null;
  let items=[],next=null,pageCursor=null,seen=new Set(),buttons=[];
  let busy=false,loading=false,pending=null,closed=false,revoked=false;
  const active=()=>!closed&&!revoked&&!!cid;
  const token=()=>({cid,epoch});
  const valid=key=>active()&&key.cid===cid&&key.epoch===epoch;
  const base=()=>'/api/assistant/conversations/'+encodeURIComponent(cid)+'/weixin-authorization';
  const stable=()=>!controller.state.loading&&!controller.state.dirty&&!controller.state.conflict&&
    !controller.state.materialAction&&!['saving','error','revoked'].includes(controller.state.status);
  const readable=()=>active()&&!readonly&&getAuthorization()?.state!=='restored_blocked';
  const writable=()=>readable()&&stable()&&!busy&&!loading&&!pending&&!isBlocked()&&
    !choices.find(view=>view.scope.conversation_id===target)?.archived_at&&
    ['current','refresh_required','target_changed'].includes(getAuthorization()?.state);
  const tell=text=>{el('notice').textContent=text;};
  function render(){
    const locked=!readable()||busy||loading||!!pending;
    el('target').disabled=locked;el('targets').disabled=locked;
    el('targets-more').hidden=!choiceCursor;el('targets-more').disabled=locked;
    el('read').disabled=locked||!target;el('more').hidden=!next;el('more').disabled=locked||!next;
    el('find').hidden=!pending;el('find').disabled=!active()||busy||loading||!pending;
    for(const {button,index} of buttons)button.disabled=!writable()||index!==0||pageCursor!==null;
    el('panel').setAttribute('aria-busy',String(busy||loading));
    el('state').textContent=!active()?'打开已有对话后，可核对待收件。':!readable()?'恢复副本不能读取或分发待收件。':
      loading?'正在读取待收件信息…':items.length?`本批 ${items.length} 条；${pageCursor?'请回到首批后按顺序分发。':'请从首条依次分发。'}`:
      target?'当前未显示待收件；请读取列表，或按提示重新核对。':'先选择收件原先指定的目标对话。';
  }
  function update(){render();onActivityChange();}
  function clearItems(){items=[];next=null;pageCursor=null;buttons=[];el('list').replaceChildren();el('result').replaceChildren();}
  function reset(){++epoch;++reading;clearItems();seen.clear();choices=[];choiceCursor=null;target='';
    busy=false;loading=false;pending=null;el('target').replaceChildren();update();}
  function failure(error){
    if(controller.revoke(error)){revoked=true;reset();tell('当前权限或目标归属不允许读取。请重新打开对话后核对原授权目标。');}
    else tell(error.status===409?'记录或授权状态已变化。请重新读取；未再次分发。':errorText(error));
  }
  function options(){
    const empty=node('option','请选择收件原先指定的目标');empty.value='';el('target').replaceChildren(empty);
    for(const view of choices){const option=node('option',view.display_title+(view.archived_at?'（已归档）':''));
      option.value=view.scope.conversation_id;el('target').append(option);}
    el('target').value=target;
  }
  async function loadTargets(append=false){
    if(!readable()||busy||loading||pending||(append&&!choiceCursor))return false;
    const key=token(),read=++reading;loading=true;clearItems();seen.clear();update();
    try{
      const result=await api.listConversations(append?choiceCursor:null);
      if(!valid(key)||read!==reading)return false;
      if(!Array.isArray(result?.items)||(result.next_cursor!==null&&typeof result.next_cursor!=='string'))throw {code:'STATE_CONFLICT'};
      const values=[...(append?choices:[controller.state.view]),...result.items];
      if(values.some(view=>!isId(view?.scope?.conversation_id)||view.scope.workspace_id!==controller.state.view?.scope.workspace_id||
        typeof view.display_title!=='string'))throw {code:'STATE_CONFLICT'};
      choices=values.filter((view,index)=>values.findIndex(other=>other.scope.conversation_id===view.scope.conversation_id)===index);
      choiceCursor=result.next_cursor;if(!choices.some(view=>view.scope.conversation_id===target))target='';
      options();tell('仅原先授权的目标可读取；选择其他对话不会转移收件。');return true;
    }catch(error){if(valid(key)&&read===reading){choices=[];choiceCursor=null;target='';options();failure(error);}return false;}
    finally{if(valid(key)&&read===reading){loading=false;update();}}
  }
  function validPage(value,chosen,cursor){
    return exact(value,['mode','read_only','conversation_id','items','next_cursor'])&&value.mode==='synthetic'&&value.read_only===true&&
      value.conversation_id===chosen&&Array.isArray(value.items)&&value.items.length<=20&&
      value.items.every(item=>exact(item,['descriptor_id','conversation_id','received_at','has_text','media_count'])&&
        isId(item.descriptor_id)&&item.conversation_id===chosen&&utc(item.received_at)&&typeof item.has_text==='boolean'&&
        Number.isSafeInteger(item.media_count)&&item.media_count>=0&&item.media_count<=20&&(!cursor||!seen.has(item.descriptor_id)))&&
      new Set(value.items.map(item=>item.descriptor_id)).size===value.items.length&&
      (value.next_cursor===null||(value.items.length===20&&value.next_cursor===value.items.at(-1).descriptor_id&&value.next_cursor!==cursor));
  }
  function rows(){
    el('list').replaceChildren();buttons=[];
    for(const [index,item] of items.entries()){
      const row=node('li'),time=node('time',new Date(item.received_at).toLocaleString('zh-CN',{hour12:false}));
      time.dateTime=item.received_at;
      const meta=node('span',`${item.has_text?'含文本':'无文本'} · 附件 ${item.media_count} 个`);
      const button=node('button','分发到所选对话');button.type='button';button.className='quiet-button';
      button.addEventListener('click',()=>dispatch(item));buttons.push({button,index});row.append(time,meta,button);el('list').append(row);
    }
  }
  async function refresh(cursor=null){
    if(!readable()||busy||loading||pending||!isId(target)||!choices.some(view=>view.scope.conversation_id===target))return false;
    const key=token(),chosen=target,read=++reading;
    if(!cursor)seen.clear();loading=true;clearItems();update();
    try{
      const query=new URLSearchParams({target_conversation_id:chosen,limit:'20'});if(cursor)query.set('cursor',cursor);
      const result=await api.request(base()+'/pending?'+query);
      if(!valid(key)||read!==reading||target!==chosen)return false;
      if(!validPage(result,chosen,cursor))throw {code:'STATE_CONFLICT'};
      items=result.items;next=result.next_cursor;pageCursor=cursor;items.forEach(item=>seen.add(item.descriptor_id));rows();
      tell(items.length?'收件仍归原授权目标；分发只进入本机模拟任务，不运行审查。':'该目标没有尚未分发的收件。');return true;
    }catch(error){if(valid(key)&&read===reading){clearItems();failure(error);}return false;}
    finally{if(valid(key)&&read===reading){loading=false;update();}}
  }
  function matches(value,operation){
    return exact(value,['mode','state','descriptor_id','conversation_id','task_event_id','expected_task_cursor','next_task_cursor','created_at','receipt_sha256'])&&
      value.mode==='synthetic'&&value.state==='recorded'&&value.descriptor_id===operation.descriptor&&value.conversation_id===operation.target&&
      isId(value.task_event_id)&&Number.isSafeInteger(value.expected_task_cursor)&&value.expected_task_cursor>=0&&
      Number.isSafeInteger(value.next_task_cursor)&&value.next_task_cursor===value.expected_task_cursor+1&&utc(value.created_at)&&
      typeof value.receipt_sha256==='string'&&/^[a-f0-9]{64}$/.test(value.receipt_sha256);
  }
  async function confirmed(value,key){
    pending=null;clearItems();update();
    try{await onDispatched(value);}catch(error){if(valid(key))failure(error);}
    if(!valid(key))return;
    tell('分发回执已确认；正在刷新待收件列表…');
    busy=false;await refresh();if(!valid(key))return;
    const link=node('a','查看目标对话的模拟任务');link.href='/assistant/'+encodeURIComponent(value.conversation_id)+'#task-draft-panel';
    el('result').replaceChildren(node('span','分发回执已确认。 '),link);
  }
  async function dispatch(item){
    if(!writable()||pageCursor!==null||items[0]!==item)return false;
    const key=token(),operation={path:base(),target,descriptor:item.descriptor_id};pending=operation;busy=true;update();
    el('result').replaceChildren();
    tell('正在分发首条收件…');
    try{
      const result=await api.request(operation.path+'/dispatches',{method:'POST',body:{descriptor_id:operation.descriptor}});
      if(!valid(key)||pending!==operation)return false;
      if(!matches(result,operation))throw {code:'NETWORK_UNKNOWN'};
      await confirmed(result,key);return true;
    }catch(error){if(valid(key)){
      if(error.code==='NETWORK_UNKNOWN')tell('分发结果尚未确认。请查找本条分发结果，不会再次提交。');
      else{pending=null;clearItems();failure(error);}
    }return false;}
    finally{if(valid(key)){busy=false;update();}}
  }
  async function find(){
    if(!active()||!pending||busy||loading)return false;
    const key=token(),operation=pending;busy=true;update();
    try{
      const result=await api.request(operation.path+'/dispatches/by-descriptor/'+encodeURIComponent(operation.descriptor));
      if(!valid(key)||pending!==operation)return false;
      if(result===null||!matches(result,operation)){tell('尚未查到匹配的分发回执。保留了本条操作，可稍后再查。');return false;}
      await confirmed(result,key);return true;
    }catch(error){if(valid(key))failure(error);return false;}
    finally{if(valid(key)){busy=false;update();}}
  }
  el('targets').addEventListener('click',()=>loadTargets());el('targets-more').addEventListener('click',()=>loadTargets(true));
  el('read').addEventListener('click',()=>refresh());el('more').addEventListener('click',()=>next?refresh(next):false);
  el('find').addEventListener('click',find);
  el('target').addEventListener('change',()=>{
    if(busy||pending){el('target').value=target;return;}
    ++reading;loading=false;target=choices.some(view=>view.scope.conversation_id===el('target').value)?el('target').value:'';
    clearItems();seen.clear();tell('已切换目标，请明确读取待收件。');update();
  });
  el('panel').addEventListener('toggle',()=>{if(el('panel').open&&!choices.length)void loadTargets();});
  render();
  return {loadTargets,refresh,find,updateControls:render,hasPending:()=>active()&&(busy||!!pending),
    state(state){
      if(closed)return;
      if(state.status==='revoked'){revoked=true;cid=null;reset();return;}
      if(state.id!==cid){reset();cid=state.id;signature='';tell('');}
      const nextSignature=JSON.stringify([cid,state.view?.scope,state.materials?.scope]);
      if(signature&&signature!==nextSignature){++reading;loading=false;clearItems();seen.clear();}
      signature=nextSignature;render();
    },dispose(){closed=true;reset();}};
}
