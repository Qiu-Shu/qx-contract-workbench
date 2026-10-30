const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const labels={disconnected:'未连接',starting:'正在准备连接',waiting_scan:'等待本人扫码',
  need_verifycode:'等待验证码',connected:'已连接',paused:'已暂停'};
export function bindPersonalWeixin({controller,bridge,document=globalThis.document,readonly=false,
  isBlocked=()=>false,onIncoming=()=>{},setTimer=setTimeout,clearTimer=clearTimeout}){
  const at=id=>document.getElementById('personal-weixin-'+id);
  const available=Boolean(bridge&&['Start','Disable','Verify','Status'].every(key=>typeof bridge['personalWeixin'+key]==='function'));
  let cid=null,epoch=0,connection=null,known=false,busy=false,reading=false,closed=false,timer=null,qrFailed=false,statusRead=null;
  const active=()=>!closed&&controller.state.status!=='revoked';
  const stable=()=>active()&&!controller.state.loading&&!controller.state.conflict&&!controller.state.materialAction&&
    !['saving','error'].includes(controller.state.status);
  const valid=(version,id)=>active()&&version===epoch&&id===cid;
  const tell=text=>{at('notice').textContent=text;};
  function render(){
    const state=connection?.state||'disconnected',here=connection?.conversation_id===cid;
    at('panel').setAttribute('aria-busy',String(busy||reading));
    at('summary').textContent=!available?'仅桌面可连接':readonly?'恢复副本只读':!known?'正在核对连接…':
      (labels[state]||'状态待核对')+(connection&&!here?' · 原聊天':'');
    at('state').textContent=!available?'请在桌面工作台连接本人微信。':readonly?'恢复副本保留历史记录；不能连接微信。':
      !known?'连接状态尚未确认，请重新读取。':connection?.notice||labels[state];
    at('origin').hidden=!connection||here;
    if(connection){at('origin').href='/assistant/'+connection.conversation_id;
      at('origin').textContent='返回连接所在聊天（'+connection.conversation_id.slice(0,8)+'）';}
    at('scope').textContent=connection?(here?'微信消息固定接收到当前聊天。':'微信仍连接到原聊天，当前聊天不会接收该连接的消息。')+
      (connection.automatic?' 已启用设置中的当前任务材料自动分析；每次请求仍受预算保护。':' 自动分析未开启；收件后请在桌面确认。'):
      '连接后，微信收件和成果保存在本次聊天。关闭程序或退出登录后需重新扫码。';
    const reconnect=here&&state==='paused';
    const reason=!available?'请在桌面工作台连接。':readonly?'恢复副本只读。':busy?'正在处理连接操作，请稍候。':
      !known?'连接状态尚未确认，请重新读取。':connection&&!reconnect?
        (here?'已有连接；需要重新扫码时请先断开。':'请返回原聊天处理连接，或先断开原连接。'):
      !stable()?'请先保存草稿或处理当前错误、冲突。':isBlocked()?'请先保存或清空待传材料及未完成操作。':'';
    at('start').disabled=Boolean(reason);
    at('start').title=reason;
    at('start').textContent=busy?'正在处理…':reconnect?'重新连接本人微信':'连接本人微信';
    if(reason&&!busy&&known)at('state').textContent=(connection?.notice||labels[state])+' · '+reason;
    at('disable').hidden=!connection;
    at('disable').disabled=!available||readonly||busy||reading;
    at('refresh').disabled=!available||readonly||busy||reading;
    const verify=known&&here&&state==='need_verifycode';
    at('verify-form').hidden=!verify;at('code').disabled=!verify||busy;
    at('verify').disabled=!verify||busy;
    if(!verify)at('code').value='';
    const qr=known&&here&&state==='waiting_scan'&&connection.qr_ready&&!qrFailed;
    at('qr-frame').hidden=!qr;
    if(qr){const src='/api/assistant/conversations/'+cid+'/personal-weixin/qr.svg';
      if(at('qr').getAttribute('src')!==src)at('qr').setAttribute('src',src);
    }else at('qr').removeAttribute('src');
  }
  function schedule(){
    clearTimer(timer);timer=null;
    if(active()&&available&&!readonly)timer=setTimer(()=>{timer=null;void refresh();},2500);
  }
  async function refresh(retryQr=false){
    if(!active()||!available||readonly||busy||reading){schedule();return false;}
    const version=epoch,id=cid;reading=true;render();
    try{
      const result=await (statusRead=bridge.personalWeixinStatus());
      if(!valid(version,id))return false;
      const next=result?.connection;
      if(result?.ok!==true||next&&(!UUID.test(next.conversation_id)||!Object.hasOwn(labels,next.state)))throw new Error();
      // Only an explicit read retries a failed image; background polling must not create a retry loop.
      if(retryQr||next?.state!=='waiting_scan')qrFailed=false;
      connection=next;known=true;render();
      // Reads reuse the controller's conflict handling and never submit a model request.
      if(connection?.conversation_id===cid&&stable()&&!isBlocked())await onIncoming();
      return true;
    }catch{if(valid(version,id)){known=false;render();tell('暂未确认连接状态。请重新读取；不要重复连接。');}return false;}
    finally{statusRead=null;reading=false;if(active()){render();schedule();}}
  }
  async function perform(operation){
    if(!active()||busy||readonly||!available)return false;
    if(operation!=='Start'&&reading)return false;
    if(operation==='Start'&&(!known||connection&&!(connection.conversation_id===cid&&connection.state==='paused')||!stable()||isBlocked()))return false;
    if(operation==='Verify'&&(connection?.conversation_id!==cid||connection?.state!=='need_verifycode'))return false;
    const code=at('code').value;
    if(operation==='Verify'&&!/^[0-9]{4,12}$/.test(code)){tell('请输入 4 至 12 位数字验证码。');at('code').focus();return false;}
    let version=epoch,id=cid;busy=true;clearTimer(timer);render();tell('正在处理本次操作…');
    try{
      // A click during a poll waits for that read; it never starts from unknown status.
      if(statusRead)await statusRead;
      if(!valid(version,id))return false;
      if(operation==='Start'){
        if(!known||!stable()||isBlocked())return false;
        if(!cid){
          if(!await controller.ensureConversation())throw new Error();
          if(!active()||!controller.state.id||controller.state.id!==cid||id!==null)throw new Error();
          version=epoch;id=cid;
        }else if(!await controller.save())throw new Error();
        if(!valid(version,id)||!stable()||isBlocked())return false;
        const read=await bridge.personalWeixinStatus();
        if(!valid(version,id))return false;
        const next=read?.connection;
        if(read?.ok!==true||next&&(!UUID.test(next.conversation_id)||!Object.hasOwn(labels,next.state)))throw new Error();
        connection=next;known=true;
        if(next){
          if(next.conversation_id!==id||next.state!=='paused')return false;
          const disabled=await bridge.personalWeixinDisable();
          if(!valid(version,id)||disabled?.ok!==true)throw new Error();
          const cleared=await bridge.personalWeixinStatus();
          if(!valid(version,id)||cleared?.ok!==true||cleared.connection)throw new Error();
          connection=null;
        }
      }
      if(!valid(version,id))return false;
      const result=await bridge['personalWeixin'+operation](...(operation==='Verify'?[code]:[]));
      if(!valid(version,id))return false;
      if(result?.ok!==true)throw new Error();
      at('code').value='';tell(operation==='Disable'?'已断开连接，聊天与材料记录保留。':'已提交，正在读取状态…');
      if(operation==='Start')at('panel').open=true;
      return true;
    }catch{if(valid(version,id)){known=false;tell('本次操作未确认。请重新读取连接状态后处理。');}return false;}
    finally{busy=false;if(active()){render();void refresh();}}
  }
  at('start').addEventListener('click',()=>perform('Start'));
  at('disable').addEventListener('click',()=>perform('Disable'));
  at('refresh').addEventListener('click',()=>refresh(true));
  at('verify-form').addEventListener('submit',event=>{event.preventDefault();void perform('Verify');});
  at('panel').addEventListener('toggle',()=>{if(!at('panel').open)at('code').value='';});
  at('qr').addEventListener('error',()=>{qrFailed=true;at('qr').removeAttribute('src');at('qr-frame').hidden=true;tell('二维码暂未显示。请重新读取状态；过期后断开并重新连接。');});
  return {refresh,hasPending:()=>busy,
    state(state){
      if(closed)return;
      if(state.id!==cid){cid=state.id;++epoch;known=false;qrFailed=false;at('code').value='';schedule();}
      if(state.status==='revoked'){++epoch;connection=null;known=false;clearTimer(timer);at('code').value='';}
      render();
    },
    dispose(){closed=true;++epoch;clearTimer(timer);at('code').value='';at('qr').removeAttribute('src');},
  };
}
