// Local-only reviewer. Only the confirmed File is handed back to the uploader.
(()=>{
  if(window.qxPrivacyReview)return;
  let queue=Promise.resolve(),activeCancel,disposed=false;
  const style=document.createElement('style');
  style.textContent=`
  .qx-review{position:fixed;z-index:9000;inset:56px 0 0 auto;width:min(650px,100vw);display:flex;flex-direction:column;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#243248);border-left:1px solid var(--dsw-alias-border-default,#bdc7d2);font:14px/1.65 system-ui,sans-serif;box-sizing:border-box}
  .qx-review *{box-sizing:border-box}.qx-review header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:20px 24px 14px;border-bottom:1px solid #d7dfe8}
  .qx-review h2{font-size:20px;line-height:1.4;margin:0 0 4px}.qx-review p{margin:6px 0;overflow-wrap:anywhere}.qx-review small{font-size:12px;color:var(--dsw-alias-label-secondary,#526071);overflow-wrap:anywhere}
  .qx-review-body{overflow:auto;flex:1;padding:16px 24px;min-height:0}.qx-review label{display:block}.qx-review label:has(input){display:flex;align-items:center;gap:8px;margin:10px 0}
  .qx-review textarea{display:block;resize:vertical;width:100%;min-height:250px;max-height:65vh;padding:12px;font:14px/1.8 system-ui,sans-serif;background:var(--dsw-alias-bg-base,#fff);color:inherit;border:1px solid #899aae;border-radius:6px;caret-color:#315d96}
  .qx-review-actions{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.qx-review button{font:inherit;line-height:1.4;min-height:36px;padding:7px 12px;border:1px solid #899aae;border-radius:6px;color:inherit;background:var(--dsw-alias-bg-base,#fff);cursor:pointer}
  .qx-review button:hover{background:var(--dsw-alias-bg-hover,#edf3f9)}.qx-review button:disabled{opacity:.55;cursor:default}.qx-review :focus-visible{outline:2px solid #3563a5;outline-offset:3px}
  .qx-review summary{cursor:pointer;padding:10px 0}.qx-review pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;margin:0;padding:12px;background:var(--dsw-alias-bg-hover,#f3f6f9);max-height:350px;overflow:auto}
  .qx-review mark{background:#fbe4a5;color:#463500}.qx-review [role=status]{min-height:24px;color:var(--dsw-alias-label-secondary,#526071)}.qx-review [data-error=true]{color:#aa3324}
  .qx-review footer{padding:12px 24px 18px;border-top:1px solid #d7dfe8;background:var(--dsw-alias-bg-base,#fff)}.qx-review footer button{width:100%;background:#315d96;color:white;border-color:#315d96}.qx-review footer button:hover{background:#254b7d}
  .qx-review ::selection{background:#cfe1f6;color:#173858}.qx-review input{accent-color:#315d96}.qx-review footer small{display:block;margin-bottom:10px}
  @media(max-width:600px){.qx-review{inset:0;width:100vw}.qx-review header,.qx-review-body,.qx-review footer{padding-left:16px;padding-right:16px}.qx-review textarea{min-height:220px}}
  `;
  document.head.append(style);
  const node=(tag,text,attrs={})=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);return el;};
  const tokens=text=>[...text.matchAll(/【脱敏-[^\n】]+】/g)];
  function present(preview,{signal,isCurrent,label,position}){
    return new Promise((resolve,reject)=>{
      if(disposed||signal.aborted||!isCurrent())return reject(Error('页面或会话已切换，附件未发送。'));
      const panel=node('aside',undefined,{class:'qx-review',role:'dialog','aria-label':'脱敏复核',tabindex:'-1'});
      const header=node('header'),heading=node('div');heading.append(node('h2','脱敏复核'),node('small',`${position} · ${label}`));
      const cancel=node('button','取消本批',{type:'button'});header.append(heading,cancel);
      const body=node('div',undefined,{class:'qx-review-body'});
      body.append(node('p','请检查每份文字。确认后才加入待发送附件，原件保留在本机。'));
      body.append(node('small',`${preview.privacy_mode==='deep'?'深度':'标准'}脱敏 · 自动替换 ${preview.replacement_count} 处。此处为提取文字，不保留原文件版式。`));
      const title=node('label','最终发送文字'),editor=node('textarea',undefined,{'aria-label':'最终发送文字',spellcheck:'false'});
      editor.value=preview.safe_text;title.append(editor);body.append(title);
      const actions=node('div',undefined,{class:'qx-review-actions'}),mask=node('button','脱敏选中文字',{type:'button'}),restore=node('button','恢复所选原文',{type:'button'}),undo=node('button','撤销上一步',{type:'button'});
      actions.append(mask,restore,undo);body.append(actions);
      const allLabel=node('label'),all=node('input',undefined,{type:'checkbox'});allLabel.append(all,document.createTextNode('同时处理全部相同文字'));body.append(allLabel);
      const status=node('p','可直接编辑文字，也可选中文字后点击脱敏。',{role:'status','aria-live':'polite'});body.append(status);
      const marked=node('details'),markedText=node('pre');marked.append(node('summary','查看高亮预览'),markedText);body.append(marked);
      const original=node('details'),originalText=node('pre',preview.original_text,{'data-original':''});original.append(node('summary','原文对照（仅本机）'),originalText);body.append(original);
      const footer=node('footer'),confirm=node('button','确认使用此版本',{type:'button'});
      footer.append(node('small','以当前文字为准。恢复原文或手动编辑可能重新带入身份信息，请核对后确认。'),confirm);
      panel.append(header,body,footer);document.body.append(panel);
      const focusBefore=document.activeElement;panel.focus();
      let manual=[],history=[],closed=false,saving=false,lastText=editor.value;
      const requestController=new AbortController();
      const notify=(message,error=false)=>{status.textContent=message;status.dataset.error=String(error);};
      const paint=()=>{
        const fragments=document.createDocumentFragment();let end=0;
        for(const match of tokens(editor.value)){fragments.append(document.createTextNode(editor.value.slice(end,match.index)),node('mark',match[0]));end=match.index+match[0].length;}
        fragments.append(document.createTextNode(editor.value.slice(end)));markedText.replaceChildren(fragments);
        undo.disabled=!history.length||saving;lastText=editor.value;
      };
      const checkpoint=()=>{history.push({text:lastText,manual:manual.slice()});if(history.length>30)history.shift();};
      const finish=(error,value)=>{
        if(closed)return;closed=true;requestController.abort();observer.disconnect();signal.removeEventListener('abort',abort);
        panel.remove();if(activeCancel===abort)activeCancel=null;if(focusBefore?.isConnected)focusBefore.focus();
        error?reject(error):resolve(value);
      };
      const abort=()=>finish(Error('本批复核已取消，附件未发送。'));
      activeCancel=abort;signal.addEventListener('abort',abort,{once:true});
      const observer=new MutationObserver(()=>{if(!isCurrent())finish(Error('页面或会话已切换，附件未发送。'));});
      observer.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['data-qx-session-id']});
      cancel.onclick=abort;
      panel.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();abort();}});
      for(const type of ['drop','paste'])panel.addEventListener(type,event=>{if((event.dataTransfer||event.clipboardData)?.files.length){event.preventDefault();event.stopPropagation();notify('请先完成或取消本批复核，再添加文件。',true);}});
      editor.addEventListener('input',()=>{checkpoint();paint();});
      function change(replacement,selection,global){
        checkpoint();
        if(global){
          // Split at existing tokens: a plain-text match cannot alter token IDs.
          const pieces=editor.value.split(/(【脱敏-[^\n】]+】)/g);
          editor.value=pieces.map((part,index)=>selection.startsWith('【脱敏-')?(part===selection?replacement:part):index%2?part:part.split(selection).join(replacement)).join('');
        }else editor.setRangeText(replacement,editor.selectionStart,editor.selectionEnd,'select');
        paint();editor.focus();
      }
      mask.onclick=()=>{
        const start=editor.selectionStart,end=editor.selectionEnd,selection=editor.value.slice(start,end);
        if(!selection.trim())return notify('请先在最终发送文字中选择需要脱敏的内容。',true);
        if(tokens(editor.value).some(m=>start<m.index+m[0].length&&end>m.index))return notify('选择范围包含脱敏标记，请只选择尚未脱敏的文字。',true);
        const existing=manual.find(item=>item.original===selection)||preview.replacements.find(item=>item.original===selection);
        const token=existing?.token||`【脱敏-${preview.document_id.replaceAll('-','').slice(0,12)}-人工-${manual.length+1}】`;
        change(token,selection,all.checked);
        if(!existing)manual.push({original:selection,token});
        notify(all.checked?'已脱敏全部相同文字。':'已脱敏所选文字。');
      };
      restore.onclick=()=>{
        const selection=editor.value.slice(editor.selectionStart,editor.selectionEnd);
        const item=[...preview.replacements,...manual].find(item=>item.token===selection);
        if(!item)return notify('请完整选中一个脱敏标记，再恢复原文。',true);
        change(item.original,selection,all.checked);notify('已恢复原文，请核对是否允许发送这些信息。');
      };
      undo.onclick=()=>{const previous=history.pop();if(!previous)return;editor.value=previous.text;manual=previous.manual;paint();notify('已撤销上一步。');};
      confirm.onclick=async()=>{
        if(saving||closed)return;
        if(!isCurrent())return finish(Error('页面或会话已切换，附件未发送。'));
        if(!editor.value.trim())return notify('最终文字不能为空。',true);
        const finalText=editor.value;saving=true;editor.readOnly=true;mask.disabled=restore.disabled=undo.disabled=confirm.disabled=true;notify('正在保存复核版本…');
        try{
          const response=await fetch('/api/qx-privacy/confirm',{method:'POST',credentials:'same-origin',signal:requestController.signal,
            headers:{'content-type':'application/json','x-qx-privacy':'1'},body:JSON.stringify({document_id:preview.document_id,review_token:preview.review_token,text:finalText,manual_replacements:manual})});
          if(!response.ok||!response.headers.get('x-qx-reviewed')||!response.headers.get('x-qx-safe-name'))throw Error('确认失败');
          const bytes=await response.text();
          if(bytes!==finalText)throw Error('复核版本不一致');
          if(closed)return;
          if(!isCurrent())return finish(Error('页面或会话已切换，附件未发送。'));
          finish(null,new File([bytes],decodeURIComponent(response.headers.get('x-qx-safe-name')),{type:'text/plain'}));
        }catch(error){if(!closed)notify('复核版本未能保存，附件未发送。修改仍在此处，请重试。',true);}
        finally{saving=false;if(!closed){editor.readOnly=false;mask.disabled=restore.disabled=confirm.disabled=false;paint();}}
      };
      paint();
    });
  }
  window.qxPrivacyReview={open(preview,options){const pending=queue.then(()=>present(preview,options));queue=pending.catch(()=>{});return pending;},
    dispose(){disposed=true;activeCancel?.();style.remove();delete window.qxPrivacyReview;}};
})();
