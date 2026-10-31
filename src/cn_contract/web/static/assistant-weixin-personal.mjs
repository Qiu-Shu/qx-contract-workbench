const labels={disconnected:'未连接',starting:'正在准备连接',waiting_scan:'等待本人扫码',
  need_verifycode:'等待验证码',connected:'已连接',paused:'已暂停'};
export function bindPersonalWeixin({controller,bridge,document=globalThis.document,readonly=false,
  isBlocked=()=>false,onIncoming=()=>{},onHistory=()=>{},onOpen=null,setTimer=setTimeout,clearTimer=clearTimeout}){
  const at=id=>document.getElementById('personal-weixin-'+id);
  const available=Boolean(bridge&&['Start','Disable','Verify','Status'].every(key=>typeof bridge['personalWeixin'+key]==='function'));
  let cid=null,epoch=0,connection=null,known=false,busy=false,reading=false,closed=false,timer=null,qrFailed=false,statusRead=null,jevAvailable=false,batches=[],batchKey=null;
  const active=()=>!closed&&controller.state.status!=='revoked';
  const stable=()=>active()&&!controller.state.loading&&!controller.state.conflict&&!controller.state.materialAction&&
    !['saving','error'].includes(controller.state.status);
  const valid=version=>active()&&version===epoch;
  const tell=text=>{at('notice').textContent=text;};
  function render(){
    const state=connection?.state||'disconnected';
    at('panel').setAttribute('aria-busy',String(busy));
    at('summary').textContent=!available?'仅桌面可连接':readonly?'恢复副本只读':!known?'正在核对连接…':labels[state];
    at('state').textContent=!available?'请在桌面工作台连接本人微信。':readonly?'恢复副本保留历史记录；不能连接微信。':
      !known?'连接状态尚未确认，请重新读取。':connection?.notice||labels[state];
    const latest=batches.find(row=>row.conversation_id);
    at('origin').hidden=!latest;
    if(latest){at('origin').href='/assistant/'+latest.conversation_id;at('origin').textContent='打开最新活动事项';}
    const stages={collecting:'收集中',held:'等待补充',clarify:'待澄清',waiting:'等待处理',routed:'已关联事项',executing:'分析中',completed:'已完成'};
    at('batches').textContent=batches.length?'最近收件：'+(stages[batches[0].state]||'待核对')+' · '+batches.length+' 批':'尚无本次连接收件。';
    at('judge').textContent=!known?'辅助判断状态待核对':jevAvailable?'Jev 辅助已配置 · 凭据有效性尚待实际请求核对':'Jev 未启用 · 使用本地规则';
    at('scope').textContent=connection?'微信连接当前工作区，切换聊天仍保持连接。'+
      (connection.automatic?' 收齐材料后自动分析。':' 自动分析已关闭；只接收材料。'):
      '连接后按事项接收消息与成果。关闭程序或退出登录后需重新扫码。';
    const reconnect=state==='paused';
    const reason=!available?'请在桌面工作台连接。':readonly?'恢复副本只读。':!active()?'登录已失效。':busy?'正在处理连接操作，请稍候。':
      !known?'连接状态尚未确认，请重新读取。':connection&&!reconnect?'已有连接；需要重新扫码时请先断开。':'';
    at('start').disabled=Boolean(reason);
    at('start').title=reason;
    at('start').textContent=busy?'正在处理…':reconnect?'重新连接本人微信':'连接本人微信';
    if(reason&&!busy&&known&&!connection)at('state').textContent=(connection?.notice||labels[state])+' · '+reason;
    at('disable').hidden=!connection;
    // Background reads must not animate the controls as if the user pressed them.
    at('disable').disabled=!available||readonly||busy||!active();
    at('refresh').disabled=!available||readonly||busy||!active();
    const verify=known&&state==='need_verifycode';
    at('verify-form').hidden=!verify;at('code').disabled=!verify||busy;
    at('verify').disabled=!verify||busy;
    if(!verify)at('code').value='';
    const qr=known&&state==='waiting_scan'&&connection.qr_ready&&!qrFailed;
    at('qr-frame').hidden=!qr;
    if(qr){const src='/api/assistant/personal-weixin/qr.svg';
      if(at('qr').getAttribute('src')!==src)at('qr').setAttribute('src',src);
    }else at('qr').removeAttribute('src');
  }
  function schedule(){
    clearTimer(timer);timer=null;
    if(active()&&available&&!readonly)timer=setTimer(()=>{timer=null;void refresh();},2500);
  }
  async function refresh(retryQr=false){
    if(!active()||!available||readonly||busy||reading){schedule();return false;}
    const version=epoch;reading=true;render();
    try{
      const result=await (statusRead=bridge.personalWeixinStatus());
      if(!valid(version))return false;
      const next=result?.connection;
      if(result?.ok!==true||next&&(next.conversation_id!==null||!Object.hasOwn(labels,next.state)))throw new Error();
      // Only an explicit read retries a failed image; background polling must not create a retry loop.
      if(retryQr||next?.state!=='waiting_scan')qrFailed=false;
      connection=next;known=true;jevAvailable=result.jev_available===true;batches=Array.isArray(result.batches)?result.batches:[];render();
      const nextKey=JSON.stringify(batches);
      if(nextKey!==batchKey){batchKey=nextKey;await onHistory();}
      // Reads reuse the controller's conflict handling and never submit a model request.
      if(cid&&batches.some(row=>row.conversation_id===cid)&&stable()&&!isBlocked())await onIncoming();
      return true;
    }catch{if(valid(version)){known=false;render();tell('暂未确认连接状态。请重新读取；不要重复连接。');}return false;}
    finally{statusRead=null;reading=false;if(active()){render();schedule();}}
  }
  async function perform(operation){
    if(!active()||busy||readonly||!available)return false;
    if(operation==='Disable'&&!connection)return false;
    if(operation==='Verify'&&reading)return false;
    if(operation==='Start'&&(!known||connection&&connection.state!=='paused'))return false;
    if(operation==='Verify'&&(connection?.state!=='need_verifycode'))return false;
    const code=at('code').value;
    if(operation==='Verify'&&!/^[0-9]{4,12}$/.test(code)){tell('请输入 4 至 12 位数字验证码。');at('code').focus();return false;}
    const version=epoch;busy=true;clearTimer(timer);render();tell('正在处理本次操作…');
    try{
      // A click during a poll waits for that read; it never starts from unknown status.
      if(statusRead)await statusRead;
      if(!valid(version))return false;
      if(operation==='Disable'&&!connection)return false;
      if(operation==='Start'){
        if(!known)return false;
        const read=await bridge.personalWeixinStatus();
        if(!valid(version))return false;
        const next=read?.connection;
        if(read?.ok!==true||next&&(next.conversation_id!==null||!Object.hasOwn(labels,next.state)))throw new Error();
        connection=next;known=true;
        if(next){
          if(next.state!=='paused')return false;
          const disabled=await bridge.personalWeixinDisable();
          if(!valid(version)||disabled?.ok!==true)throw new Error();
          const cleared=await bridge.personalWeixinStatus();
          if(!valid(version)||cleared?.ok!==true||cleared.connection)throw new Error();
          connection=null;
        }
      }
      if(!valid(version))return false;
      const result=await bridge['personalWeixin'+operation](...(operation==='Verify'?[code]:[]));
      if(!valid(version))return false;
      if(result?.ok!==true)throw new Error();
      if(operation==='Disable')connection=null;
      at('code').value='';tell(operation==='Disable'?'已断开连接，聊天与材料记录保留。':'已提交，正在读取状态…');
      if(operation==='Start')at('panel').open=true;
      return true;
    }catch{if(valid(version)){known=false;tell('本次操作未确认。请重新读取连接状态后处理。');}return false;}
    finally{busy=false;if(active()){render();void refresh();}}
  }
  at('origin').addEventListener('click',event=>{if(onOpen){event.preventDefault();const latest=batches.find(row=>row.conversation_id);if(latest)onOpen(latest.conversation_id);}});
  at('start').addEventListener('click',()=>perform('Start'));
  at('disable').addEventListener('click',()=>perform('Disable'));
  at('refresh').addEventListener('click',()=>refresh(true));
  at('verify-form').addEventListener('submit',event=>{event.preventDefault();void perform('Verify');});
  at('panel').addEventListener('toggle',()=>{if(!at('panel').open)at('code').value='';});
  at('qr').addEventListener('error',()=>{qrFailed=true;at('qr').removeAttribute('src');at('qr-frame').hidden=true;tell('二维码暂未显示。请重新读取状态；过期后断开并重新连接。');});
  return {refresh,hasPending:()=>busy,
    state(state){
      if(closed)return;
      if(state.id!==cid){cid=state.id;schedule();}
      if(state.status==='revoked'){++epoch;connection=null;batches=[];jevAvailable=false;batchKey=null;known=false;clearTimer(timer);at('code').value='';}
      render();
    },
    dispose(){closed=true;++epoch;clearTimer(timer);at('code').value='';at('qr').removeAttribute('src');},
  };
}
