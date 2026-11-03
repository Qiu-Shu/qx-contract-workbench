window.__ModuleLoader__.load({id:'@qunxing/desktop-session',factory:require=>{
  const React=require('react');
  const h=React.createElement;
  // The library view ships in the same registered client bundle as its entry.
  function createKnowledgeView(React){
    const h=React.createElement;
    const css=`
    .qx-kb{width:min(1120px,94vw);max-height:90vh;padding:0;border:1px solid #d7dce4;border-radius:12px;background:#fff;color:#172a3d;font:14px/1.6 "Microsoft YaHei",system-ui,sans-serif;box-shadow:0 18px 65px #10203030}
    .qx-kb::backdrop{background:#15293d70}.qx-kb *{box-sizing:border-box}.qx-kb button,.qx-kb input{font:inherit}.qx-kb button,.qx-kb a{touch-action:manipulation}
    .qx-kb-head{display:flex;align-items:center;justify-content:space-between;padding:20px 26px;border-bottom:1px solid #e1e6ed}.qx-kb h2{margin:0;font-size:22px}.qx-kb h3{font-size:16px;margin:0 0 10px}.qx-kb p{margin:6px 0}
    .qx-kb-body{padding:20px 26px;overflow:auto;max-height:calc(90vh - 85px)}.qx-kb-muted{color:#58687a;font-size:13px}.qx-kb-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0}
    .qx-kb input{min-width:0;padding:9px 12px;border:1px solid #b8c4d2;border-radius:6px;color:#172a3d;background:#fff}.qx-kb input[type=search]{flex:1;min-width:180px}.qx-kb input:focus-visible,.qx-kb button:focus-visible,.qx-kb a:focus-visible{outline:2px solid #235ba0;outline-offset:3px}
    .qx-kb button{border:1px solid #b8c4d2;border-radius:6px;background:#fff;padding:8px 12px;color:#173c65;cursor:pointer}.qx-kb button:hover:enabled{background:#edf3f8}.qx-kb button:disabled{opacity:.55;cursor:wait}.qx-kb .qx-kb-primary{background:#235b91;color:#fff;border-color:#235b91}.qx-kb .qx-kb-primary:hover:enabled{background:#19466f}
    .qx-kb-table{width:100%;border-collapse:collapse;text-align:left}.qx-kb-table th{padding:10px 8px;background:#f3f6fa;color:#4f6175;font-weight:500}.qx-kb-table td{padding:14px 8px;border-bottom:1px solid #e1e6ed;vertical-align:top}.qx-kb-title{overflow-wrap:anywhere;font-weight:600}.qx-kb-actions{display:flex;flex-wrap:wrap;gap:6px;min-width:180px}.qx-kb-actions button{padding:5px 9px}.qx-kb a{color:#235b91;text-decoration:underline;text-underline-offset:3px}
    .qx-kb-notice{padding:10px 14px;background:#eef4fa;border-left:3px solid #527fa9;margin:12px 0;white-space:pre-wrap}.qx-kb-error{background:#fff1ec;border-color:#b34a27;color:#8e351a}.qx-kb-result{padding:16px 0;border-bottom:1px solid #e1e6ed}.qx-kb-result blockquote{margin:10px 0;padding:0 0 0 14px;border-left:2px solid #b7cadc;white-space:pre-wrap;overflow-wrap:anywhere}.qx-kb-empty{padding:40px 12px;text-align:center;color:#58687a}.qx-kb-source{padding:18px;background:#f7f9fc;border:1px solid #dbe3ec;border-radius:8px;margin:20px 0}.qx-kb-source pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.85}.qx-kb-close{font-size:20px!important;padding:4px 12px!important}.qx-kb-pager{display:flex;justify-content:space-between;gap:10px;margin:16px 0}
    @media(max-width:650px){.qx-kb-head,.qx-kb-body{padding:16px}.qx-kb-table th:nth-child(2),.qx-kb-table td:nth-child(2){display:none}.qx-kb-table th,.qx-kb-table td{padding:10px 4px}.qx-kb-actions{min-width:110px;flex-direction:column}.qx-kb-toolbar input{width:100%}.qx-kb{width:96vw}.qx-kb h2{font-size:20px}}
    `;
    const states={pending:'待解析',indexing:'解析中',partial:'部分已解析',ready:'可检索',no_text:'未提取到文字',error:'解析未完成',interrupted:'解析中断'};
    async function api(path,options={}){
      const response=await fetch('/api/qx-knowledge/'+path,{credentials:'same-origin',...options,headers:{'x-qx-knowledge':'1',...options.headers}});
      if(response.status===401||response.status===403)throw new Error('工作台连接已失效，请从“工作台 → 重新连接”恢复。');
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error(`知识库服务暂时不可用（${response.status}），请稍后重试。`);
      const data=await response.json();if(!response.ok)throw new Error(data.error||'操作未完成');return data;
    }
    return function KnowledgePanel({onClose}){
      const dialog=React.useRef(null),file=React.useRef(null),backupFile=React.useRef(null),alive=React.useRef(true);
      const [catalog,setCatalog]=React.useState({documents:[],total:0,next_offset:null});
      const [offset,setOffset]=React.useState(0),[archived,setArchived]=React.useState(false),[category,setCategory]=React.useState('');
      const [query,setQuery]=React.useState(''),[results,setResults]=React.useState(null),[searchOffset,setSearchOffset]=React.useState(0);
      const [source,setSource]=React.useState(null),[busy,setBusy]=React.useState(false),[loading,setLoading]=React.useState(true);
      const [error,setError]=React.useState(''),[notice,setNotice]=React.useState('');
      const [loadError,setLoadError]=React.useState('');
      const [backupUrl,setBackupUrl]=React.useState('');
      const load=React.useCallback(async()=>{const data=await api(`documents?offset=${offset}&archived=${archived?1:0}`);if(alive.current)setCatalog(data);},[offset,archived]);
      React.useEffect(()=>{
        alive.current=true;
        const element=dialog.current;
        if(!element.open)element.showModal();
        return()=>{alive.current=false;if(element.open)element.close();};
      },[]);
      React.useEffect(()=>{
        let cancelled=false,timer;
        const controller=new AbortController();
        const refresh=async()=>{
          try{
            if(document.visibilityState==='visible'){
              const data=await api(`documents?offset=${offset}&archived=${archived?1:0}`,{signal:controller.signal});
              if(!cancelled){setCatalog(data);setLoading(false);setLoadError('');}
            }
          }catch(e){if(!cancelled){setLoadError(e.message);setLoading(false);}}
          finally{if(!cancelled)timer=setTimeout(refresh,4000);}
        };
        setLoading(true);void refresh();
        return()=>{cancelled=true;clearTimeout(timer);controller.abort();};
      },[offset,archived]);
      async function act(task){setBusy(true);setError('');try{await task();}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
      async function upload(files){
        const selected=Array.from(files);if(!selected.length)return;
        await act(async()=>{
          const failed=[];let count=0;
          for(const item of selected){
            setNotice(`正在上传 ${count+failed.length+1}/${selected.length}：${item.name}`);
            try{await api('upload',{method:'POST',headers:{'content-type':'application/octet-stream','x-qx-filename':encodeURIComponent(item.name),'x-qx-category':encodeURIComponent(category.trim()||'未分类')},body:item});count++;}
            catch(e){failed.push(`${item.name}：${e.message}`);}
          }
          setNotice(`已上传 ${count} 份，正在本机解析。${failed.length?'\n未完成：'+failed.join('\n'):''}`);setResults(null);setArchived(false);setOffset(0);await load();
        });
      }
      async function search(next=0){await act(async()=>{const data=await api(`search?q=${encodeURIComponent(query.trim())}&offset=${next}`);setResults(data);setSearchOffset(next);setSource(null);});}
      async function backup(){await act(async()=>{
        setNotice('正在整理原件和引用索引，请保持工作台开启。');setBackupUrl('');
        const data=await api('backup',{method:'POST'});setBackupUrl(data.download);
        setNotice(`已生成 ${data.documents} 份资料的备份。请点击“下载备份”保存到安全位置，下载链接 30 分钟内有效。`);
      });}
      async function restore(item){if(!item)return;await act(async()=>{
        setNotice('正在校验并合并备份，请保持工作台开启。');
        const data=await api('restore',{method:'POST',headers:{'content-type':'application/zip'},body:item});
        setNotice(`已恢复 ${data.imported} 份资料，跳过 ${data.skipped} 份已有资料。现有资料保留。`);
        setResults(null);setSource(null);setOffset(0);await load();
      });}
      async function read(id,start=0){await act(async()=>{setSource(await api(`read?id=${id}&start=${start}`));});}
      async function citation(ref){await act(async()=>{const data=await api('citation?reference='+encodeURIComponent(ref));setSource({document_id:data.document_id,title:data.title,chunks:[data],next_start:null});});}
      async function copy(chunk,title){
        await act(async()=>{
          const value=await api('citation?reference='+encodeURIComponent(chunk.citation));
          const text=`【${title}｜${value.page?'第 '+value.page+' 页｜':''}${value.location}｜${value.citation}】\n${value.text}`;
          if(!navigator.clipboard?.writeText){setNotice('当前环境无法直接复制，请在原文区域选中内容复制。');return;}
          await navigator.clipboard.writeText(text);setNotice('已复制原文与来源，可粘贴到对话中。');
        });
      }
      function docActions(d){return h('div',{className:'qx-kb-actions'},
        !archived&&h('button',{disabled:busy||d.busy,onClick:()=>read(d.id)},'查看原文'),
        h('a',{href:`/api/qx-knowledge/source?id=${d.id}`,download:true},'下载原件'),
        !archived&&d.state!=='ready'&&h('button',{disabled:busy||d.busy,onClick:()=>act(async()=>{await api(`index?id=${d.id}`,{method:'POST'});await load();})},d.busy?'解析中…':'重新解析'),
        h('button',{disabled:busy||d.busy,onClick:()=>act(async()=>{await api(`archive?id=${d.id}${archived?'&restore=1':''}`,{method:'POST'});setSource(null);setResults(null);await load();})},archived?'恢复到库':'归档'));
      }
      return h('dialog',{className:'qx-kb',ref:dialog,'aria-labelledby':'qx-kb-heading',onCancel:e=>{e.preventDefault();if(!busy)onClose();}},
        h('style',null,css),
        h('header',{className:'qx-kb-head'},h('div',null,h('h2',{id:'qx-kb-heading'},'律所知识库'),h('p',{className:'qx-kb-muted'},'本机保存 · 原文可追溯')),h('button',{className:'qx-kb-close',disabled:busy,onClick:onClose,'aria-label':'关闭知识库'},'×')),
        h('div',{className:'qx-kb-body'},
          h('p',{className:'qx-kb-muted'},'上传律所范本、办案经验、制度与研究资料。上传和检索在本机完成；用于 AI 问答的片段会发送给当前配置的模型。'),
          h('div',{className:'qx-kb-toolbar'},h('input',{value:category,onChange:e=>setCategory(e.target.value),placeholder:'上传分类，如：合同范本',maxLength:80,'aria-label':'上传资料分类'}),
            h('input',{ref:file,type:'file',multiple:true,hidden:true,accept:'.txt,.md,.csv,.tsv,.json,.html,.htm,.rtf,.doc,.docx,.pdf,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff',onChange:e=>{void upload(e.target.files);e.target.value='';}}),
            h('button',{className:'qx-kb-primary',disabled:busy,onClick:()=>file.current.click()},busy?'正在处理…':'上传资料'),
            h('button',{disabled:busy,onClick:()=>{setArchived(!archived);setOffset(0);setResults(null);setSource(null);}},archived?'返回资料库':'已归档')),
          h('div',{className:'qx-kb-toolbar'},
            h('button',{disabled:busy,onClick:backup},'备份知识库'),
            h('input',{ref:backupFile,type:'file',hidden:true,accept:'.zip',onChange:e=>{void restore(e.target.files[0]);e.target.value='';}}),
            h('button',{disabled:busy,onClick:()=>backupFile.current.click()},'从备份恢复'),
            backupUrl&&h('a',{href:backupUrl,download:true},'下载备份'),
            h('span',{className:'qx-kb-muted'},'仅备份已入库资料，文件未加密；恢复只合并，不覆盖已有资料。')),
          h('details',{className:'qx-kb-muted'},h('summary',null,'备份范围与限制'),h('p',null,'包含知识库中已归档资料、入库文件和引用索引。不包含案件、对话，以及脱敏功能单独保管的原始文件和映射记录；脱敏后入库的资料只备份脱敏副本。仅恢复来源可信的本工作台备份；当前支持单份入库文件 512 MiB、展开总量 2 GiB、最多 10,000 份资料、清单 64 MiB。超过限制会停止并提示，不会生成不完整的知识库备份。恢复时请保持工作台开启。')),
          h('form',{className:'qx-kb-toolbar',onSubmit:e=>{e.preventDefault();void search();}},h('input',{type:'search',value:query,onChange:e=>setQuery(e.target.value),maxLength:300,placeholder:'检索原文关键词，如：劳动合同 解除','aria-label':'检索知识库关键词'}),h('button',{type:'submit',disabled:busy||!query.trim()},'检索'),results&&h('button',{type:'button',onClick:()=>{setResults(null);setSource(null);}},'返回列表')),
          (error||loadError)&&h('div',{className:'qx-kb-notice qx-kb-error',role:'alert'},error||loadError),notice&&h('div',{className:'qx-kb-notice',role:'status'},notice),
          source&&h('section',{className:'qx-kb-source','aria-label':'资料原文'},h('div',{className:'qx-kb-pager'},h('h3',null,source.title),h('button',{onClick:()=>setSource(null)},'收起原文')),
            source.chunks.length?source.chunks.map(chunk=>h('article',{key:chunk.ordinal??chunk.citation},
              h('p',{className:'qx-kb-muted'},`${chunk.page?'第 '+chunk.page+' 页 · ':''}${chunk.location}`),h('pre',null,chunk.text),h('button',{disabled:busy,onClick:()=>copy(chunk,source.title)},'复制原文及引用'))):h('p',null,'暂无可读取文字，请完成解析后重试。'),
            source.next_start!==null&&source.next_start!==undefined&&h('button',{disabled:busy,onClick:()=>read(source.document_id,source.next_start)},'下一段')),
          results?h('section',{'aria-label':'检索结果'},h('p',{className:'qx-kb-muted'},'仅显示未归档且已解析的资料。原文关键词检索，不代表语义检索或现行法律核验。'),
            results.matches.length?results.matches.map(item=>h('article',{className:'qx-kb-result',key:item.citation},h('h3',null,item.title),h('p',{className:'qx-kb-muted'},`${item.category} · ${item.page?'第 '+item.page+' 页 · ':''}${item.location}`),h('blockquote',null,item.excerpt),
              (item.citations||[{citation:item.citation}]).map((ref,index,refs)=>h('button',{key:ref.citation,disabled:busy,onClick:()=>citation(ref.citation)},refs.length>1?`定位第 ${index+1} 段原文`:'定位引用原文')))):h('div',{className:'qx-kb-empty'},'没有找到匹配原文。请尝试更短的关键词，或确认资料已经解析完成。'),
            h('div',{className:'qx-kb-pager'},h('button',{disabled:busy||searchOffset===0,onClick:()=>search(Math.max(0,searchOffset-12))},'上一页'),h('button',{disabled:busy||!results.has_more,onClick:()=>search(searchOffset+12)},'下一页')))
            :h('section',{'aria-label':archived?'已归档资料':'资料列表'},h('p',{className:'qx-kb-muted'},`${archived?'已归档':'资料库'} · 共 ${catalog.total} 份${archived?' · 保留原件，可恢复':''}`),
              catalog.documents.length?h('table',{className:'qx-kb-table'},h('thead',null,h('tr',null,['资料','分类','状态','操作'].map(s=>h('th',{key:s,scope:'col'},s)))),h('tbody',null,catalog.documents.map(d=>h('tr',{key:d.id},h('td',null,h('div',{className:'qx-kb-title'},d.title),h('div',{className:'qx-kb-muted'},new Date(d.created_at).toLocaleDateString('zh-CN')),d.error&&h('div',{className:'qx-kb-error'},d.error),d.warnings?.length>0&&h('div',{className:'qx-kb-muted'},d.warnings.join('；'))),h('td',null,d.category),h('td',null,d.busy?'解析中…':states[d.state]||d.state),h('td',null,docActions(d))))))
                :h('div',{className:'qx-kb-empty'},loading?'正在读取资料…':archived?'还没有归档资料。':'还没有资料。点击“上传资料”，建立属于律所的知识库。'),
              h('div',{className:'qx-kb-pager'},h('button',{disabled:busy||offset===0,onClick:()=>setOffset(Math.max(0,offset-50))},'上一页'),h('button',{disabled:busy||catalog.next_offset===null,onClick:()=>setOffset(catalog.next_offset)},'下一页')))));
    };
  }
  const KnowledgePanel=createKnowledgeView(React);
  function WechatPanel({onClose}){
    const dialog=React.useRef(null),alive=React.useRef(true),refreshVersion=React.useRef(0),actionRunning=React.useRef(false);
    const [state,setState]=React.useState(null),[settings,setSettings]=React.useState(null);
    const [selected,setSelected]=React.useState(''),[busy,setBusy]=React.useState(false);
    const [error,setError]=React.useState(''),[notice,setNotice]=React.useState(''),[code,setCode]=React.useState('');
    async function api(path,options={}){
      const response=await fetch('/qx-wechat/'+path,{credentials:'same-origin',...options});
      if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('连接已失效，请从“工作台 → 重新连接”恢复。');
      const value=await response.json();if(!response.ok)throw new Error(value.error||'操作未完成，请重试。');return value;
    }
    const refresh=React.useCallback(async(signal)=>{
      const version=++refreshVersion.current;
      const [next,options]=await Promise.all([api('state',{signal}),api('settings',{signal})]);
      if(alive.current&&version===refreshVersion.current){setState(next);setSettings(options);setSelected(previous=>previous||next.sessionId||'');}
    },[]);
    React.useEffect(()=>{
      alive.current=true;const element=dialog.current,returnFocus=document.activeElement,controller=new AbortController();let timer;
      element.showModal();
      const poll=async()=>{
        try{if(!actionRunning.current)await refresh(controller.signal)}catch(e){if(!controller.signal.aborted)setError(e.message)}
        finally{if(!controller.signal.aborted)timer=setTimeout(poll,2500)}
      };
      void poll();
      return()=>{alive.current=false;controller.abort();clearTimeout(timer);element.close();if(returnFocus?.isConnected)returnFocus.focus();};
    },[refresh]);
    async function run(action,extra={}){
      if(actionRunning.current||!settings)return;actionRunning.current=true;refreshVersion.current++;setBusy(true);setError('');setNotice('');
      try{
        const result=await api('action',{method:'POST',headers:{'content-type':'application/json','x-qx-token':settings.csrf},body:JSON.stringify({action,...extra})});
        if(!alive.current)return;
        if(action==='session'||action==='new-session')setSelected(result.sessionId);
        if(action==='verify')setCode('');
        await refresh();
        if(alive.current)setNotice(action==='new-session'?'已新建会话，微信将使用这个会话。':action==='session'?'已切换会话，之后的微信消息将进入所选会话。':action==='cancel'?'已取消扫码，可恢复原微信连接。':'');
      }catch(e){if(alive.current)setError(e.message)}finally{actionRunning.current=false;if(alive.current)setBusy(false)}
    }
    const scanning=state?.login&&!['confirmed','cancelled','error','give_up'].includes(state.login.status);
    const processing=state?.batching?.active||state?.batching?.pendingMessages>0;
    const sessions=settings?.sessions||[];
    const bound=sessions.find(row=>row.id===state?.sessionId);
    const titles=new Map();for(const row of sessions)titles.set(row.title,(titles.get(row.title)||0)+1);
    const scanText=state?.login?.status==='activating'?'手机已确认，正在连接新微信…':state?.login?.verifyCodeNeeded?'请填写手机显示的验证码。':state?.login?.status==='scaned'?'已扫码，请在手机上确认连接。':'请使用要连接的微信扫描二维码，并在手机确认。';
    const closeIcon=h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.6,'aria-hidden':true},h('path',{d:'m6 6 12 12M18 6 6 18',strokeLinecap:'round'}));
    return h('dialog',{className:'qx-wx',ref:dialog,'aria-labelledby':'qx-wx-title',onCancel:e=>{e.preventDefault();onClose()},onClick:e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose()}}},
      h('header',{className:'qx-wx-head'},h('h2',{id:'qx-wx-title'},'微信连接'),h('button',{type:'button',className:'qx-wx-close','aria-label':'关闭微信连接',onClick:onClose},closeIcon)),
      h('div',{className:'qx-wx-body'},
        h('div',{className:'qx-wx-status',role:'status'},h('span',{className:'qx-wx-dot'+(state?.connected?' connected':''),'aria-hidden':true}),h('strong',null,!state?'正在读取连接状态…':state.connected?'微信已连接':scanning?'等待扫码确认':state.owner?'微信接收已暂停':'尚未连接微信')),
        h('p',{className:'qx-wx-muted'},'用微信发送文字、图片和文件，在工作台中继续处理。'),
        state?.owner&&h('p',{className:'qx-wx-owner'},'当前微信：',state.owner),
        h('section',{className:'qx-wx-section'},
          h('label',{htmlFor:'qx-wx-session'},'微信使用的会话'),
          h('div',{className:'qx-wx-session-row'},h('select',{id:'qx-wx-session',value:selected,disabled:busy||!settings||scanning||processing,onChange:e=>setSelected(e.target.value)},
            !sessions.some(row=>row.id===selected)&&h('option',{value:selected},!settings?'正在读取会话…':sessions.length?'当前会话暂不可选':'暂无会话，请新建'),
            sessions.map((row,index)=>h('option',{value:row.id,key:row.id},row.title+(titles.get(row.title)>1?' · '+(index+1):'')))),
            h('button',{type:'button',disabled:busy||scanning||processing||!sessions.some(row=>row.id===selected)||selected===state?.sessionId,onClick:()=>run('session',{sessionId:selected})},'切换会话')),
          h('div',{className:'qx-wx-session-foot'},h('span',{className:'qx-wx-muted'},bound?'当前：'+bound.title:'新建后会自动关联微信。'),h('button',{type:'button',className:'qx-wx-text',disabled:busy||!settings||scanning||processing,onClick:()=>run('new-session')},'新建会话')),
          processing&&h('p',{className:'qx-wx-muted'},'微信消息正在收集或处理，完成后即可切换。')),
        scanning?h('section',{className:'qx-wx-scan','aria-label':'微信扫码'},
          state.login.qrImage&&h('img',{src:state.login.qrImage,alt:'微信连接二维码',width:208,height:208}),
          h('p',{role:'status'},scanText),
          state.login.verifyCodeNeeded&&h('form',{className:'qx-wx-verify',onSubmit:e=>{e.preventDefault();void run('verify',{code:code.trim()})}},h('label',{htmlFor:'qx-wx-code'},'手机验证码'),h('input',{id:'qx-wx-code',value:code,inputMode:'numeric',autoComplete:'one-time-code',onChange:e=>setCode(e.target.value)}),h('button',{disabled:busy||!code.trim(),type:'submit'},'提交验证码')),
          h('button',{type:'button',disabled:busy||state.login.status==='activating',onClick:()=>run('cancel')},'取消扫码')):
          h('div',{className:'qx-wx-actions'},
            h('button',{type:'button',className:'qx-wx-primary',disabled:busy||!settings||processing,onClick:()=>run(state?.owner?'switch-account':'login')},busy?'正在处理…':state?.owner?'重新扫码切换微信':'扫码连接微信'),
            state?.owner&&h('button',{type:'button',disabled:busy||!settings,onClick:()=>run(state.connected?'pause':'resume')},state.connected?'暂停接收':'恢复原微信连接')),
        h('p',{className:'qx-wx-muted qx-wx-help'},scanning?'重新扫码期间暂停接收。取消后可恢复原微信。':'只接收当前连接微信的私聊；重新扫码可以更换微信。'),
        notice&&h('p',{className:'qx-wx-notice',role:'status'},notice),
        (error||state?.lastError||state?.login?.error)&&h('div',{className:'qx-wx-error',role:'alert'},h('p',null,error||state?.lastError||state?.login?.error),h('button',{type:'button',disabled:busy,onClick:()=>{setError('');void refresh().catch(e=>setError(e.message))}},'刷新状态'))));
  }
  class KnowledgeBoundary extends React.Component{
    constructor(props){super(props);this.state={failed:false,message:''};}
    static getDerivedStateFromError(error){return {failed:true,message:String(error?.message||error)};}
    componentDidCatch(error){console.error('群兴知识库界面错误',error);}
    render(){return this.state.failed?h('div',{role:'alert',style:{padding:12,overflowWrap:'anywhere'}},
      h('p',null,'知识库界面未能显示。'),
      h('button',{type:'button',onClick:()=>this.setState({failed:false,message:''})},'重试'),
      h('button',{type:'button',onClick:this.props.onClose},'关闭'),
      h('details',null,h('summary',null,'查看错误信息'),h('pre',{style:{whiteSpace:'pre-wrap'}},this.state.message))):this.props.children;}
  }
  const styles=`
    [data-slot="sidebar"] nav:has([data-slot="sidebar.panellist"]){display:none}
    .qx-wordmark{font-family:inherit;font-size:20px;font-weight:600;letter-spacing:.08em;white-space:nowrap}
    .qx-brand-compact{display:none;font-family:inherit;font-size:11px;font-weight:600;white-space:nowrap}
    [data-sidebar-collapsed=true] .qx-brand-compact{display:inline-flex}
    .qx-sidebar-account{width:100%;min-width:0}
    .qx-wechat-link{box-sizing:border-box;display:flex;align-items:center;gap:10px;min-height:36px;margin:0 4px;padding:8px;border-radius:var(--dsw-radius-sm);color:var(--dsw-alias-label-primary);font:inherit;font-size:14px;line-height:20px;text-decoration:none;transition:background-color 160ms ease-out}
    .qx-wechat-link:hover,.qx-wechat-link:active{background:var(--dsw-alias-interactive-bg-hover)}
    .qx-wechat-link:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary);outline-offset:2px}
    .qx-wechat-link svg{flex:none}
    .qx-sidebar-account-compact{width:36px}
    .qx-sidebar-account-compact .qx-wechat-link{justify-content:center;margin:0;padding:8px}
    .qx-balance{box-sizing:border-box;width:100%;padding:10px 12px 8px;color:var(--dsw-alias-label-primary);font-family:inherit}
    .qx-balance-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;color:var(--dsw-alias-label-secondary);font-size:12px;line-height:20px}
    .qx-balance-values{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:2px;font-size:15px;line-height:24px;font-weight:500;font-variant-numeric:tabular-nums}
    .qx-balance-notice{margin-top:2px;color:var(--dsw-alias-label-secondary);font-size:12px;line-height:18px}
    .qx-balance-refresh{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;height:28px;padding:0;border:0;border-radius:var(--dsw-radius-sm);background:transparent;color:var(--dsw-alias-label-secondary);cursor:pointer;transition:background-color 160ms ease-out}
    .qx-balance-refresh:hover:not(:disabled){background:var(--dsw-alias-interactive-bg-hover)}
    .qx-balance-refresh:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary);outline-offset:2px}
    .qx-balance-refresh:disabled{opacity:.45;cursor:wait}
    .qx-balance-compact{width:36px;padding:4px}
    @media(prefers-reduced-motion:reduce){.qx-balance-refresh,.qx-wechat-link{transition:none}}
    .qx-wx{box-sizing:border-box;width:min(540px,calc(100vw - 32px));max-height:calc(100vh - 48px);padding:0;border:0;border-radius:16px;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#20242b);font-family:inherit;font-size:14px;line-height:1.6;box-shadow:0 20px 64px #14203130;overflow:auto}
    .qx-wx::backdrop{background:#18202a66}.qx-wx *{box-sizing:border-box}.qx-wx p{margin:8px 0}.qx-wx h2{font:inherit;font-size:19px;font-weight:600;margin:0}.qx-wx-head{display:flex;align-items:center;justify-content:space-between;padding:22px 26px 14px}.qx-wx-body{padding:0 26px 24px}.qx-wx button,.qx-wx select,.qx-wx input{font:inherit;color:inherit;min-height:38px;border:1px solid var(--dsw-alias-border-l,#dce0e6);border-radius:8px;background:var(--dsw-alias-bg-base,#fff);padding:7px 12px}.qx-wx button{cursor:pointer;white-space:nowrap}.qx-wx button:hover:enabled{background:var(--dsw-alias-interactive-bg-hover,#f2f4f7)}.qx-wx button:disabled{opacity:.5;cursor:default}.qx-wx select:disabled{opacity:.65}.qx-wx button:focus-visible,.qx-wx select:focus-visible,.qx-wx input:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#4c79ff);outline-offset:3px}.qx-wx .qx-wx-close{display:grid;place-items:center;min-height:32px;width:32px;padding:0;border:0;background:transparent}.qx-wx-status{display:flex;gap:9px;align-items:center}.qx-wx-dot{width:8px;height:8px;border-radius:50%;background:#89919e}.qx-wx-dot.connected{background:#26814b}.qx-wx-muted{color:var(--dsw-alias-label-secondary,#626b78);font-size:13px}.qx-wx-owner{font-size:12px;color:var(--dsw-alias-label-secondary,#626b78);overflow-wrap:anywhere}.qx-wx-section{margin:24px 0;padding-top:20px;border-top:1px solid var(--dsw-alias-border-l,#e6e8ed)}.qx-wx-section label{display:block;font-weight:500;margin-bottom:9px}.qx-wx-session-row{display:flex;gap:8px}.qx-wx select{flex:1;min-width:0;width:100%;text-overflow:ellipsis}.qx-wx-session-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:6px}.qx-wx-session-foot span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.qx-wx .qx-wx-text{border:0;padding:5px 0;background:transparent;color:var(--dsw-alias-state-business-primary,#3f6cdb)}.qx-wx-actions{display:flex;flex-wrap:wrap;gap:10px}.qx-wx .qx-wx-primary{background:var(--dsw-alias-state-business-primary,#4c79ff);border-color:transparent;color:#fff}.qx-wx .qx-wx-primary:hover:enabled{filter:brightness(.94);background:var(--dsw-alias-state-business-primary,#4c79ff)}.qx-wx-help{margin-top:12px!important}.qx-wx-scan{text-align:center;padding:16px 0;background:var(--dsw-alias-interactive-bg-hover,#f7f8fa);border-radius:12px}.qx-wx-scan img{display:block;margin:0 auto;background:#fff;max-width:100%;object-fit:contain}.qx-wx-verify{display:flex;flex-wrap:wrap;gap:8px;padding:8px 16px 16px;text-align:left}.qx-wx-verify label{width:100%}.qx-wx-verify input{flex:1;min-width:80px;width:150px}.qx-wx-notice{color:var(--dsw-alias-label-secondary,#626b78)}.qx-wx-error{margin-top:16px;color:#a12c2c;overflow-wrap:anywhere}.qx-wx-error p{white-space:pre-wrap}.qx-wx-error button{color:inherit}.qx-wx ::selection{background:#dbe6ff}.qx-wx input{caret-color:var(--dsw-alias-state-business-primary,#4c79ff)}
    @media(max-width:500px){.qx-wx-head{padding:18px 18px 12px}.qx-wx-body{padding:0 18px 20px}.qx-wx-actions{flex-direction:column}.qx-wx{max-height:calc(100dvh - 24px)}}
  `;
  function RefreshIcon(){return h('svg',{width:16,height:16,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.6,'aria-hidden':true},h('path',{d:'M19 8a8 8 0 1 0 1 7M19 3v5h-5',strokeLinecap:'round',strokeLinejoin:'round'}));}
  function PhoneIcon(){return h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.6,'aria-hidden':true},h('rect',{x:6,y:2.5,width:12,height:19,rx:2}),h('path',{d:'M10 18.5h4',strokeLinecap:'round'}));}
  function AccountFooter({wide}){
    const [knowledgeOpen,setKnowledgeOpen]=React.useState(false);
    const [wechatOpen,setWechatOpen]=React.useState(false);
    React.useEffect(()=>{
      const open=()=>{window.__qxOpenWechatRequested=false;setWechatOpen(true)};
      window.addEventListener('qx-open-wechat',open);
      if(window.__qxOpenWechatRequested)open();
      return()=>window.removeEventListener('qx-open-wechat',open);
    },[]);
    return h('div',{className:'qx-sidebar-account'+(wide?'':' qx-sidebar-account-compact')},
      h('button',{type:'button',className:'qx-wechat-link',style:{width:'calc(100% - 8px)',border:0,background:'transparent',cursor:'pointer'},'aria-label':'律所知识库',title:'律所知识库',onClick:()=>setKnowledgeOpen(true)},h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.6,'aria-hidden':true},h('path',{d:'M4 3h12a2 2 0 0 1 2 2v16H6a2 2 0 0 1-2-2V3zm0 13h14M8 7h6M8 11h6'})),wide&&h('span',null,'律所知识库')),
      knowledgeOpen&&h(KnowledgeBoundary,{onClose:()=>setKnowledgeOpen(false)},h(KnowledgePanel,{onClose:()=>setKnowledgeOpen(false)})),
      h('button',{type:'button',className:'qx-wechat-link',style:{width:'calc(100% - 8px)',border:0,background:'transparent',cursor:'pointer'},'aria-label':'微信连接',title:'微信连接','aria-haspopup':'dialog',onClick:()=>setWechatOpen(true)},h(PhoneIcon),wide&&h('span',null,'微信连接')),
      wechatOpen&&h(WechatPanel,{onClose:()=>setWechatOpen(false)}),
      h(Balance,{wide}));
  }
  function Balance({wide}){
    const [state,setState]=React.useState({status:'loading',balances:[]});
    const [busy,setBusy]=React.useState(false);
    const refresh=React.useRef(()=>{});
    React.useEffect(()=>{
      const controller=new AbortController();let running=false;
      refresh.current=async(force=false)=>{
        if(running||controller.signal.aborted)return;
        running=true;setBusy(true);
        try{
          const response=await fetch('/api/qx-account/balance'+(force?'?refresh=1':''),{credentials:'same-origin',signal:controller.signal});
          if(!response.ok)throw new Error('余额暂时无法读取');
          const next=await response.json();
          if(!['ok','unavailable','error'].includes(next.status))throw new Error('余额暂时无法读取');
          const balances=Array.isArray(next.balances)?next.balances.filter(row=>['CNY','USD'].includes(row.currency)&&typeof row.total_balance==='string'&&/^-?\d+(\.\d+)?$/.test(row.total_balance)):[];
          if(next.status==='ok'&&!balances.length)throw new Error('余额暂时无法读取');
          setState(previous=>({...next,balances:next.status==='ok'?balances:next.status==='error'?previous.balances:[]}));
        }catch(error){
          if(error.name!=='AbortError')setState(previous=>({...previous,status:'error',error:'暂时无法读取余额，请刷新重试。'}));
        }finally{running=false;if(!controller.signal.aborted)setBusy(false);}
      };
      const visibleRefresh=()=>{if(document.visibilityState==='visible')void refresh.current();};
      void refresh.current();
      const timer=setInterval(visibleRefresh,60000);
      document.addEventListener('visibilitychange',visibleRefresh);
      window.addEventListener('focus',visibleRefresh);
      return()=>{controller.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visibleRefresh);window.removeEventListener('focus',visibleRefresh);};
    },[]);
    const values=state.balances.map(row=>`${row.total_balance} ${row.currency}`);
    const notice=state.status==='loading'?'读取中…':state.status==='unavailable'?'暂未配置 DeepSeek 账户':state.status==='error'?(values.length?'更新失败，显示上次余额':'暂时无法读取，请刷新重试'):'';
    const button=h('button',{type:'button',className:'qx-balance-refresh',disabled:busy,'aria-label':'刷新 DeepSeek 余额',title:['DeepSeek 余额',...values,notice].filter(Boolean).join(' · '),onClick:()=>refresh.current(true)},h(RefreshIcon));
    if(!wide)return h('div',{className:'qx-balance qx-balance-compact','data-qx-balance':state.status},button);
    return h('section',{className:'qx-balance','data-qx-balance':state.status,'aria-label':'DeepSeek 余额'},
      h('div',{className:'qx-balance-heading'},h('span',null,'DeepSeek 余额'),button),
      h('div',{'aria-live':'polite','aria-atomic':true},values.length>0&&h('div',{className:'qx-balance-values'},values.map(value=>h('span',{key:value},value))),notice&&h('div',{className:'qx-balance-notice'},notice)));
  }
  return {inject:['sessions','uiWorkspace','slots'],apply(ctx){
    ctx.effect(()=>{
      const script=document.createElement('script');script.src='/api/qx-privacy/client.js';script.async=true;
      script.onerror=()=>console.warn('群兴：上传脱敏组件暂未加载，可刷新工作台重试；当前上传保持原流程。');
      document.head.append(script);
      return()=>{window.qxPrivacy?.dispose();script.remove();};
    },'qunxing: optional upload privacy');
    ctx.effect(()=>{const style=document.createElement('style');style.dataset.qxChrome='true';style.textContent=styles;document.head.append(style);return()=>style.remove();},'qunxing: concise desktop chrome');
    ctx.slots.inject('sidebar.brand.mark',()=>ctx.slots.register({name:'sidebar.brand.mark',priority:-100},()=>h('span',{className:'qx-brand-compact'},'群兴')));
    ctx.slots.inject('sidebar.brand.name',()=>ctx.slots.register({name:'sidebar.brand.name',priority:-100},()=>h('span',{className:'qx-wordmark'},'群兴')));
    ctx.slots.inject('conversation.hero.brand.mark',()=>ctx.slots.register({name:'conversation.hero.brand.mark',priority:-100},()=>null));
    ctx.slots.inject('settings.launcher',()=>ctx.slots.register({name:'settings.launcher',priority:-100},()=>null));
    ctx.slots.inject('sidebar.footer.action',()=>ctx.slots.register({name:'sidebar.footer.action',id:'qx-balance',order:100},AccountFooter));
    // A plugin hot reload must not move a window the user is already working in.
    let opened=Boolean(document.documentElement.dataset.qxSessionId);
    let shared;
    function synchronize(){
      const rows=Object.values(ctx.sessions.list.getSnapshot().byId);
      const selected=rows.find(row=>(row.retainedBy.mainView||0)>0);
      document.documentElement.dataset.qxSessionId=selected?.id||'';
      if(!opened&&shared&&rows.some(row=>row.id===shared)){
        opened=true;
        ctx.uiWorkspace.openSession(shared);
      }
    }
    ctx.effect(()=>{
      const remove=ctx.sessions.list.subscribe(synchronize);
      const controller=new AbortController();
      synchronize();
      if(!opened){
        fetch('/qx-wechat/state',{credentials:'same-origin',signal:controller.signal})
          .then(response=>{if(!response.ok)throw new Error('Session unavailable');return response.json();})
          .then(state=>{
            if(controller.signal.aborted)return;
            shared=typeof state.sessionId==='string'?state.sessionId:undefined;
            synchronize();
          }).catch(error=>{if(error.name!=='AbortError')console.warn('群兴：暂未读取到手机共用会话，保留当前选择。');});
      }
      return()=>{controller.abort();remove();};
    },'qunxing: shared desktop session');
  }};
}});
