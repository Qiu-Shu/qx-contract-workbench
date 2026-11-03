// Scoped enhancement for the existing Harness composer and knowledge upload.
// Capture file intake before React/Lexical see bytes; replay only the safe File.
(()=>{
  if(window.qxPrivacy)return;
  const states=new Map(),replayed=new WeakSet(),controllers=new Set(),controls=new Set();
  let disposed=false,scheduled=false;
  const current=()=>document.documentElement.dataset.qxSessionId||'new-session';
  const stateFor=key=>{if(!states.has(key))states.set(key,{enabled:false,terms:'',busy:0,message:'',error:false,context:crypto.randomUUID()});return states.get(key);};
  const keyFor=element=>element.closest?.('.qx-kb')?'knowledge':current();
  const scopeFor=element=>element.closest?.('.qx-kb')||element.closest?.('[data-composer-card]');
  const css=document.createElement('style');css.dataset.qxPrivacy='';css.textContent=`
    .qx-privacy{padding:8px 14px 0;font:inherit;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-secondary,#526071);display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
    .qx-kb .qx-privacy{padding:0;width:100%;order:3}.qx-privacy label{display:inline-flex;gap:6px;align-items:center;cursor:pointer;min-height:28px}
    .qx-privacy input[type=checkbox]{accent-color:#3563a5;width:15px;height:15px;padding:0;margin:0}.qx-privacy details{max-width:100%}.qx-privacy summary{cursor:pointer;padding:4px 0;color:var(--dsw-alias-label-secondary,#526071)}
    .qx-privacy details[open]{flex-basis:100%}.qx-privacy p{font-size:12px;margin:6px 0;line-height:1.6;max-width:68ch}.qx-privacy textarea{box-sizing:border-box;width:100%;max-width:480px;font:inherit;padding:7px 9px;resize:vertical;border:1px solid #bdc7d2;border-radius:6px;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#1d2937)}
    .qx-privacy :focus-visible{outline:2px solid #3563a5;outline-offset:3px}.qx-privacy-status{flex-basis:100%;margin:0!important;color:var(--dsw-alias-label-secondary,#526071);transition:color .18s ease-out}.qx-privacy-status:empty{display:none}.qx-privacy[data-error=true] .qx-privacy-status{color:#a33a29}
    .qx-privacy[data-busy=true] label{cursor:progress}.qx-privacy::selection{background:#dbe8f8;color:#173858}@media(prefers-reduced-motion:reduce){.qx-privacy-status{transition:none}}
  `;document.head.append(css);
  function repaint(){
    for(const node of controls){
      if(!node.isConnected){controls.delete(node);continue;}
      const state=stateFor(keyFor(node));
      const check=node.querySelector('input');check.checked=state.enabled;
      const disabled=Boolean(node.closest('[data-composer-card]')?.querySelector('input[type=file]')?.disabled);
      if(check.disabled!==disabled)check.disabled=disabled;
      const textarea=node.querySelector('textarea');if(document.activeElement!==textarea)textarea.value=state.terms;
      node.dataset.error=String(state.error);node.dataset.busy=String(state.busy>0);
      const message=state.busy?`正在本机脱敏（${state.busy} 批）… 完成后附件会出现在输入框内。`:state.message;
      const status=node.querySelector('[role=status]');if(status.textContent!==message)status.textContent=message;
    }
  }
  function createControl(host){
    if(host.querySelector(':scope > .qx-privacy'))return;
    const node=document.createElement('div');node.className='qx-privacy';node.dataset.composerOverlay='true';
    node.addEventListener('click',event=>event.stopPropagation());
    const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';
    label.append(check,document.createTextNode('上传前脱敏'));node.append(label);
    const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='说明与敏感词';
    const hint=document.createElement('p');hint.textContent='仅作用于之后添加的文件。本机提取文字并替换识别到的身份信息，再上传文字副本；原件留在本机，图片与版式不随附。自动识别可能遗漏，可在下方补充姓名、公司或其他敏感词。';
    const textarea=document.createElement('textarea');textarea.rows=2;textarea.placeholder='补充敏感词，每行一个（可选）';textarea.setAttribute('aria-label','补充需要脱敏的敏感词，每行一个');
    details.append(summary,hint,textarea);node.append(details);
    const status=document.createElement('p');status.className='qx-privacy-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');node.append(status);
    check.addEventListener('change',()=>{const s=stateFor(keyFor(node));s.enabled=check.checked;s.message=s.enabled?'之后添加的文件将先在本机脱敏；已添加的附件不会改变。':'之后添加的文件按原件上传。';s.error=false;repaint();});
    textarea.addEventListener('input',()=>{stateFor(keyFor(node)).terms=textarea.value;});
    host.prepend(node);controls.add(node);
  }
  function mount(){
    scheduled=false;if(disposed)return;
    document.querySelectorAll('[data-composer-card],.qx-kb-toolbar:has(input[type=file][multiple])').forEach(createControl);repaint();
  }
  const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(mount);}});
  observer.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['data-qx-session-id','disabled']});mount();
  function filesFrom(event){
    if(event.type==='change')return event.target instanceof HTMLInputElement&&event.target.type==='file'?Array.from(event.target.files||[]):[];
    return Array.from((event.type==='paste'?event.clipboardData:event.dataTransfer)?.files||[]);
  }
  async function convert(file,settings,signal){
    const query=new URLSearchParams({name:file.name,context:settings.context});
    const response=await fetch('/api/qx-privacy/prepare?'+query,{method:'POST',credentials:'same-origin',signal,headers:{'content-type':'application/octet-stream','x-qx-privacy':'1','x-qx-terms':encodeURIComponent(JSON.stringify(settings.terms.split(/\r?\n/).map(t=>t.trim()).filter(Boolean)))},body:file});
    if(!response.ok){let message='脱敏服务未就绪，原件未发送。请稍后重新添加。';try{message=(await response.json()).error||message;}catch{}throw Error(message);}
    if(!response.headers.get('x-qx-safe-name'))throw Error('脱敏响应不完整，原件未发送。请重新添加。');
    return {file:new File([await response.blob()],decodeURIComponent(response.headers.get('x-qx-safe-name')),{type:'text/plain'}),count:Number(response.headers.get('x-qx-replacements')||0)};
  }
  function intake(event){
    if(replayed.has(event)||disposed)return;
    const target=event.target instanceof Element?event.target:null;if(!target)return;
    // Harness accepts OS drops across the whole document, including outside the composer.
    const scope=scopeFor(target)||(['drop','paste','change'].includes(event.type)&&!target.closest('dialog,[role=dialog]')?document.querySelector('[data-composer-card]'):null);if(!scope)return;
    const key=keyFor(scope),state=stateFor(key);
    if(scope.matches('[data-composer-card]')&&scope.querySelector('input[type=file]')?.disabled)return;
    if(state.enabled&&event.type==='drop'&&event.dataTransfer?.types.includes('application/x-dsh-file')){
      event.preventDefault();event.stopImmediatePropagation();state.error=true;state.message='此拖拽引用已有附件。要先脱敏，请从本机重新选择或拖入原文件。';repaint();return;
    }
    const files=filesFrom(event);if(!files.length)return;
    // ZIP backup restore is a distinct local workflow, never a model upload.
    if(scope.matches('.qx-kb')&&event.type==='change'&&!target.multiple&&target.accept?.toLowerCase()==='.zip'&&files.every(file=>file.name.toLowerCase().endsWith('.zip')))return;
    if(!state.enabled)return;
    event.preventDefault();event.stopImmediatePropagation();
    if(event.type==='change')target.value='';
    const controller=new AbortController();controllers.add(controller);
    const settings={context:key==='knowledge'?crypto.randomUUID():state.context,terms:state.terms};state.busy++;state.error=false;state.message='';repaint();
    void(async()=>{
      try{
        const converted=[];for(const file of files)converted.push(await convert(file,settings,controller.signal));
        if(disposed||!target.isConnected||keyFor(scope)!==key)throw Error('页面或会话已切换，附件未发送。请在当前会话重新添加。');
        const transfer=new DataTransfer();for(const result of converted)transfer.items.add(result.file);
        let replay,replayTarget=target;
        if(scope.matches('.qx-kb')&&event.type!=='change'){
          replayTarget=Array.from(scope.querySelectorAll('input[type=file]')).find(input=>!input.accept.toLowerCase().includes('.zip'));
          if(!replayTarget)throw Error('知识库上传入口已关闭，请重新添加。');
          replayTarget.files=transfer.files;replay=new Event('change',{bubbles:true});
        }
        else if(event.type==='change'){target.files=transfer.files;replay=new Event('change',{bubbles:true});}
        else if(event.type==='paste')replay=new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:transfer});
        else replay=new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer});
        replayed.add(replay);replayTarget.dispatchEvent(replay);
        state.message=`已生成 ${converted.length} 份脱敏文字副本，共替换 ${converted.reduce((n,r)=>n+r.count,0)} 处。原件留在本机，上传状态请查看附件。`;
      }catch(error){state.error=true;state.message=error instanceof TypeError?'本机连接中断，原件未发送。恢复连接后重新添加文件。':error.message||'本机脱敏失败，原件未发送。请重新添加文件。';}
      finally{controllers.delete(controller);state.busy--;repaint();}
    })();
  }
  function holdSend(event){
    const target=event.target instanceof Element?event.target:null;if(!target?.closest('[data-composer-card]'))return;
    const state=stateFor(keyFor(target));if(!state.busy)return;
    const button=target.closest('button');
    if((event.type==='keydown'&&event.key==='Enter'&&!event.shiftKey&&!target.closest('.qx-privacy'))||(event.type==='click'&&button&&/发送|Send|Queue|Steer/i.test(button.getAttribute('aria-label')||''))){event.preventDefault();event.stopImmediatePropagation();}
  }
  for(const type of ['change','paste','drop'])window.addEventListener(type,intake,true);
  for(const type of ['keydown','click'])window.addEventListener(type,holdSend,true);
  window.qxPrivacy={dispose(){disposed=true;observer.disconnect();for(const c of controllers)c.abort();for(const type of ['change','paste','drop'])window.removeEventListener(type,intake,true);for(const type of ['keydown','click'])window.removeEventListener(type,holdSend,true);for(const n of controls)n.remove();css.remove();delete window.qxPrivacy;}};
})();
