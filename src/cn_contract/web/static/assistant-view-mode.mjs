// Presentation only: both views share the original conversation and form nodes.
export function bindViewMode({document=globalThis.document,window=globalThis.window}={}){
  const at=id=>document.getElementById(id),body=document.body;
  const tools=at('conversation-tools'),summary=at('conversation-tools-summary');
  const hosts={workbench:at('workspace-tools-host'),chat:at('chat-tools-host')};
  const buttons={workbench:at('view-mode-workbench'),chat:at('view-mode-chat')};
  const dock=at('chat-workarea'),title=at('chat-workarea-title');
  const thread=at('conversation-thread'),compose=document.querySelector('.compose-section');
  const sheets=[
    {button:at('show-worksheet'),panel:at('worksheet-panel'),title:'事项底稿'},
    {button:at('show-evidence'),panel:at('evidence-panel'),title:'事实与材料'},
    {button:at('show-followups'),panel:at('followup-panel'),title:'待补材料与跟进清单'},
  ];
  const sources=[
    ['profile-preview','close-profile-preview'],['output-panel','close-outputs'],
    ['material-preview','close-material-preview'],['citation-preview','close-citation-preview'],
  ].map(([panel,close])=>({panel:at(panel),close:at(close),restoreSummary:panel!=='material-preview'})).filter(source=>source.panel);
  const removers=[],frames=new Set(),inertBefore=new Map();
  const nativeOpen=new Map(sheets.map(({panel})=>[panel,panel.open]));
  let current='workbench',active=null,lastFocused=null,disposed=false;
  let benchTop=0,chatTop=0,chatVisited=false,followTail=true,tailFrame=null,revision=0;

  function listen(target,type,handler,options){
    if(!target)return;
    target.addEventListener(type,handler,options);
    removers.push(()=>target.removeEventListener(type,handler,options));
  }
  function frame(fn){
    if(!window.requestAnimationFrame){fn();return null;}
    const id=window.requestAnimationFrame(()=>{frames.delete(id);if(!disposed)fn();});
    frames.add(id);return id;
  }
  function cancelFrames(){
    for(const id of frames)window.cancelAnimationFrame?.(id);
    frames.clear();tailFrame=null;
  }
  function focusSummary(){if(current==='chat'&&!disposed)summary.focus({preventScroll:true});}
  function syncInert(){
    if(current==='chat'&&active){
      for(const node of [thread,compose])if(node){
        if(!inertBefore.has(node))inertBefore.set(node,node.inert);
        node.inert=true;
      }
    }else{
      for(const [node,value]of inertBefore)node.inert=value;
      inertBefore.clear();
    }
  }
  function renderSheet(){
    const visible=current==='chat'&&active?.open;
    if(!visible)active=null;
    for(const {button,panel}of sheets){
      panel.dataset.chatActive=String(current==='chat'&&panel===active);
      button.setAttribute('aria-expanded',String(current==='chat'?panel===active:panel.open));
    }
    dock.classList.toggle('is-open',Boolean(active));
    title.textContent=sheets.find(sheet=>sheet.panel===active)?.title||'事项工具';
    syncInert();
  }
  function hideSheet(focus=true){active=null;renderSheet();if(focus)focusSummary();}
  function closeTools(focus=true){
    if(disposed||current!=='chat')return;
    tools.open=false;summary.setAttribute('aria-expanded','false');
    if(focus)focusSummary();
  }
  function setMode(next){
    if(disposed||!Object.hasOwn(buttons,next))return false;
    if(next===current)return true;
    cancelFrames();const token=++revision;
    if(current==='workbench')benchTop=window.scrollY||0;
    else chatTop=thread.scrollTop;
    current=next;body.dataset.viewMode=next;
    for(const [mode,button]of Object.entries(buttons))button.setAttribute('aria-pressed',String(mode===next));
    hosts[next].append(tools);tools.open=next==='workbench';
    summary.setAttribute('aria-expanded',String(tools.open));
    // A native details toggle can arrive after the mode click that changed layout.
    for(const {panel}of sheets)nativeOpen.set(panel,panel.open);
    if(next==='chat'){
      active=sheets.find(({panel})=>panel.open&&panel.contains(document.activeElement))?.panel
        ||(lastFocused?.open?lastFocused:null)||sheets.find(({panel})=>panel.open)?.panel||null;
      const first=!chatVisited;chatVisited=true;
      renderSheet();
      frame(()=>{
        if(current!=='chat'||token!==revision)return;
        thread.scrollTop=first?thread.scrollHeight:chatTop;
        chatTop=thread.scrollTop;followTail=thread.scrollHeight-thread.clientHeight-thread.scrollTop<=64;
      });
    }else{
      active=null;renderSheet();
      frame(()=>{if(current==='workbench'&&token===revision)window.scrollTo({top:benchTop,behavior:'instant'});});
    }
    return true;
  }

  for(const [mode,button]of Object.entries(buttons))listen(button,'click',()=>setMode(mode));
  listen(document,'focusin',event=>{
    const sheet=sheets.find(({panel})=>panel.open&&panel.contains(event.target));
    if(sheet)lastFocused=sheet.panel;
  });
  for(const {button,panel}of sheets){
    listen(button,'click',()=>{
      if(current!=='chat')return;
      nativeOpen.set(panel,panel.open);
      if(panel.open){active=panel;renderSheet();}
      closeTools(false);
    });
    listen(panel,'toggle',()=>{
      const changed=nativeOpen.get(panel)!==panel.open;nativeOpen.set(panel,panel.open);
      if(current==='chat'){
        if(!panel.open&&active===panel){hideSheet();return;}
        if(panel.open&&changed)active=panel;
      }
      renderSheet();
    });
  }
  for(const id of ['show-profile','show-outputs'])listen(at(id),'click',()=>closeTools(false));
  listen(at('close-chat-workarea'),'click',()=>hideSheet());
  listen(tools,'toggle',()=>{
    if(current==='workbench'&&!tools.open)tools.open=true;
    summary.setAttribute('aria-expanded',String(tools.open));
  });
  listen(document,'pointerdown',event=>{
    if(current==='chat'&&tools.open&&!tools.contains(event.target))closeTools();
  },true);

  // Browser input may flush microtasks between listeners; wait for the next frame.
  for(const source of sources)listen(source.close,'click',()=>{
    const wasVisible=!source.panel.hidden;
    if(wasVisible&&source.restoreSummary)frame(()=>{if(source.panel.hidden)focusSummary();});
  },true);
  listen(document,'keydown',event=>{
    if(event.key!=='Escape'||current!=='chat'||disposed)return;
    const visible=sources.filter(source=>!source.panel.hidden);
    if(visible.length){
      frame(()=>{
        for(const source of visible){
          // Existing Escape handlers get first chance; use the existing button otherwise.
          if(!source.panel.hidden)source.close?.click();
          else if(source.restoreSummary)focusSummary();
        }
      });
      return;
    }
    if(body.classList.contains('sidebar-open'))return;
    if(tools.open){event.preventDefault();event.stopPropagation();closeTools();}
    else if(active){event.preventDefault();event.stopPropagation();hideSheet();}
  },true);

  listen(at('show-workbench-tasks'),'click',()=>{
    if(!setMode('workbench'))return;
    const taskPanel=at('task-draft-panel');
    if(!taskPanel)return;
    taskPanel.open=true;
    frame(()=>{
      taskPanel.scrollIntoView({block:'start',behavior:'instant'});
      taskPanel.querySelector('summary')?.focus({preventScroll:true});
    });
  });

  listen(thread,'scroll',()=>{
    if(current!=='chat')return;
    chatTop=thread.scrollTop;followTail=thread.scrollHeight-thread.clientHeight-thread.scrollTop<=64;
  },{passive:true});
  const history=at('history');
  const mutationObserver=window.MutationObserver&&history?new window.MutationObserver(()=>{
    if(current!=='chat'||!followTail||tailFrame!==null||disposed)return;
    const token=revision;
    tailFrame=frame(()=>{
      tailFrame=null;
      if(current!=='chat'||token!==revision||!followTail)return;
      thread.scrollTop=thread.scrollHeight;chatTop=thread.scrollTop;
    });
  }):null;
  mutationObserver?.observe(history,{subtree:true,childList:true,characterData:true});
  const toolbar=document.querySelector('.page-toolbar');
  const originalHeaderHeight=body.style.getPropertyValue('--chat-header-height');
  function measureHeader(){
    if(!disposed&&toolbar)body.style.setProperty('--chat-header-height',`${Math.ceil(toolbar.getBoundingClientRect().height)}px`);
  }
  const resizeObserver=window.ResizeObserver&&toolbar?new window.ResizeObserver(measureHeader):null;
  resizeObserver?.observe(toolbar);measureHeader();
  if(!resizeObserver)listen(window,'resize',measureHeader);

  body.dataset.viewMode='workbench';hosts.workbench.append(tools);tools.open=true;
  buttons.workbench.setAttribute('aria-pressed','true');buttons.chat.setAttribute('aria-pressed','false');
  summary.setAttribute('aria-expanded','true');renderSheet();
  return {setMode,mode:()=>current,closeTools,dispose(){
    if(disposed)return;
    disposed=true;cancelFrames();for(const remove of removers)remove();
    mutationObserver?.disconnect();resizeObserver?.disconnect();
    for(const [node,value]of inertBefore)node.inert=value;
    inertBefore.clear();active=null;dock.classList.remove('is-open');
    for(const {button,panel}of sheets){delete panel.dataset.chatActive;button.setAttribute('aria-expanded',String(panel.open));}
    if(originalHeaderHeight)body.style.setProperty('--chat-header-height',originalHeaderHeight);
    else body.style.removeProperty('--chat-header-height');
  }};
}
