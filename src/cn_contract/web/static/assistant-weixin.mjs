import {errorText} from './assistant-render.mjs';

const labels={unbound:'本对话尚未绑定本机合成收件；真实微信未接通。',
  current:'本机收件授权与当前输入和材料版本一致。',
  refresh_required:'输入或材料版本已变化，需显式更新同一目标的收件授权。',
  target_changed:'授权目标或版本已改变；历史记录不会自动更新收件。',
  revoked:'收件授权已撤销，不能在这里恢复。',archived:'对话已归档，不能更新收件授权。',
  restored_blocked:'恢复副本只读，可核对授权记录，不能更新或继续收件。'};

export function bindWeixinAuthorization({controller,api,root=document,readonly=false,
  uuid=()=>crypto.randomUUID(),isBlocked=()=>false,onActivityChange=()=>{}}={}){
  const byId=id=>root.getElementById(id);
  let cid=null,epoch=0,reading=0,signature='',data=null,closed=false,revoked=false;
  let busy=false,loading=false,pending=null;
  const active=()=>!closed&&!revoked;
  const key=()=>({cid,epoch});
  const valid=token=>active()&&token.cid===cid&&token.epoch===epoch;
  const base=()=>'/api/assistant/conversations/'+encodeURIComponent(cid)+'/weixin-authorization';
  const stable=()=>!controller.state.loading&&!controller.state.dirty&&!controller.state.conflict&&
    !controller.state.materialAction&&!['saving','error','revoked'].includes(controller.state.status);
  const writable=()=>active()&&!readonly&&!busy&&!loading&&!pending&&!isBlocked()&&stable()&&data?.state==='refresh_required';
  const tell=text=>{byId('weixin-notice').textContent=text;};
  function receiptMatches(value,operation){
    const fields=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
    return value?.request_id===operation.body.request_id&&value.revision===operation.body.expected_grant_revision+1&&
      value.previous_scope_sha256===operation.body.expected_scope_sha256&&
      fields.every(field=>value.scope?.[field]===operation.body.expected_scope[field])&&
      /^[a-f0-9]{64}$/.test(value.scope_sha256||'')&&/^[a-f0-9]{64}$/.test(value.grant_sha256||'');
  }
  function render(){
    byId('weixin-state').textContent=!active()?'暂不能读取收件授权。':data?labels[data.state]:
      cid?'正在读取本机收件授权…':'打开已有对话后，可核对本机合成收件授权。';
    byId('weixin-authorize').hidden=data?.state!=='refresh_required'||!active()||readonly;
    byId('weixin-authorize').disabled=!writable();
    byId('weixin-authorize').textContent=busy&&!pending?'正在更新授权…':'更新本机授权';
    byId('weixin-read').disabled=!active()||!cid||busy||loading;
    byId('weixin-find').hidden=!pending||!active();
    byId('weixin-find').disabled=!active()||busy||loading;
    byId('weixin-authorization').setAttribute('aria-busy',String(busy||loading));
  }
  function clear(){++epoch;++reading;data=null;pending=null;busy=false;loading=false;signature='';render();}
  function failure(error){
    if(controller.revoke(error)){
      revoked=true;clear();tell('当前权限已变化，请重新打开对话后核对。');
    }else tell(errorText(error));
  }
  async function refresh(){
    if(!active()||!cid)return false;
    const token=key(),read=++reading;loading=true;render();
    try{
      const result=await api.request(base());
      if(!valid(token)||read!==reading)return false;
      if(result?.mode!=='synthetic'||!Object.hasOwn(labels,result.state)||result.current_scope?.conversation_id!==cid)
        throw {code:'STATE_CONFLICT'};
      data=result;return true;
    }catch(error){if(valid(token)&&read===reading){data=null;failure(error);}return false;}
    finally{if(valid(token)&&read===reading){loading=false;render();onActivityChange();}}
  }
  async function authorize(){
    if(!writable())return false;
    const token=key(),operation={path:base(),body:{request_id:uuid(),expected_grant_revision:data.grant_revision,
      expected_scope_sha256:data.scope_sha256,expected_scope:structuredClone(data.current_scope),
      reason:'对话页显式更新同目标输入和材料授权'}};
    busy=true;render();onActivityChange();tell('正在保存本次明确授权…');
    try{
      const receipt=await api.request(operation.path+'/refresh',{method:'POST',body:operation.body});
      if(!valid(token))return false;
      if(!receiptMatches(receipt,operation))throw {code:'NETWORK_UNKNOWN',status:0};
      await refresh();if(valid(token))tell('已保存本次授权；当前可用状态以上方重新读取结果为准。');
      return true;
    }catch(error){
      if(valid(token)){
        if(error.code==='NETWORK_UNKNOWN'){
          pending=operation;tell('本次授权结果尚未确认。请查找本次授权结果，不会自动重发。');
        }else{failure(error);if(active())await refresh();}
      }
      return false;
    }finally{if(valid(token)){busy=false;render();onActivityChange();}}
  }
  async function find(){
    if(!active()||!pending||busy||loading)return false;
    const token=key(),operation=pending;busy=true;render();onActivityChange();
    try{
      const result=await api.request(operation.path+'/refreshes/by-request/'+encodeURIComponent(operation.body.request_id));
      if(!valid(token)||pending!==operation)return false;
      if(result===null){tell('尚未查到本次授权结果。保留了本次编号，可稍后再次查找。');return false;}
      if(!receiptMatches(result,operation))throw {code:'NETWORK_UNKNOWN',status:0};
      pending=null;await refresh();
      if(valid(token))tell('已找到本次授权回执；当前可用状态以上方重新读取结果为准。');
      return true;
    }catch(error){if(valid(token))failure(error);return false;}
    finally{if(valid(token)){busy=false;render();onActivityChange();}}
  }
  byId('weixin-authorize').addEventListener('click',authorize);
  byId('weixin-read').addEventListener('click',refresh);
  byId('weixin-find').addEventListener('click',find);
  render();
  return {
    refresh,updateControls:render,projection:()=>data,hasPending:()=>busy||!!pending,
    state(state){
      if(closed)return;
      if(state.status==='revoked'){revoked=true;cid=null;clear();tell('当前权限已变化。');return;}
      if(state.id!==cid){clear();cid=state.id;tell('');}
      const next=JSON.stringify([cid,state.view?.scope,state.materials?.scope]);
      if(next!==signature){signature=next;if(cid)void refresh();}
      render();
    },
    dispose(){closed=true;clear();},
  };
}
