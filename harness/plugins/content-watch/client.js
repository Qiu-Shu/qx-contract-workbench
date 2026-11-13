// Mounted by the resident desktop client. Entered credentials stay in memory only until saved.
window.qxInstallContentWatch=function(ctx,React){
  const h=React.createElement,panels=new Set();let disposed=false;
  const stylesheet=document.createElement('link');stylesheet.rel='stylesheet';stylesheet.href='/api/qx-content-watch/panel.css';document.head.append(stylesheet);
  const labels={unconfigured:'填写业务方向后开始',ready:'等待下次整理',running:'正在整理',login_required:'需要重新扫码',unavailable:'小红书暂未连接',error:'上次整理未完成',paused:'已暂停',token_required:'请填写 API 凭据',token_invalid:'API 凭据无效',rate_limited:'服务请求过于频繁',quota_exceeded:'服务额度不足',budget_exceeded:'服务余额或 Token 预算不足',provider_unavailable:'采集服务暂时不可用',model_required:'请配置摘要模型'};
  const providerMessages={token_required:'请填写并保存 JustOneAPI Token，再开始整理。',token_invalid:'JustOneAPI 凭据无效或已失效，请更新 Token 后保存连接。',rate_limited:'JustOneAPI 请求过于频繁，请稍后重试。',quota_exceeded:'JustOneAPI 额度不足，请在服务商账户中检查额度。',budget_exceeded:'JustOneAPI 账户余额或 Token 预算不足，请在服务商账户中检查。',provider_unavailable:'JustOneAPI 暂时无法连接，请稍后重试。'};
  const when=value=>{if(!value)return '尚未安排';const date=new Date(value);return Number.isNaN(date.getTime())?'尚未安排':date.toLocaleString('zh-CN',{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'});};
  function qrSource(value){
    return typeof value==='string'&&value.length<=2*1024*1024&&/^data:image\/(?:png|jpeg);base64,[a-zA-Z0-9+/]+={0,2}$/.test(value)?value:null;
  }
  async function api(path,body,signal){
    const response=await fetch('/api/qx-content-watch/'+path,{credentials:'same-origin',cache:'no-store',signal,headers:{'x-qx-content-watch':'1',...(body?{'content-type':'application/json'}:{})},
      ...(body?{method:'POST',body:JSON.stringify(body)}:{})});
    if(response.status===401||response.status===403)throw Error('工作台连接已失效，请从“工作台 → 重新连接”恢复。');
    if(!response.headers.get('content-type')?.includes('application/json'))throw Error('拓客内容暂时无法连接，请稍后重试。');
    const data=await response.json();if(!response.ok)throw Error(typeof data.error==='string'?data.error:'操作未完成，请稍后重试。');
    return data;
  }
  function Panel({onClose}){
    const [state,setState]=React.useState(null),[practice,setPractice]=React.useState(''),[targetClients,setTargetClients]=React.useState('');
    const [provider,setProvider]=React.useState('justone'),[token,setToken]=React.useState('');
    const [loading,setLoading]=React.useState(true),[busy,setBusy]=React.useState(false),[error,setError]=React.useState(''),[loadError,setLoadError]=React.useState(''),[notice,setNotice]=React.useState(''),[qr,setQr]=React.useState(null);
    const dialog=React.useRef(null),alive=React.useRef(false),working=React.useRef(false),reading=React.useRef(false),loaded=React.useRef(false),dirty=React.useRef(false),connectionDirty=React.useRef(false),version=React.useRef(0),connection=React.useRef(null);
    function accept(next,syncProfile=false,syncConnection=false){
      if(!alive.current)return;setState(next);
      if(syncProfile||!loaded.current&&!dirty.current){setPractice(next.profile?.practice||'');setTargetClients(next.profile?.targetClients||'');loaded.current=true;}
      if(syncConnection||!connectionDirty.current)setProvider(next.connection?.provider||'justone');
      if(next.connection?.provider!=='local-xhs'||next.login?.loggedIn)setQr(null);
    }
    async function refresh(){
      if(!alive.current||working.current||reading.current||document.visibilityState==='hidden')return;
      reading.current=true;const stamp=++version.current;
      try{const next=await api('status',undefined,connection.current.signal);if(alive.current&&stamp===version.current){accept(next);setLoadError('');}}
      catch(error){if(alive.current&&stamp===version.current&&error.name!=='AbortError')setLoadError(error.message);}
      finally{reading.current=false;if(alive.current)setLoading(false);}
    }
    async function run(action,body,path=body?'profile':'action'){
      if(working.current||!alive.current)return;working.current=true;version.current++;setBusy(true);setError('');setNotice('');
      try{
        let next=await api(path,body||{action},connection.current.signal);if(!alive.current)return;
        accept(next,path==='profile',path==='connection');setLoadError('');
        if(path==='connection'){
          connectionDirty.current=false;setToken('');setQr(null);
          setNotice('已保存连接设置。');
          next=await api('action',{action:'check-login'},connection.current.signal);if(!alive.current)return;accept(next);
          if(next.connection?.provider==='justone')setNotice(next.connection.tokenConfigured?'已保存 API 凭据；首次整理时验证服务连接。':'已保存连接设置，请填写 API 凭据。');
          else setNotice(next.login?.loggedIn?'小红书已连接。':'已保存本机采集设置，请连接小红书并扫码。');
        }
        else if(path==='profile'){dirty.current=false;setNotice('已保存。每 3 天整理一次，结果进入专用会话。');}
        else if(action==='draft'){
          if(next.sessionId){ctx.uiWorkspace.openSession(next.sessionId);onClose();}
          else setNotice('已提交选题，请稍后查看整理会话。');
        }
        else if(action==='login'){
          if(next.qr?.isLoggedIn||next.login?.loggedIn){setQr(null);setNotice('小红书已连接。');}
          else{const img=qrSource(next.qr?.img);setQr(img?{img}:null);if(!img)setError('二维码暂时无法显示，请重新获取。');}
        }
        else if(action==='check-login')setNotice(next.connection?.provider==='justone'?(next.connection.tokenConfigured?'API 凭据已保存在本机；首次整理时验证服务连接。':'请填写并保存 API 凭据。'):(next.login?.loggedIn?'小红书已连接，可以开始整理。':'尚未确认登录，请完成手机扫码后再检查。'));
        else if(action==='prepare')setNotice(next.status==='running'?'正在准备连接组件，请稍后查看连接状态。':'已完成连接准备，请连接小红书并扫码。');
      }catch(error){if(alive.current&&error.name!=='AbortError')setError(error.message);}
      finally{working.current=false;if(alive.current)setBusy(false);}
    }
    React.useEffect(()=>{
      alive.current=true;const control=new AbortController();connection.current=control;
      const timer=setInterval(()=>void refresh(),5000);
      const cleanup=()=>{alive.current=false;control.abort();clearInterval(timer);panels.delete(cleanup);};panels.add(cleanup);
      if(dialog.current&&!dialog.current.open)dialog.current.showModal();void refresh();return cleanup;
    },[]);
    const configured=Boolean(state?.profile),running=state?.status==='running',unavailable=state?.status==='unavailable',blocked=busy||running||Boolean(state?.scriptPending);
    const loggedIn=Boolean(state?.login?.loggedIn),expired=state?.status==='login_required';
    const apiSelected=provider==='justone',savedProvider=state?.connection?.provider||'justone',unsavedConnection=connectionDirty.current;
    const tokenConfigured=Boolean(state?.connection?.tokenConfigured),canCollect=savedProvider==='justone'?tokenConfigured&&!['token_required','token_invalid'].includes(state?.status):loggedIn;
    const unsavedProfile=configured&&(practice.trim()!==state.profile.practice||targetClients.trim()!==state.profile.targetClients);
    const retrySaved=Boolean(state?.lastReport?.pending&&state.lastReport.submitted===false&&state.lastReport.profile&&configured&&state.lastReport.profile.practice===state.profile.practice&&state.lastReport.profile.targetClients===state.profile.targetClients);
    const taskMessage=state?.message||(state?.status==='model_required'?'请先在工作台选择并配置摘要模型，再重试整理。':'');
    const field=(label,value,set,placeholder)=>h('label',{className:'qx-content-field'},h('span',null,label),h('textarea',{value,required:true,maxLength:500,rows:2,'aria-label':label,placeholder,disabled:blocked,onChange:e=>{dirty.current=true;set(e.target.value);}}));
    return h('dialog',{className:'qx-content-panel',ref:dialog,'aria-labelledby':'qx-content-heading',onCancel:e=>{e.preventDefault();onClose();}},
      h('header',{className:'qx-content-header'},h('div',null,h('h2',{id:'qx-content-heading'},'拓客内容'),h('p',null,'从行业内容中，找到值得回答的客户问题')),h('button',{type:'button',className:'qx-content-close','aria-label':'关闭拓客内容',onClick:onClose},'×')),
      h('div',{className:'qx-content-body'},
        h('div',{className:'qx-content-cadence'},h('strong',null,'每 3 天'),h('span',null,'小红书内容观察 → 工作台专用会话')),
        h('p',{className:'qx-content-muted'},'填写你擅长的业务和希望服务的客户。无需先准备知识库资料。'),
        h('p',{className:'qx-content-muted'},'业务方向和客户类型将用于平台搜索，请填写公开类别，不填案件详情或当事人信息。'),
        h('form',{onSubmit:e=>{e.preventDefault();if(practice.trim()&&targetClients.trim())return run(null,{practice:practice.trim(),targetClients:targetClients.trim(),enabled:true});}},
          field('业务方向',practice,setPractice,'例如：劳动用工、公司治理、婚姻家事'),field('目标客户',targetClients,setTargetClients,'例如：中小企业负责人、人力资源负责人'),
          h('p',{className:'qx-content-muted'},'保存后启用每 3 天（72 小时）整理。摘要使用当前模型，沿用现有用量设置；请保持电脑开机、联网且不休眠。'),
          h('div',{className:'qx-content-actions'},h('button',{type:'submit',className:'qx-content-primary',disabled:blocked||!practice.trim()||!targetClients.trim()},busy?'正在处理…':'保存并启用'))),
        h('section',{className:'qx-content-connection','aria-label':'小红书连接'},h('div',{className:'qx-content-section-heading'},h('h3',null,'小红书采集连接'),h('span',{className:'qx-content-status','data-status':state?.status||'unconfigured'},unsavedConnection?'连接设置待保存':apiSelected?(tokenConfigured?'API 凭据已保存':'尚未设置 API 凭据'):loggedIn?'已连接'+(state.login.username?' · '+state.login.username:''):expired?'登录已过期':'尚未连接')),
          h('label',{className:'qx-content-field'},h('span',null,'采集方式'),h('select',{'aria-label':'采集方式',value:provider,disabled:blocked,onChange:e=>{connectionDirty.current=true;setProvider(e.target.value);setQr(null);setNotice('');}},h('option',{value:'justone'},'JustOneAPI'),h('option',{value:'local-xhs'},'本机扫码采集'))),
          apiSelected?h(React.Fragment,null,
            h('label',{className:'qx-content-field'},h('span',null,'JustOneAPI Token'),h('input',{type:'password','aria-label':'JustOneAPI Token',value:token,autoComplete:'off',spellCheck:false,maxLength:4096,placeholder:tokenConfigured?'已配置；留空保留现有 Token':'输入 JustOneAPI Token',disabled:blocked,onChange:e=>{connectionDirty.current=true;setToken(e.target.value);setNotice('');}})),
            h('p',{className:'qx-content-muted'},'Token 仅提交到本机服务，不保存在浏览器中。保存只检查是否已填写；服务连接在首次整理时验证。'),
            tokenConfigured&&state?.connection?.secretStorage==='dpapi'&&h('p',{className:'qx-content-muted'},'凭据保存：Windows 系统账号保护。'),
            tokenConfigured&&state?.connection?.secretStorage==='restricted-file'&&h('p',{className:'qx-content-muted'},'凭据保存：本机受限文件（本系统未加密）。'),
            h('p',{className:'qx-content-muted'},'JustOneAPI 按调用计费，整理摘要另使用当前模型的用量。保存连接设置不会启用或立即执行采集。'),
            providerMessages[state?.status]&&h('p',{className:'qx-content-notice qx-content-error',role:'status'},providerMessages[state.status])):
            h('p',{className:'qx-content-muted'},expired?'采集已暂停。重新扫码后继续，已保存的整理内容会保留。':'使用小红书扫码连接，登录信息保存在本机。'),
          h('div',{className:'qx-content-actions'},h('button',{type:'button',disabled:blocked,onClick:()=>run(null,{provider,...(apiSelected&&token.trim()?{token:token.trim()}:{})},'connection')},'保存连接设置'),
            !apiSelected&&unavailable&&h('button',{type:'button',disabled:blocked||unsavedConnection,onClick:()=>run('prepare')},'准备小红书连接'),
            !apiSelected&&h('button',{type:'button',disabled:blocked||unsavedConnection,onClick:()=>run('login')},expired?'重新扫码':loggedIn?'更换登录':'连接小红书'),
            !apiSelected&&h('button',{type:'button',disabled:blocked||unsavedConnection,onClick:()=>run('check-login')},qr?'我已扫码，检查连接':'检查连接')),
          !apiSelected&&qr&&h('div',{className:'qx-content-qr'},h('img',{src:qr.img,alt:'小红书登录二维码',width:200,height:200}),h('p',null,'用小红书扫码并在手机上确认。完成后点击“我已扫码，检查连接”。'))),
        h('section',{className:'qx-content-task','aria-label':'整理任务'},h('div',{className:'qx-content-section-heading'},h('h3',null,'整理安排'),h('span',{className:'qx-content-status','data-status':state?.status||'unconfigured'},loading?'正在读取…':labels[state?.status]||'暂未取得状态')),
          h('dl',null,h('div',null,h('dt',null,'下次整理'),h('dd',null,state?.enabled?when(state.nextRunAt):'已暂停或尚未启用')),h('div',null,h('dt',null,'上次整理'),h('dd',null,state?.lastRunAt?when(state.lastRunAt):'尚无整理记录'))),
          taskMessage&&h('p',{className:'qx-content-muted'},taskMessage),
          unsavedProfile&&h('p',{className:'qx-content-muted'},'业务方向或目标客户已修改，请先保存再整理。'),
          h('div',{className:'qx-content-actions'},h('button',{type:'button',className:'qx-content-primary',disabled:blocked||!configured||(!canCollect&&!retrySaved)||unsavedConnection||unsavedProfile,onClick:()=>retrySaved?run('run',{action:'run',retryReportId:state.lastReport.id},'action'):run('run')},running?'正在整理…':retrySaved?'重试整理已保存内容':'立即整理'),
            h('button',{type:'button',disabled:blocked||!configured,onClick:()=>run(state?.enabled?'pause':'resume')},state?.enabled?'暂停整理':'恢复整理'),
            state?.sessionId&&h('button',{type:'button',disabled:busy||!state?.lastReport,onClick:()=>{ctx.uiWorkspace.openSession(state.sessionId);onClose();}},'查看整理会话'))),
        (error||loadError)&&h('p',{role:'alert',className:'qx-content-notice qx-content-error'},error||loadError),notice&&h('p',{role:'status',className:'qx-content-notice'},notice),
        state?.lastReport&&h('section',{className:'qx-content-report','aria-label':'最近整理'},h('h3',null,'最近整理'),h('p',null,state.lastReport.title||'小红书内容观察'),h('p',{className:'qx-content-muted'},when(state.lastReport.createdAt)),typeof state.lastReport.content==='string'&&h('details',null,h('summary',null,'查看已保存的报告'),h('pre',null,state.lastReport.content)),
          state.lastReport.items?.length>0&&h('div',{className:'qx-content-topics'},h('p',{className:'qx-content-muted'},'选择一个选题，生成原创口播与拍摄稿。仅依据已取得的标题、简介或正文，不代表已读取视频完整口播。'),
            state.lastReport.items.map(item=>h('div',{className:'qx-content-topic',key:item.id},h('span',null,item.title||'未取得标题'),h('button',{type:'button',disabled:blocked,onClick:()=>run('draft',{action:'draft',reportId:state.lastReport.id,itemId:item.id},'action')},'生成口播与拍摄稿')))),
          state.scriptPending&&h('p',{className:'qx-content-muted',role:'status'},'正在生成口播与拍摄稿，请到整理会话查看进度。')),
        h('p',{className:'qx-content-footnote'},'每期保留来源、采集时间与筛选理由，提供原创选题参考。内容不会自动发布。')));
  }
  function Entry({wide}){
    const [open,setOpen]=React.useState(false);
    return h('div',{className:'qx-content-entry'+(wide?'':' qx-content-entry-compact')},
      h('button',{type:'button',className:'qx-wechat-link qx-content-launcher','aria-label':'拓客内容',title:'拓客内容','aria-haspopup':'dialog',onClick:()=>setOpen(true)},
        h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.6,'aria-hidden':true},h('path',{d:'M5 4h14v16H5V4zm4 4h6m-6 4h6m-6 4h3M2 7h3m-3 5h3m-3 5h3'})),wide&&h('span',null,'拓客内容')),
      open&&h(Panel,{onClose:()=>setOpen(false)}));
  }
  const unregister=ctx.slots.inject('sidebar.footer.action',()=>ctx.slots.register({name:'sidebar.footer.action',id:'qx-content-watch',order:90},Entry));
  return()=>{if(disposed)return;disposed=true;for(const cleanup of [...panels])cleanup();unregister?.();stylesheet.remove();};
};
