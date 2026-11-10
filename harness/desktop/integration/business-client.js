// Loaded by the desktop integration; all actions stay on the resident session/input APIs.
window.qxInstallBusiness=function(ctx,React){
  const h=React.createElement,controller=new AbortController(),disposers=[];
  const modes=[{id:'reception',title:'客户接待',hint:'粘贴客户原话或截图，准备回复并推进下一步',icon:'M4 4h16v11H9l-5 4V4m4 4h8m-8 3h5'},
    {id:'contract',title:'合同审查',hint:'先发合同，再确认我方立场和审查程度',icon:'M14 3H5v18h14V8l-5-5v5h5M8 12h8m-8 4h5'},
    {id:'case',title:'办案整理',hint:'直接发送材料，逐步理清事实、证据和办案目标',icon:'M3 7h7l2 2h9v11H3V7m0 0V4h7l2 3h7v2M7 13h10m-10 3h6'},
    {id:'hearing',title:'模拟法庭',hint:'发送案件材料，确认我方角色后开始演练',icon:'M12 3v17m-6 1h12M4 7h16M6 7l-4 8h8L6 7m12 0-4 8h8l-4-8'},
    {id:'media',title:'律师账号运营',hint:'从账号定位、选题到文稿与拍摄清单，逐步完成',icon:'M3 5h13v14H3V5m13 5 5-3v10l-5-3M7 9l5 3-5 3V9'}];
  const stages={new:'初次接触',consulting:'沟通需求',scheduling:'推进预约',quoted:'已报价',pending:'待委托',engaged:'已委托'};
  let snapshot={states:{},index:[],busy:false,error:''},indexReady=false;const listeners=new Set(),inputs=new Map(),pendingCreations=new Map();
  const publish=patch=>{if(controller.signal.aborted)return;snapshot={...snapshot,...patch};listeners.forEach(fn=>fn());};
  const subscribe=fn=>{listeners.add(fn);return()=>listeners.delete(fn);};
  const useBusiness=()=>React.useSyncExternalStore(subscribe,()=>snapshot);
  const useSessions=()=>React.useSyncExternalStore(fn=>ctx.sessions.list.subscribe(fn),()=>ctx.sessions.list.getSnapshot());
  // A workflow has meaningful state even before its first message. Keep it out of plain-chat reuse.
  const priorReuse=ctx.uiWorkspace.canReuseBlank;
  const canReuseBlank=id=>indexReady&&!snapshot.busy&&!snapshot.states[id]&&!snapshot.index.some(flow=>flow.sessionId===id)&&(priorReuse?.call(ctx.uiWorkspace,id)??true);
  ctx.uiWorkspace.canReuseBlank=canReuseBlank;
  disposers.push(()=>{if(ctx.uiWorkspace.canReuseBlank===canReuseBlank)ctx.uiWorkspace.canReuseBlank=priorReuse;});
  const activeId=()=>Object.values(ctx.sessions.list.getSnapshot().byId).find(row=>(row.retainedBy?.mainView||0)>0)?.id;
  let navigationEpoch=0,lastActive=activeId(),lastWorkspaceId;
  const observeNavigation=()=>{
    const id=activeId();if(id!==lastActive){navigationEpoch++;lastActive=id;}
    const workspace=ctx.get('workspaces')?.list.getSnapshot().items.find(item=>item.sessionIds.includes(id));
    if(workspace)lastWorkspaceId=workspace.workspaceId;
  };
  disposers.push(ctx.sessions.list.subscribe(observeNavigation));observeNavigation();
  async function api(id,body){
    const response=await fetch('/api/qx-business/state'+(id?'?sessionId='+encodeURIComponent(id):''),{credentials:'same-origin',signal:controller.signal,
      ...(body?{method:'POST',headers:{'content-type':'application/json','x-qx-workflow':'1'},body:JSON.stringify(body)}:{})});
    const data=await response.json();if(!response.ok)throw Error(data.error||'业务设置暂不可用');return data;
  }
  function remember(state,id=state?.sessionId){
    if(!id)return;
    if(snapshot.states[id]&&(!state||snapshot.states[id].revision>state.revision))return;
    publish({states:{...snapshot.states,[id]:state},index:state?[...snapshot.index.filter(item=>item.sessionId!==id),state]:snapshot.index});
  }
  async function load(id){const {state}=await api(id);remember(state,id);return state;}
  async function save(id,patch){const old=snapshot.states[id];const {state}=await api(id,{revision:old?.revision||0,...patch});remember(state);return state;}
  function useFlow(id){
    const data=useBusiness();const [error,setError]=React.useState('');
    const reload=React.useCallback(()=>{let live=true;setError('');load(id).catch(e=>{if(live&&!controller.signal.aborted)setError(e.message)});return()=>{live=false};},[id]);
    React.useEffect(reload,[reload]);return {state:data.states[id],error,reload};
  }
  async function create(mode,extra){
    if(snapshot.busy)return;const before=activeId(),epoch=navigationEpoch,current=ctx.sessions.list.getSnapshot().byId[before];
    if(extra&&(typeof extra.summary!=='string'||!extra.summary.trim()||extra.summary.length>12000))throw Error('交接摘要须为 1–12000 字。');
    if(extra&&extra.sourceSessionId!==before)throw Error('接待对话已切换，请回到原对话确认交接。');
    publish({busy:true,error:''});
    try{
      const workspaces=ctx.get('workspaces')?.list.getSnapshot().items||[];
      const workspace=workspaces.find(item=>item.sessionIds.includes(before))||workspaces.find(item=>item.path===current?.cwd)||workspaces.find(item=>item.workspaceId===lastWorkspaceId)||(workspaces.length===1?workspaces[0]:undefined);
      if(!workspace)throw Error('请先在工作区中选择或添加一个文件夹，再新建业务对话。');
      if(!extra&&current?.blank&&snapshot.states[before]?.mode===mode&&workspace.sessionIds.includes(before)){ctx.uiWorkspace.openSession(before);return before;}
      const key=JSON.stringify([workspace.workspaceId,mode,extra]);
      let id=pendingCreations.get(key);
      if(!id||!ctx.sessions.list.getSnapshot().byId[id]?.blank){id=await ctx.sessions.create({workspaceId:workspace.workspaceId,agentPreset:'qunxing'});pendingCreations.set(key,id);}
      const existing=await load(id);
      if(!existing)await save(id,{mode,...extra});
      pendingCreations.delete(key);
      if(activeId()===before&&navigationEpoch===epoch&&!controller.signal.aborted)ctx.uiWorkspace.openSession(id);
      return id;
    }catch(e){if(!controller.signal.aborted)publish({error:e.message});throw e;}
    finally{publish({busy:false});}
  }
  function send(id,text){
    if(activeId()!==id)throw Error('对话已切换，请在原对话中操作。');
    const live=inputs.get(id);
    if(!live||live.input.phase!=='plain'||live.input.draft.trim()||live.input.attachmentIds?.length||ctx.sessions.list.getSnapshot().byId[id]?.running)throw Error('请先发送或保存输入框中的内容，等待本轮回复完成后再操作。');
    live.actions.setDraft(text);live.actions.persistDraft();live.actions.submit();
  }
  const icon=item=>h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.5,strokeLinecap:'round',strokeLinejoin:'round','aria-hidden':true},h('path',{d:item.icon}));
  function Entries({wide=true}){
    const data=useBusiness(),sessions=useSessions(),[expanded,setExpanded]=React.useState(null);
    const current=Object.values(sessions.byId).find(row=>(row.retainedBy?.mainView||0)>0)?.id;
    return h('section',{className:'qx-business-entries','aria-label':'业务入口'},wide&&h('p',{className:'qx-business-eyebrow'},'开始一项工作'),
      modes.map(item=>h('div',{key:item.id},h('div',{className:'qx-business-entry-row'},
        h('button',{type:'button',className:'qx-business-entry',disabled:data.busy,title:item.title,'aria-label':'新建'+item.title+'对话','aria-current':data.states[current]?.mode===item.id?'true':undefined,onClick:()=>{void create(item.id).catch(()=>{})}},icon(item),wide&&h('span',null,item.title),wide&&h('span',{className:'qx-business-plus','aria-hidden':true},'+')),
        wide&&h('button',{type:'button',className:'qx-business-history-toggle','aria-label':item.title+'历史对话','aria-expanded':expanded===item.id,onClick:()=>setExpanded(expanded===item.id?null:item.id)},expanded===item.id?'▴':'▾')),
        wide&&expanded===item.id&&h('div',{className:'qx-business-history'},
          data.index.filter(flow=>flow.mode===item.id&&sessions.byId[flow.sessionId]).sort((a,b)=>(sessions.byId[b.sessionId].updatedAt||b.updatedAt)-(sessions.byId[a.sessionId].updatedAt||a.updatedAt)).map(flow=>h('button',{type:'button',key:flow.sessionId,onClick:()=>ctx.uiWorkspace.openSession(flow.sessionId),'aria-current':current===flow.sessionId?'page':undefined},sessions.byId[flow.sessionId].displayTitle||'新对话')),
          !data.index.some(flow=>flow.mode===item.id&&sessions.byId[flow.sessionId])&&h('p',null,'暂无对话')))),
      data.error&&h('p',{role:'alert',className:'qx-business-error'},data.error));
  }
  function FlowDock({session,input,inputActions}){
    const id=session.sessionId||session.id,{state,error,reload}=useFlow(id),data=useBusiness();
    const [notice,setNotice]=React.useState(''),[busy,setBusy]=React.useState(false),[party,setParty]=React.useState(''),[review,setReview]=React.useState('full'),[focus,setFocus]=React.useState('');
    const [confirmSigned,setConfirmSigned]=React.useState(false),[handoff,setHandoff]=React.useState(false),[summary,setSummary]=React.useState(''),[confirmed,setConfirmed]=React.useState(false),alive=React.useRef(true);
    React.useEffect(()=>{alive.current=true;return()=>{alive.current=false;inputs.delete(id)}},[id]);
    React.useEffect(()=>{inputs.set(id,{input,actions:inputActions});return()=>inputs.delete(id)},[id,input,inputActions]);
    React.useEffect(()=>{if(state){setReview(state.review||'full');setFocus(state.focus||'');setParty(state.party||'');}},[state?.revision]);
    async function act(operation){setBusy(true);setNotice('');try{await operation()}catch(e){if(alive.current)setNotice(e.message)}finally{if(alive.current)setBusy(false)}}
    if(error)return h('section',{className:'qx-business-dock'},h('p',{role:'alert'},error),h('button',{type:'button',onClick:reload},'重试业务设置'));
    if(state===undefined)return h('p',{className:'qx-business-loading',role:'status'},'正在读取业务设置…');
    if(!state)return null;
    const item=modes.find(item=>item.id===state.mode),disabled=busy||data.busy||input.phase!=='plain'||Boolean(session.running);
    const button=(label,fn,extra={})=>h('button',{type:'button',disabled,onClick:()=>void act(fn),...extra},label);
    const title=h('div',{className:'qx-business-dock-title'},h('strong',null,item.title),h('span',null,item.hint));
    let controls=null;
    if(state.mode==='contract')controls=state.confirmed?h('div',{className:'qx-business-controls'},h('span',null,`我方：${state.party} · ${ {quick:'快速审查',full:'全面审查',focused:'重点审查'}[state.review]}`),button('按此选项继续',async()=>send(id,'请按我已确认的立场和程度继续审查。')),button('调整审查选项',()=>save(id,{confirmed:false}))):
      session.blank?h('p',{className:'qx-business-help'},'第一步：把合同拖入或上传后发送。启用脱敏时，请先逐份完成右侧复核。'):
      h('div',null,!state.party?h('div',null,h('p',null,'第二步：我们代表哪一方？'),h('div',{className:'qx-business-controls'},button('甲方',()=>save(id,{party:'甲方'})),button('乙方',()=>save(id,{party:'乙方'})),h('input',{'aria-label':'其他我方立场',placeholder:'其他：填写主体名称或角色',value:party,maxLength:100,onChange:e=>setParty(e.target.value)}),button('确认其他立场',()=>save(id,{party}),{disabled:disabled||!party.trim()}))):
        h('div',null,h('p',null,`第三步：我方为 ${state.party}，需要什么程度的审查？`),h('div',{className:'qx-business-controls'},
          ...[['quick','快速审查'],['full','全面审查（推荐）'],['focused','重点审查']].map(([value,label])=>h('button',{type:'button',disabled,key:value,'aria-pressed':review===value,onClick:()=>setReview(value)},label))),
          h('label',{className:'qx-business-field'},'我方立场',h('input',{value:party,maxLength:100,onChange:e=>setParty(e.target.value),'aria-label':'审查我方立场'})),
          review==='focused'&&h('textarea',{'aria-label':'重点审查事项',placeholder:'例如：付款、违约责任、解除条件',value:focus,maxLength:2000,onChange:e=>setFocus(e.target.value)}),
          button('开始审查',async()=>{if(input.draft.trim()||input.attachmentIds?.length)throw Error('请先发送输入框中的补充材料，再开始审查。');await save(id,{party,review,...review==='focused'?{focus}:{},confirmed:true});send(id,'我方立场和审查程度已确认，请开始审查。');},{className:'qx-business-primary',disabled:disabled||!party.trim()||(review==='focused'&&!focus.trim())})));
    if(state.mode==='reception')controls=h('div',null,h('div',{className:'qx-business-controls'},
      h('label',null,'接待阶段 ',h('select',{'aria-label':'接待阶段',value:state.stage,disabled,onChange:e=>{const value=e.target.value;if(value==='engaged')setConfirmSigned(true);else void act(()=>save(id,{stage:value}));}},Object.entries(stages).map(([value,label])=>h('option',{key:value,value},label)))),
      button('转入办案',async()=>{setHandoff(!handoff);setConfirmed(false)})),
      confirmSigned&&h('div',{className:'qx-business-confirm'},h('p',null,'请核实委托已经成立，再标记为“已委托”。'),button('确认已委托',async()=>{await save(id,{stage:'engaged',confirmEngagement:true});if(alive.current)setConfirmSigned(false)}),button('暂不标记',async()=>setConfirmSigned(false))),
      handoff&&h('div',{className:'qx-business-handoff'},h('label',{className:'qx-business-field'},'办案交接摘要',h('textarea',{'aria-label':'办案交接摘要',placeholder:'填写已核实的当事人、核心事实、目标和材料位置。尚未核实的内容请明确标注。',value:summary,maxLength:12000,onChange:e=>{setSummary(e.target.value);setConfirmed(false)}})),
        h('label',null,h('input',{type:'checkbox',checked:confirmed,onChange:e=>setConfirmed(e.target.checked)}),' 我已核对上述摘要，确认带入办案对话'),button('确认并新建办案对话',()=>create('case',{sourceSessionId:id,summary,confirmHandoff:true}),{disabled:disabled||!confirmed||!summary.trim(),className:'qx-business-primary'})));
    if(state.mode==='case'&&state.summary)controls=h('details',null,h('summary',null,'已确认的接待交接摘要'),h('p',{className:'qx-business-prose'},state.summary));
    return h('section',{className:'qx-business-dock','aria-label':item.title+'业务引导'},title,controls,notice&&h('p',{role:'status',className:'qx-business-error'},notice));
  }
  function Reply(props){
    const id=props.useSession(session=>session.sessionId||session.id),data=useBusiness(),[notice,setNotice]=React.useState('');
    const blocks=props.node?.data?.blocks||[],text=blocks.filter(block=>block.kind==='text').map(block=>block.text).join('');
    const start=text.indexOf('【可发送回复】'),split=text.indexOf('【律师参考】',start+7);
    if(data.states[id]?.mode!=='reception'||start<0||split<0||props.groupPart==='reasoning')return props.renderOriginal();
    const reply=text.slice(start+'【可发送回复】'.length,split).trim(),notes=text.slice(split+'【律师参考】'.length).trim();
    let inserted=false;const visible=blocks.flatMap(block=>{if(block.kind!=='text')return [block];if(inserted)return [];inserted=true;return [{...block,text:reply}];});
    const settled=props.node.data.status==='settled';
    async function action(task){try{await task();}catch(e){setNotice(e.message)}}
    return h('section',{className:'qx-business-reply','aria-label':'客户接待回复'},h('p',{className:'qx-business-eyebrow'},'可发送给客户'),props.renderOriginal({node:{...props.node,data:{...props.node.data,blocks:visible}}}),
      settled&&h('div',{className:'qx-business-controls'},h('button',{type:'button',onClick:()=>void action(async()=>{await navigator.clipboard.writeText(reply);setNotice('已复制客户回复，不含律师参考。')})},'复制回复'),
        h('button',{type:'button',onClick:()=>void action(()=>send(id,'请把以下客户回复缩短，保留关键事实和下一步。待改写文本：'+JSON.stringify(reply)))},'更简短'),
        h('button',{type:'button',onClick:()=>void action(()=>send(id,'请基于当前客户情况，拟一段自然推进预约咨询的回复；未确认的时间和费用不要编造。'))},'推进预约')),
      notes&&h('details',{className:'qx-business-notes'},h('summary',null,'律师参考 · 内部使用'),h('div',{className:'qx-business-prose'},notes)),notice&&h('p',{role:'status'},notice));
  }
  disposers.push(ctx.slots.inject('sidebar.workspaces.business',()=>ctx.slots.register({name:'sidebar.workspaces.business',id:'qx-business-entries',order:0},Entries)));
  disposers.push(ctx.slots.inject('conversation.chat.assistant.business',()=>ctx.slots.register({name:'conversation.chat.assistant.business',priority:-100,select:props=>props},Reply)));
  disposers.push(ctx.slots.inject('conversation.input.dock',()=>ctx.slots.register({name:'conversation.input.dock',id:'qx-business-flow',order:-100},props=>h(FlowDock,{...props,key:props.session.sessionId||props.session.id}))));
  const refresh=()=>api().then(data=>{indexReady=true;publish({index:data.items});}).catch(e=>{if(!controller.signal.aborted)publish({error:e.message})});
  void refresh();window.addEventListener('focus',refresh);disposers.push(()=>window.removeEventListener('focus',refresh));
  const style=document.createElement('style');style.textContent=`
  .qx-business-sidebar{display:flex;flex-direction:column;min-height:0;height:100%;width:100%}.qx-business-native-workspaces{display:flex;flex-direction:column;flex:1;min-height:0;overflow:hidden}.qx-business-entries{padding:6px 8px 12px;border-bottom:1px solid var(--border-color,#e5e5e5);flex-shrink:0;max-height:50vh;overflow:auto}.qx-business-eyebrow{font-size:11px;color:var(--text-secondary,#737373);margin:6px 6px 9px;letter-spacing:.04em}.qx-business-entry-row{display:flex;gap:3px}.qx-business-entry{display:flex;align-items:center;gap:10px;min-height:38px;flex:1;padding:8px;border:0;background:transparent;border-radius:6px;text-align:left;color:inherit;font:inherit;cursor:pointer}.qx-business-entry:hover,.qx-business-entry[aria-current=true]{background:var(--surface-hover,#ece9e3)}.qx-business-plus{margin-left:auto;color:#8a806f}.qx-business-history-toggle{border:0;background:transparent;color:inherit;padding:5px;cursor:pointer}.qx-business-history{padding:2px 4px 4px 27px;max-height:200px;overflow:auto}.qx-business-history button{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;width:100%;border:0;background:transparent;color:inherit;text-align:left;font:inherit;font-size:12px;padding:7px 3px;cursor:pointer}.qx-business-history button:hover,.qx-business-history button[aria-current=page]{background:var(--surface-hover,#ece9e3)}.qx-business-history p{font-size:12px;color:#777}.qx-business-dock{padding:10px 12px;border:1px solid var(--border-color,#ded9cf);border-radius:8px;margin:0 0 8px;background:var(--surface-primary,transparent);font-size:13px}.qx-business-dock-title{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}.qx-business-dock-title span,.qx-business-help,.qx-business-loading{font-size:12px;color:var(--text-secondary,#74706a)}.qx-business-controls{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:8px}.qx-business-controls button,.qx-business-dock button{border:1px solid var(--border-color,#cec7ba);background:var(--surface-primary,transparent);color:inherit;padding:6px 10px;border-radius:5px;cursor:pointer;font:inherit}.qx-business-controls button:hover:enabled,.qx-business-dock button:hover:enabled{background:var(--surface-hover,#ece9e3)}.qx-business-dock button[aria-pressed=true],.qx-business-dock .qx-business-primary{background:#57482f;color:#fff;border-color:#57482f}.qx-business-dock input:not([type=checkbox]),.qx-business-dock select,.qx-business-dock textarea{font:inherit;color:inherit;background:transparent;border:1px solid var(--border-color,#cfc9be);border-radius:4px;padding:6px;max-width:100%;min-width:0}.qx-business-dock textarea{width:100%;min-height:70px;box-sizing:border-box;margin:8px 0}.qx-business-field{display:flex;flex-direction:column;gap:6px;margin:10px 0}.qx-business-confirm,.qx-business-handoff{margin-top:12px;padding-top:10px;border-top:1px solid #ddd4c5}.qx-business-error{color:#ac422d;font-size:12px;overflow-wrap:anywhere}.qx-business-prose{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.7}.qx-business-reply .qx-business-eyebrow{margin-left:0}.qx-business-notes{margin-top:14px;padding:10px 12px;border-left:2px solid #c6bfae;background:var(--surface-secondary,#f5f3ee)}.qx-business-notes summary{cursor:pointer;font-size:12px;color:var(--text-secondary,#625b50)}.qx-business-entries button:focus-visible,.qx-business-dock button:focus-visible,.qx-business-reply button:focus-visible{outline:2px solid #967943;outline-offset:2px}.qx-business-dock button:disabled,.qx-business-entries button:disabled{opacity:.5;cursor:wait}@media(max-width:700px){.qx-business-dock-title span{display:block;width:100%}.qx-business-controls{gap:5px}.qx-business-dock{padding:8px}.qx-business-dock button{min-height:34px}}
  `;document.head.append(style);disposers.push(()=>style.remove());
  return()=>{controller.abort();disposers.reverse().forEach(dispose=>dispose());inputs.clear();listeners.clear();};
};
