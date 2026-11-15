// Transient view state only; keys are host-verified session/workspace/case revisions.
window.qxCreateComparisonState=function(request){
  const rows=new Map(),listeners=new Set();let disposed=false;
  const get=key=>{if(!rows.has(key))rows.set(key,{open:false,before:'',after:'',result:null,busy:false,error:'',generation:0,filter:'all',active:0});return rows.get(key);};
  const set=(key,patch)=>{if(disposed)return;rows.set(key,{...get(key),...patch});listeners.forEach(fn=>fn());};
  return {get,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},
    open(key,open,surface='business'){set(key,{open,surface});},
    display(key,patch){set(key,patch);},
    choose(key,side,value){if(!['before','after'].includes(side))throw Error('无效版本');
      const old=get(key);if(old[side]===value)return;
      set(key,{[side]:value,result:null,busy:false,error:'',filter:'all',active:0,generation:old.generation+1});},
    async run(key,args){
      const old=get(key);if(old.busy||!old.before||!old.after)return;
      const generation=old.generation+1;set(key,{busy:true,error:'',result:null,generation});
      try{const result=await request('compare',{...args,before:old.before,after:old.after});
        if(!disposed&&get(key).generation===generation)set(key,{result,completedAt:Date.now()});
      }catch(error){if(!disposed&&get(key).generation===generation)set(key,{error:error.message});}
      finally{if(!disposed&&get(key).generation===generation)set(key,{busy:false});}
    },
    dispose(){disposed=true;rows.clear();listeners.clear();}
  };
};
// Called only after the host has revalidated the source hash and exact anchor.
window.qxContractPreview=function(ctx,sessionId,source){
  window.qxContractPreview.cancel?.();
  if(document.documentElement.dataset.qxSessionId!==sessionId)throw Error('对话已切换，请回原对话重新定位。');
  const path=source.absolutePath.replace(/\\/g,'/'),address='dsh-resource://file/session/'+encodeURIComponent(sessionId)+'/'+path.split('/').map(encodeURIComponent).join('/');
  ctx.sidebarRight.openResource(address,{params:source.reference.line?{line:source.reference.line}:{}});
  if(!source.reference.page)return;
  // The resident PDF renderer exposes page DOM, but no public page navigation method.
  let timer,observer;
  const stop=()=>{observer?.disconnect();clearTimeout(timer);};
  window.qxContractPreview.cancel=stop;
  const locate=()=>{
    if(document.documentElement.dataset.qxSessionId!==sessionId){stop();return;}
    for(const pane of document.querySelectorAll('[data-document-preview]')){
      if(pane.dataset.textpreviewUrl!==address)continue;
      const page=pane.querySelector('[data-pdf-page="'+source.reference.page+'"]');
      if(page){page.scrollIntoView({block:'start',behavior:'instant'});stop();return;}
    }
  };
  observer=new MutationObserver(locate);observer.observe(document.body,{childList:true,subtree:true});timer=setTimeout(stop,15000);locate();
};
window.qxInstallContractComparison=function(ctx,React){
  const h=React.createElement,controller=new AbortController();
  async function api(action,data){const response=await fetch('/api/qx-compare/'+action,{method:'POST',credentials:'same-origin',signal:AbortSignal.any([controller.signal,AbortSignal.timeout(120000)]),headers:{'content-type':'application/json','x-qx-compare':'1'},body:JSON.stringify(data)});const value=await response.json();if(!response.ok){if(value.code==='SCOPE_CHANGED')window.dispatchEvent(new CustomEvent('qx-comparison-scope-changed',{detail:{sessionId:data.sessionId}}));throw Error(value.error||'对比未完成，请重试。');}return value;}
  const state=window.qxCreateComparisonState(api);
  function Picker({label,sessionId,scopeKey,value,onChange,disabled}){
    const [folder,setFolder]=React.useState(''),[files,setFiles]=React.useState(null),[error,setError]=React.useState('');
    React.useEffect(()=>{let live=true;setFiles(null);setError('');api('list',{sessionId,path:folder,expectedScope:scopeKey}).then(data=>{if(live)setFiles(data)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false};},[folder,sessionId,scopeKey]);
    return h('div',{className:'qx-compare-picker'},h('label',null,label,h('select',{'aria-label':label,disabled:disabled||!files,value:'',onChange:event=>{const entry=files.entries[Number(event.target.value)];if(!entry)return;const path=entry.path||[folder,entry.name].filter(Boolean).join('/');entry.type==='directory'?setFolder(path):onChange(path);}},h('option',{value:''},files?'选择文件或进入文件夹':'正在读取文件…'),files?.entries.map((entry,i)=>h('option',{key:entry.path||entry.name,value:i},(entry.type==='directory'?'文件夹：':entry.indexed?'已解析：':'')+entry.name+(entry.indexed?' · '+entry.path.split('/').slice(-2,-1)[0]:''))))),folder&&h('button',{type:'button',disabled,onClick:()=>setFolder(folder.split('/').slice(0,-1).join('/'))},'返回上层'),h('p',null,value||'尚未选择'),error&&h('p',{role:'alert'},error),files?.truncated&&h('p',null,'文件较多，请从具体子文件夹选择。'));
  }
  const location=ref=>(ref.page?'第'+ref.page+'页 · ':'')+(ref.line?'第'+ref.line+'行':'提取段'+ref.paragraph);
  function Panel(props){
    const sessionId=props.session.sessionId||props.session.id;
    const [context,setContext]=React.useState(null),[problem,setProblem]=React.useState(''),[scopeChanged,setScopeChanged]=React.useState(false);
    React.useEffect(()=>{
      let alive=true,generation=0;
      const refresh=()=>{const stamp=++generation;setContext(null);setProblem('');
        api('context',{sessionId,path:props.initialPath}).then(value=>{if(alive&&stamp===generation)setContext(value)}).catch(error=>{if(alive&&stamp===generation)setProblem(error.message)});
      };
      const changed=event=>{if(event.detail.sessionId===sessionId){setScopeChanged(true);refresh();}};
      refresh();window.addEventListener('focus',refresh);window.addEventListener('qx-knowledge-binding-changed',refresh);
      window.addEventListener('qx-comparison-scope-changed',changed);
      return()=>{alive=false;window.removeEventListener('focus',refresh);window.removeEventListener('qx-knowledge-binding-changed',refresh);window.removeEventListener('qx-comparison-scope-changed',changed)};
    },[sessionId,props.initialPath]);
    if(problem)return h('p',{role:'alert',className:'qx-compare-error'},problem);
    if(!context)return h('span',{className:'qx-compare-muted'},'正在核对材料归属…');
    return h(ComparisonBody,{...props,initialPath:context.initialPath||props.initialPath,scopeKey:context.scopeKey,key:context.scopeKey,scopeChanged});
  }
  function ComparisonBody({session,scopeKey,initialPath,preview=false,scopeChanged=false}){
    const sessionId=session.sessionId||session.id,key=scopeKey;
    const value=React.useSyncExternalStore(state.subscribe,()=>state.get(key));
    const {before,after,result,busy}=value,surface=preview?'preview:'+initialPath:'business',open=value.open&&value.surface===surface;
    const [selected,setSelected]=React.useState(null),[localError,setError]=React.useState(''),[notice,setNotice]=React.useState('');
    const [filesOpen,setFilesOpen]=React.useState(false),[preparing,setPreparing]=React.useState(false);
    const error=localError||value.error,generation=React.useRef(0),sourceRef=React.useRef(),readingRef=React.useRef(),entryRef=React.useRef();
    React.useEffect(()=>()=>{generation.current++;window.qxContractPreview.cancel?.();},[]);
    async function choose(side,path){
      if(state.get(key)[side]===path)return;
      generation.current++;state.choose(key,side,path);setSelected(null);setError('');setNotice('');
      const current=state.get(key);if(current.before&&current.after)await run();
    }
    function toggle(){if(!open&&initialPath&&before!==initialPath){generation.current++;state.choose(key,'before',initialPath);state.choose(key,'after','');setSelected(null);setError('');}state.open(key,!open,surface);}
    function returnToConversation(){generation.current++;state.open(key,false,surface);ctx.uiWorkspace?.openSession(sessionId);setTimeout(()=>entryRef.current?.focus(),0);}
    async function run(){generation.current++;setSelected(null);setError('');setNotice('');state.display(key,{active:0,filter:'all'});await state.run(key,{sessionId,expectedScope:scopeKey});}
    async function locate(reference){if(busy)return;const stamp=++generation.current,selection=state.get(key),current=()=>stamp===generation.current&&state.get(key)===selection;setError('');setSelected(null);try{const source=await api('locate',{sessionId,reference,expectedScope:scopeKey});if(!current())return;setSelected(source);window.qxContractPreview(ctx,sessionId,source);setTimeout(()=>sourceRef.current?.focus(),0);}catch(e){if(current())setError(e.message)}}
    async function analyze(){
      if(preparing)return;
      const stamp=++generation.current,selection=state.get(key),current=()=>stamp===generation.current&&state.get(key)===selection;
      setPreparing(true);setError('');setNotice('');
      try{
        if(!window.qxAnalyzeComparison)throw Error('原对话输入框尚未就绪，请返回原对话后重试。');
        await window.qxAnalyzeComparison(sessionId,async party=>{
          const prepared=await api('analysis-draft',{sessionId,expectedScope:scopeKey,party,before:{path:result.before.path,sha256:result.before.sha256},after:{path:result.after.path,sha256:result.after.sha256}});
          if(!current())throw Error('对比已变化，请重新点击分析。');
          return prepared.text;
        });
        if(current()){returnToConversation();setNotice('分析请求已交给原对话，文字对比结果已保留。');}
      }catch(e){if(current())setError(e.message)}finally{setPreparing(false)}
    }
    const kindName={added:'新增',deleted:'删除',modified:'修改'},facetName={amount:'金额',date:'日期／期限',liability:'违约责任文字'};
    const kind=change=>change.kind||(!change.before?'added':!change.after?'deleted':'modified');
    const matches=(change,filter)=>filter==='all'||kind(change)===filter||change.facets?.includes(filter);
    const changes=result?.changes||[],matching=changes.map((change,i)=>matches(change,value.filter)?i:-1).filter(i=>i>=0);
    const active=matching.includes(value.active)?value.active:matching[0],position=matching.indexOf(active);
    const name=path=>(path||'尚未选择').replace(/\\/g,'/').split('/').at(-1);
    function jump(index){if(index===undefined)return;state.display(key,{active:index});const element=readingRef.current?.querySelector('[data-change-index="'+index+'"]');element?.focus({preventScroll:true});element?.scrollIntoView({block:'nearest'});}
    function filter(next){state.display(key,{filter:next,active:changes.findIndex(change=>matches(change,next))});}
    function cell(row,side,changed){
      const content=row[side];
      return h('div',{key:side,className:'qx-compare-cell','data-side':side==='before'?'原稿':'修改稿'},
        content&&changed&&h('div',{className:'qx-compare-anchor'},h('span',null,kindName[kind(row)]),h('button',{type:'button',onClick:()=>locate(content.reference),'aria-label':(side==='before'?'回看原版本 ':'回看新版本 ')+location(content.reference)},location(content.reference))),
        h('div',{className:'qx-compare-text'},content?(changed?row.parts.filter(p=>side==='before'?!p.added:!p.removed).map((part,k)=>h(part.removed?'del':part.added?'ins':'span',{key:k},part.value)):content.text):h('span',{className:'qx-compare-muted'},side==='before'?'此处无原文（新增）':'此处已删除')),
        changed&&side==='after'&&row.facets?.length>0&&h('div',{className:'qx-compare-facets'},row.facets.map(facet=>h('span',{key:facet},facetName[facet]))));
    }
    const reading=result&&h('div',null,

      h('p',{role:'status'},result.status==='unavailable'?'暂时没有足够的可读文字':result.status==='partial'?'仅部分文本结果 · 已发现 '+changes.length+' 处变化':result.equal?'已比较文字相同':'已发现 '+changes.length+' 处文字变化'),
      result.warnings.length>0&&h('details',{open:result.status!=='complete'},h('summary',null,'对比范围与待核对内容'),h('ul',null,result.warnings.map((warning,i)=>h('li',{key:i},warning)))),
      result.status!=='unavailable'&&h('div',null,
        h('div',{className:'qx-compare-toolbar'},h('div',{className:'qx-compare-filters','aria-label':'变更分类'},[['all','全部'],...Object.entries(kindName),...Object.entries(facetName)].map(([id,label])=>h('button',{type:'button',key:id,'aria-pressed':value.filter===id,onClick:()=>filter(id)},label+' '+changes.filter(change=>matches(change,id)).length))),
          h('div',{className:'qx-compare-navigation'},h('span',null,'两栏同步滚动'),h('button',{type:'button',disabled:position<=0,onClick:()=>jump(matching[position-1])},'上一处'),h('span',{'aria-live':'polite'},matching.length?(position+1)+' / '+matching.length:'0 / 0'),h('button',{type:'button',disabled:position<0||position>=matching.length-1,onClick:()=>jump(matching[position+1])},'下一处'))),
        h('p',{className:'qx-compare-muted'},'删除用红色删除线，新增用绿色下划线。金额、日期与违约责任标签仅提示相关文字变化，不代表法律判断。'),
        h('div',{className:'qx-compare-documents'},h('div',{className:'qx-compare-document-heads'},['before','after'].map(side=>h('div',{key:side},h('h3',null,side==='before'?'原稿':'修改稿'),h('p',{title:result[side].path},name(result[side].path))))),
          h('div',{className:'qx-compare-results',ref:readingRef,'aria-label':'合同文字对照',tabIndex:0},(result.rows||changes.map((_,changeIndex)=>({changeIndex}))).map((entry,i)=>{
            const changed=entry.changeIndex!==undefined,row=changed?changes[entry.changeIndex]:entry;
            if(value.filter!=='all'&&(!changed||!matches(row,value.filter)))return null;
            return h(changed?'article':'div',{key:i,className:'qx-compare-versions'+(changed?' qx-compare-change':' qx-compare-unchanged')+(changed&&entry.changeIndex===active?' qx-compare-current':''),'data-change-index':changed?entry.changeIndex:undefined,tabIndex:changed?-1:undefined,'aria-label':changed?'第'+(entry.changeIndex+1)+'处'+kindName[kind(row)]:undefined,onClick:changed?event=>{if(!event.target.closest('button'))state.display(key,{active:entry.changeIndex})}:undefined},['before','after'].map(side=>cell(row,side,changed)),changed&&!row.characterDetail&&h('p',{className:'qx-compare-detail-note'},'该段差异较大，显示整段增删。'));
          }),value.filter!=='all'&&!matching.length&&h('p',null,'此分类没有识别到文字变化。请查看全部对照，关键词标签不能覆盖所有表达。'))),
        h('div',{className:'qx-compare-reading-footer'},h('p',null,active===undefined?'暂无可定位变更':('当前：第'+(active+1)+'处'+kindName[kind(changes[active])]+' · '+(changes[active].before?.text||'无原文').trim().slice(0,80)+' → '+(changes[active].after?.text||'已删除').trim().slice(0,80))),h('div',{className:'qx-compare-ai-action'},h('p',{className:'qx-compare-muted'},'AI 分析沿用原对话与立场，按原对话规则计费。'),h('button',{type:'button',className:'qx-compare-primary',disabled:preparing||busy,onClick:analyze},preparing?'正在核对版本…':'AI分析修改影响')))),
      selected&&h('section',{className:'qx-compare-source',tabIndex:-1,ref:sourceRef,'aria-label':'已核验原文位置'},h('h3',null,'原文回看 · '+location(selected.reference)),h('p',null,selected.reference.path),selected.context.map(row=>h(row.selected?'mark':'p',{key:row.paragraph},row.text)),h('p',{className:'qx-compare-muted'},'原件 SHA-256：'+selected.reference.sha256),!selected.reference.page&&!selected.reference.line&&h('p',null,'来源段落：'+selected.reference.location+'。Word 页码随排版变化，请在右侧原件中核对。')));
    const content=h('div',{className:'qx-compare-body'},
      h('div',{className:'qx-compare-heading'},h('h2',null,'合同文字对比'),h('button',{type:'button',onClick:returnToConversation},'返回原对话')),
      h('p',{className:'qx-compare-muted'},'选好两个版本后自动对比文字，不调用模型。返回对话后保留结果。'),
      error&&h('p',{role:'alert',className:'qx-compare-error'},error),
      h('div',{className:'qx-compare-pickers',hidden:!!result&&!filesOpen},
        initialPath&&!filesOpen?h('div',null,h('span',null,'原版本'),h('p',{title:before},name(before))):h(Picker,{label:'原版本',sessionId,scopeKey,value:before,onChange:path=>choose('before',path),disabled:busy}),
        h(Picker,{label:'新版本',sessionId,scopeKey,value:after,onChange:path=>choose('after',path),disabled:busy})),
      h('div',{className:'qx-compare-file-actions'},h('button',{type:'button',disabled:busy,onClick:()=>setFilesOpen(!filesOpen)},filesOpen?'收起文件选择':'更换文件'),
        before&&after&&h('button',{type:'button',disabled:busy,onClick:run},busy?'正在对比…':error?'重试对比':'重新对比')),reading);
    return h('section',{className:'qx-compare'+(preview?' qx-compare-preview':'')+(open?' qx-compare-open':''),'aria-label':'合同对比'},h('button',{type:'button',ref:entryRef,'aria-expanded':open,onClick:toggle},preview?'对比版本':'合同对比'),
      scopeChanged&&!result&&h('p',{role:'status',className:'qx-compare-muted'},'材料归属已更新，请重新选择合同。'),!open&&notice&&h('p',{role:'status'},notice),open&&content);
  }
  function PreviewEntry({ownerSessionId,absolutePath}){
    if(!ownerSessionId||typeof absolutePath!=='string'||! /\.(txt|md|docx?|pdf|rtf|odt)$/i.test(absolutePath))return null;
    return h(Panel,{session:{sessionId:ownerSessionId},initialPath:absolutePath,preview:true,key:ownerSessionId+absolutePath});
  }
  const dispose=ctx.slots.inject('sidebar.right.tab.document.actions',()=>ctx.slots.register({
    name:'sidebar.right.tab.document.actions',id:'qx-contract-compare',order:20,
    inject:sessionId=>({ownerSessionId:sessionId})
  },PreviewEntry));
  window.qxComparisonPanel=Panel;window.dispatchEvent(new Event('qx-comparison-ready'));

  const style=document.createElement('style');style.textContent=`
  [data-document-preview] div:has(> [data-slot="sidebar.right.tab.document.actions"] .qx-compare-preview.qx-compare-open){flex-wrap:wrap;height:auto;min-height:38px;align-items:flex-start}
  .qx-compare-preview.qx-compare-open{flex-basis:100%;width:100%}.qx-compare-preview>button{white-space:nowrap}.qx-compare-preview:not(.qx-compare-open){flex:none;margin-bottom:0}
  .qx-compare{margin:0 0 8px;font:13px/1.7 var(--dsw-font,'Microsoft YaHei',system-ui,sans-serif);color:var(--dsw-alias-label-primary,#29251f)}.qx-compare *{box-sizing:border-box}
  .qx-compare button,.qx-compare select,.qx-compare input{font:inherit;color:inherit;background:var(--dsw-alias-bg-base,#fff);border:1px solid var(--border-color,#cec7ba);border-radius:5px;padding:5px 9px;max-width:100%;min-height:34px}
  .qx-compare button{cursor:pointer}.qx-compare button:hover:enabled{background:var(--surface-hover,#ece9e3)}.qx-compare button:disabled{opacity:.55;cursor:default}.qx-compare :focus-visible{outline:2px solid #967943;outline-offset:2px}
  .qx-compare .qx-compare-filters button[aria-pressed=true],.qx-compare .qx-compare-primary{background:#eee4d2;color:#4e371d;border-color:#a58a5c}
  .qx-compare-body{border-top:1px solid var(--border-color,#ded9cf);padding:12px 0;margin-top:8px;max-height:64vh;overflow:auto;scrollbar-color:#b6ad9c transparent;background:var(--dsw-alias-bg-base,#fff)}
  .qx-compare p{margin:6px 0;overflow-wrap:anywhere}.qx-compare h2{font-size:20px;margin:0}.qx-compare h3{font-size:16px;margin:0 0 4px}
  .qx-compare-heading,.qx-compare-toolbar,.qx-compare-filters,.qx-compare-navigation,.qx-compare-reading-footer{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .qx-compare-heading,.qx-compare-toolbar,.qx-compare-reading-footer{justify-content:space-between}.qx-compare-heading{margin-bottom:12px}
  .qx-compare-pickers,.qx-compare-versions,.qx-compare-document-heads{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.qx-compare-pickers{gap:16px;margin:12px 0}.qx-compare-pickers[hidden]{display:none}.qx-compare-file-actions{display:flex;gap:8px;margin:10px 0}.qx-compare-picker{min-width:0}.qx-compare-picker label{display:grid;gap:4px}.qx-compare select{width:100%}
  .qx-compare-toolbar{gap:10px;margin-top:16px}.qx-compare-filters{gap:4px}.qx-compare-filters button{padding:4px 8px}.qx-compare-navigation{font-variant-numeric:tabular-nums}.qx-compare-navigation>span:first-child{color:var(--dsw-alias-label-secondary,#665e51);font-size:12px}
  .qx-compare-documents{border:1px solid var(--border-color,#ded9cf);border-radius:6px;overflow:hidden;margin-top:10px}.qx-compare-document-heads{background:var(--surface-hover,#f4f1eb)}.qx-compare-document-heads>div{padding:12px 20px;min-width:0;border-bottom:1px solid #ded9cf}.qx-compare-document-heads>div+div{border-left:1px solid #ded9cf}.qx-compare-document-heads p{margin:0;font-size:12px;color:var(--dsw-alias-label-secondary,#665e51)}
  .qx-compare-results{max-height:48vh;overflow:auto;scrollbar-color:#b6ad9c transparent}.qx-compare-versions{margin:0;padding:0;gap:0;outline-offset:-2px}.qx-compare-cell{min-width:0;padding:12px 20px}.qx-compare-cell+.qx-compare-cell{border-left:1px solid #ded9cf}
  .qx-compare-unchanged .qx-compare-cell{padding-top:8px;padding-bottom:8px}.qx-compare-change{border-top:1px solid #e6dfd2;border-bottom:1px solid #e6dfd2}.qx-compare-current{outline:2px solid #a58a5c}
  .qx-compare-anchor{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px;margin-bottom:8px;color:var(--dsw-alias-label-secondary,#665e51)}.qx-compare-anchor button{padding:2px 6px;min-height:28px;font-size:12px}
  .qx-compare-text,.qx-compare-source mark,.qx-compare-source>p{white-space:pre-wrap;overflow-wrap:anywhere}.qx-compare-text{font-size:15px;line-height:1.9}.qx-compare del{color:#8c2c20;background:#fff0ec;text-decoration-thickness:1px}.qx-compare ins{color:#195a38;background:#eaf7ef;text-decoration-thickness:1px;text-underline-offset:3px}
  .qx-compare-facets{display:flex;gap:8px;font-size:12px;color:#665235;margin-top:6px}.qx-compare-detail-note{grid-column:1/-1;padding:0 20px;font-size:12px}.qx-compare-reading-footer{position:sticky;bottom:0;z-index:1;background:var(--dsw-alias-bg-base,#fff);border-top:1px solid var(--border-color,#ded9cf);padding:10px 0;gap:12px;align-items:center}.qx-compare-reading-footer p{flex:1;min-width:200px;font-size:12px}
  .qx-compare-source{border-top:1px solid #b6ad9c;margin:16px 0;padding:12px 0}.qx-compare-source mark{display:block;background:#fff2cd;color:#453c25;padding:8px}.qx-compare .qx-compare-muted{font-size:12px;color:var(--dsw-alias-label-secondary,#665e51)}.qx-compare .qx-compare-error{color:#9b3023}.qx-compare summary{cursor:pointer}.qx-compare ::selection{background:#eadbb9;color:#29251f}
  .qx-compare-ai-action{display:flex;align-items:center;gap:10px;max-width:390px}.qx-compare-ai-action p{min-width:0;margin:0}.qx-compare-ai-action button{flex-shrink:0}
  @media(max-width:620px){.qx-compare-pickers,.qx-compare-versions{grid-template-columns:1fr;gap:8px}.qx-compare-cell+.qx-compare-cell{border-left:0;border-top:1px dashed #ded9cf}.qx-compare-cell::before{content:attr(data-side);display:block;font-size:12px;color:#665e51}.qx-compare-cell,.qx-compare-document-heads>div{padding:10px}}

  `;document.head.append(style);
  return()=>{controller.abort();state.dispose();if(window.qxComparisonPanel===Panel)delete window.qxComparisonPanel;window.qxContractPreview.cancel?.();dispose();style.remove();};
};
