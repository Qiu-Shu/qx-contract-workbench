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
    return function KnowledgePanel({onClose,onGraph}){
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
        const session=document.documentElement.dataset.qxSessionId||'';
        await act(async()=>{
          const failed=[];let count=0;
          for(const item of selected){
            setNotice(`正在上传 ${count+failed.length+1}/${selected.length}：${item.name}`);
            try{const result=await api('upload',{method:'POST',headers:{'content-type':'application/octet-stream','x-qx-filename':encodeURIComponent(item.name),...(session?{'x-qx-session':session}:{}),...(category.trim()?{'x-qx-category':encodeURIComponent(category.trim())}:{})},body:item});count++;if(result.linkWarning)failed.push(`${item.name}：${result.linkWarning}`);}
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
        h('header',{className:'qx-kb-head'},h('div',null,h('h2',{id:'qx-kb-heading'},'资料库'),h('p',{className:'qx-kb-muted'},'本机保存 · 原文可追溯')),h('button',{className:'qx-kb-close',disabled:busy,onClick:onClose,'aria-label':'关闭知识库'},'×')),
        h('div',{className:'qx-kb-body'},
          h('div',{className:'qx-kb-toolbar'},h('button',{onClick:onGraph},'返回知识库')),
          h('p',{className:'qx-kb-muted'},'上传律所范本、办案经验、制度与研究资料。上传和检索在本机完成；用于 AI 问答的片段会发送给当前配置的模型。'),
          h('div',{className:'qx-kb-toolbar'},
            h('input',{ref:file,type:'file',multiple:true,hidden:true,accept:'.txt,.md,.csv,.tsv,.json,.html,.htm,.rtf,.doc,.docx,.pdf,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff',onChange:e=>{void upload(e.target.files);e.target.value='';}}),
            h('button',{className:'qx-kb-primary',disabled:busy,onClick:()=>file.current.click()},busy?'正在处理…':'上传资料'),h('span',{className:'qx-kb-muted'},'自动分类，并关联当前工作。')),
          h('details',null,h('summary',null,'资料管理与备份'),h('div',{className:'qx-kb-toolbar'},
            h('input',{value:category,onChange:e=>setCategory(e.target.value),placeholder:'自动分类，可手动指定',maxLength:80,'aria-label':'上传资料分类'}),
            h('button',{disabled:busy,onClick:()=>{setArchived(!archived);setOffset(0);setResults(null);setSource(null);}},archived?'返回资料库':'已归档'),
            h('button',{disabled:busy,onClick:backup},'备份知识库'),
            h('input',{ref:backupFile,type:'file',hidden:true,accept:'.zip',onChange:e=>{void restore(e.target.files[0]);e.target.value='';}}),
            h('button',{disabled:busy,onClick:()=>backupFile.current.click()},'从备份恢复'),
            backupUrl&&h('a',{href:backupUrl,download:true},'下载备份'),
            h('span',{className:'qx-kb-muted'},'仅备份已入库资料，文件未加密；恢复只合并，不覆盖已有资料。')),
          h('p',{className:'qx-kb-muted'},'包含知识库中已归档资料、入库文件和引用索引。不包含案件、对话，以及脱敏功能单独保管的原始文件和映射记录；脱敏后入库的资料只备份脱敏副本。仅恢复来源可信的本工作台备份；当前支持单份入库文件 512 MiB、展开总量 2 GiB、最多 10,000 份资料、清单 64 MiB。超过限制会停止并提示，不会生成不完整的知识库备份。恢复时请保持工作台开启。')),
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
  const LibraryPanel=createKnowledgeView(React);
  function KnowledgePanel({onClose,onMemory,initialProject='',onScopeChange}){
    const [graph,setGraph]=React.useState(true),[ready,setReady]=React.useState(!!window.qxKnowledgePanel);
    const [scope,setScope]=React.useState(initialProject);
    const changeScope=value=>{setScope(value);onScopeChange?.(value);};
    React.useEffect(()=>{const loaded=()=>setReady(true);window.addEventListener('qx-knowledge-ready',loaded);return()=>window.removeEventListener('qx-knowledge-ready',loaded);},[]);
    if(graph&&ready&&window.qxKnowledgePanel)return h(window.qxKnowledgePanel,{onClose,onMemory,initialProject:scope,onScopeChange:changeScope,onLibrary:()=>setGraph(false)});
    return h(LibraryPanel,{onClose,onGraph:()=>{if(window.qxKnowledgePanel){setReady(true);setGraph(true);}else window.alert('工作知识组件正在加载，请稍后重试。');}});
  }
  function createMemoryView(React){
    const h=React.createElement;
    const css=`
      .qx-memory{width:min(940px,94vw);max-height:90vh;padding:0;border:1px solid #d7dce4;border-radius:12px;background:#fff;color:#172a3d;font:14px/1.65 "Microsoft YaHei",system-ui,sans-serif;box-shadow:0 18px 65px #10203030}
      .qx-memory::backdrop{background:#15293d70}.qx-memory *{box-sizing:border-box}.qx-memory ::selection{background:#d6e7f6}.qx-memory header{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:18px 24px;border-bottom:1px solid #e1e6ed}.qx-memory h2{margin:0;font-size:22px}.qx-memory h3{margin:0 0 10px;font-size:16px}.qx-memory p{margin:8px 0}.qx-memory-body{padding:20px 24px;max-height:calc(90vh - 80px);overflow:auto;scrollbar-color:#9aafc2 #f4f7fa}
      .qx-memory button,.qx-memory input,.qx-memory select,.qx-memory textarea{font:inherit;max-width:100%;color:inherit}.qx-memory button{border:1px solid #b8c4d2;border-radius:6px;background:#fff;padding:8px 12px;color:#173c65;cursor:pointer;touch-action:manipulation}.qx-memory button:hover:enabled{background:#edf3f8}.qx-memory button:disabled{opacity:.55;cursor:default}.qx-memory button.primary{background:#235b91;color:#fff;border-color:#235b91}.qx-memory button.danger{color:#9c3321;border-color:#bb7567}.qx-memory input:not([type=checkbox]),.qx-memory select,.qx-memory textarea{width:100%;padding:9px 12px;border:1px solid #b8c4d2;border-radius:6px;background:#fff;caret-color:#235b91}.qx-memory textarea{min-height:120px;resize:vertical;line-height:1.75}.qx-memory input::placeholder,.qx-memory textarea::placeholder{color:#58687a;opacity:1}.qx-memory input[type=checkbox]{accent-color:#235b91;width:17px;height:17px;margin:0}
      .qx-memory :is(button,input,select,textarea,summary):focus-visible{outline:2px solid #235ba0;outline-offset:3px}.qx-memory label{display:block}.qx-memory .check{display:flex;align-items:center;gap:9px}.qx-memory .muted{color:#58687a;font-size:13px}.qx-memory .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0}.qx-memory .row>input{flex:1;min-width:180px}.qx-memory .field{margin:14px 0}.qx-memory .field>span{display:block;margin-bottom:6px}.qx-memory .notice{padding:10px 14px;background:#eef4fa;margin:12px 0;white-space:pre-wrap;overflow-wrap:anywhere}.qx-memory .error{color:#8e351a;background:#fff1ec}.qx-memory .section{margin-top:22px;padding-top:20px;border-top:1px solid #e1e6ed}.qx-memory article{padding:18px 0;border-bottom:1px solid #e1e6ed}.qx-memory .body-text{white-space:pre-wrap;overflow-wrap:anywhere;max-width:75ch}.qx-memory pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto;background:#f5f8fb;padding:14px}.qx-memory details{margin:10px 0}.qx-memory summary{cursor:pointer}.qx-memory .pager{display:flex;justify-content:space-between;gap:10px;margin:12px 0}.qx-memory .confirm{padding:16px;background:#fff5ef;margin:14px 0}.qx-memory .empty{padding:24px 0;color:#58687a}.qx-memory .case-select{max-width:100%}
      @media(max-width:650px){.qx-memory{width:96vw}.qx-memory header,.qx-memory-body{padding:16px}.qx-memory h2{font-size:20px}.qx-memory .row>input{width:100%;flex-basis:100%}.qx-memory button{min-height:40px}.qx-memory .row{gap:8px}}
    `;
    async function api(path,options={}){
      const response=await fetch('/api/qx-case-memory/'+path,{credentials:'same-origin',cache:'no-store',...options,
        headers:{'x-qx-case-memory':'1',...(options.body?{'content-type':'application/json'}:{}),...options.headers}});
      if(response.status===401||response.status===403)throw Error('工作台连接已失效，请从“工作台 → 重新连接”恢复。');
      if(!response.headers.get('content-type')?.includes('application/json'))throw Error('案件记忆服务暂时不可用，请稍后重试。');
      const value=await response.json();if(!response.ok)throw Error(value.error||'操作未完成，请重试。');return value;
    }
    const post=(path,value)=>api(path,{method:'POST',body:JSON.stringify(value)});
    const kinds={fact:'事实记录',timeline:'时间线',consultation:'接待记录',client_reply:'客户回复',internal_note:'内部笔记',todo:'待办',manual:'手工记忆'};
    function CaseMemories({caseId,enabled,onStatus}){
      const alive=React.useRef(true),cancelDelete=React.useRef(null),listVersion=React.useRef(0);
      const [catalog,setCatalog]=React.useState({memories:[],total:0,next_offset:null}),[offset,setOffset]=React.useState(0);
      const [loading,setLoading]=React.useState(true),[busy,setBusy]=React.useState(false),[error,setError]=React.useState(''),[notice,setNotice]=React.useState('');
      const [query,setQuery]=React.useState(''),[results,setResults]=React.useState(null),[adding,setAdding]=React.useState(false);
      const [mode,setMode]=React.useState('note'),[notes,setNotes]=React.useState({notes:[],total:0,next_offset:null}),[noteOffset,setNoteOffset]=React.useState(0),[noteId,setNoteId]=React.useState('');
      const [content,setContent]=React.useState(''),[source,setSource]=React.useState(''),[confirmed,setConfirmed]=React.useState(false);
      const [editing,setEditing]=React.useState(null),[editContent,setEditContent]=React.useState(''),[deleting,setDeleting]=React.useState(null);
      React.useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
      const load=React.useCallback(async()=>{const version=++listVersion.current;const next=await api(`list?case_id=${caseId}&offset=${offset}`);if(alive.current&&version===listVersion.current)setCatalog(next);},[caseId,offset]);
      React.useEffect(()=>{let cancelled=false;setLoading(true);setError('');void load().catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[load]);
      React.useEffect(()=>{
        if(!adding||mode!=='note')return;const controller=new AbortController();setNoteId('');
        void api(`sources?case_id=${caseId}&offset=${noteOffset}`,{signal:controller.signal}).then(next=>{if(!controller.signal.aborted)setNotes(next);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
        return()=>controller.abort();
      },[caseId,adding,mode,noteOffset]);
      React.useEffect(()=>{if(deleting)cancelDelete.current?.focus();},[deleting]);
      async function act(task){setBusy(true);setError('');try{await task();}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
      async function refresh(){await load();if(alive.current)await onStatus();}
      async function readSource(item){await act(async()=>{
        const current=await api(`read?case_id=${caseId}&memory_id=${item.id}`);if(!alive.current)return;
        setCatalog(previous=>({...previous,memories:previous.memories.map(value=>value.id===current.id?current:value)}));
        setResults(previous=>previous?{...previous,matches:previous.matches.map(value=>value.id===current.id?current:value)}:null);
      });}
      async function add(){await act(async()=>{
        await post('add',mode==='note'?{case_id:caseId,note_id:noteId}:{case_id:caseId,content,source,confirmed});
        if(!alive.current)return;setAdding(false);setContent('');setSource('');setConfirmed(false);setNoteId('');setResults(null);
        setNotice('已保存到本案记忆。后台同步不影响本机查看。');await refresh();
      });}
      async function update(){await act(async()=>{
        await post('update',{case_id:caseId,memory_id:editing.id,revision:editing.revision,content:editContent});
        if(!alive.current)return;setEditing(null);setResults(null);setNotice('记忆已修订，保存时的来源原文保留。');await refresh();
      });}
      async function remove(){await act(async()=>{
        const result=await post('delete',{case_id:caseId,memory_id:deleting.id,revision:deleting.revision});
        if(!alive.current)return;setDeleting(null);setResults(null);
        setNotice(result.pending_cleanup?'本机记忆已删除，案件原始记录保留。增强服务中的旧索引待后台清理，请留意上方状态。':'本机记忆已删除，案件原始记录保留。');await refresh();
      });}
      const selectedNote=notes.notes.find(item=>item.id===noteId);
      const shown=results?results.matches:catalog.memories;
      return h('section',{className:'section','aria-label':'本案记忆内容'},
        h('div',{className:'row'},h('h3',null,`本案记忆 · ${catalog.total} 条`),h('button',{type:'button',disabled:busy||!enabled,onClick:()=>{setAdding(!adding);setEditing(null);setDeleting(null);setError('');}},adding?'收起添加':'添加记忆'),h('button',{type:'button',disabled:busy,onClick:()=>act(async()=>{setResults(null);await refresh();})},'刷新列表')),
        !enabled&&h('p',{className:'notice'},'记忆已关闭，已有记录仍可查看、修订和删除。开启后才能添加或检索。'),
        error&&h('p',{className:'notice error',role:'alert'},error),notice&&h('p',{className:'notice',role:'status'},notice),
        adding&&h('form',{className:'section',onSubmit:e=>{e.preventDefault();void add();},'aria-label':'添加案件记忆'},
          h('label',{className:'field'},h('span',null,'记忆来源'),h('select',{'aria-label':'记忆来源',value:mode,disabled:busy,onChange:e=>setMode(e.target.value)},h('option',{value:'note'},'选择本案记录'),h('option',{value:'manual'},'手工填写已确认内容'))),
          h('p',{className:'muted'},'单条记忆最多 16000 字，每案最多 500 条。较长记录不在选择列表中，可手工摘录重点并注明来源。'),
          mode==='note'?h(React.Fragment,null,
            h('label',{className:'field'},h('span',null,'选择一条记录'),h('select',{'aria-label':'选择一条记录',value:noteId,disabled:busy,onChange:e=>setNoteId(e.target.value)},h('option',{value:''},'请选择要保存的本案记录'),notes.notes.map(item=>h('option',{key:item.id,value:item.id},`${kinds[item.kind]||item.kind} · ${item.content.slice(0,65)}`)))),
            h('p',{className:'muted'},'只列出本案当前版本、正文不超过 16,000 字的记录。不会读取全部聊天或其他案件正文。'),
            selectedNote&&h('div',null,h('p',{className:'muted'},`来源：${selectedNote.source||'案件记录'} · ${kinds[selectedNote.kind]||selectedNote.kind}`),h('pre',null,selectedNote.content)),
            h('div',{className:'pager'},h('button',{type:'button',disabled:busy||noteOffset===0,onClick:()=>setNoteOffset(Math.max(0,noteOffset-20))},'上一页记录'),h('button',{type:'button',disabled:busy||notes.next_offset==null,onClick:()=>setNoteOffset(notes.next_offset)},'下一页记录')))
            :h(React.Fragment,null,h('label',{className:'field'},h('span',null,'来源说明'),h('input',{value:source,onChange:e=>setSource(e.target.value),maxLength:1000,required:true,disabled:busy,placeholder:'例如：2026年11月4日，客户电话确认'})),
              h('label',{className:'field'},h('span',null,'记忆正文'),h('textarea',{value:content,onChange:e=>setContent(e.target.value),maxLength:16000,required:true,disabled:busy})),
              h('label',{className:'check'},h('input',{type:'checkbox',checked:confirmed,onChange:e=>setConfirmed(e.target.checked),disabled:busy,required:true}),'我已核对上述内容和来源')),
          h('p',{className:'muted'},'仅保存你选中的这一条。增强服务运行时，该记忆片段会交由当前配置的 DeepSeek 处理。'),
          h('button',{type:'submit',className:'primary',disabled:busy||!enabled||(mode==='note'?!noteId:!content.trim()||!source.trim()||!confirmed)},busy?'正在保存…':'保存到本案记忆')),
        h('form',{className:'row',onSubmit:e=>{e.preventDefault();void act(async()=>{const found=await api(`recall?case_id=${caseId}&query=${encodeURIComponent(query.trim())}`);if(alive.current){setResults(found);setEditing(null);setDeleting(null);}});}},
          h('input',{type:'search',value:query,onChange:e=>setQuery(e.target.value),maxLength:300,'aria-label':'检索本案记忆',placeholder:'检索本案已保存的记忆'}),h('button',{type:'submit',disabled:busy||!enabled||!query.trim()},'检索记忆'),results&&h('button',{type:'button',onClick:()=>setResults(null)},'返回全部')),
        results&&h('p',{className:'muted'},results.mode==='hindsight'?'增强记忆检索 · 最多显示 10 条；结果均对应本案保存的来源。':results.mode==='disabled'?'本案记忆已关闭。':'当前使用本机关键词匹配 · 增强服务未就绪或暂不可用，最多显示 10 条。'),
        deleting&&h('section',{className:'confirm','aria-labelledby':'qx-memory-delete-title'},h('h3',{id:'qx-memory-delete-title'},'确认删除这条记忆？'),h('p',null,'将删除这条派生记忆及其来源快照；案件原始记录和原文件保留。增强服务离线时，旧索引需等待服务恢复后清理。'),h('p',{className:'body-text'},deleting.content.slice(0,200)),h('div',{className:'row'},h('button',{ref:cancelDelete,type:'button',disabled:busy,onClick:()=>setDeleting(null)},'取消删除'),h('button',{type:'button',className:'danger',disabled:busy,onClick:remove},'确认删除此记忆'))),
        editing&&h('form',{className:'section',onSubmit:e=>{e.preventDefault();void update();},'aria-label':'修订案件记忆'},h('h3',null,`修订记忆 · 版本 ${editing.revision}`),h('p',{className:'muted'},'这里只修改派生记忆，来源原文保持不变。若记录已被他人修改，将提示刷新。'),h('label',{className:'field'},h('span',null,'修订后的记忆正文'),h('textarea',{value:editContent,onChange:e=>setEditContent(e.target.value),maxLength:16000,required:true,disabled:busy})),h('div',{className:'row'},h('button',{type:'submit',className:'primary',disabled:busy||!editContent.trim()},'保存修订'),h('button',{type:'button',disabled:busy,onClick:()=>setEditing(null)},'取消修订'))),
        shown.length?shown.map(item=>h('article',{key:item.id,'aria-label':'记忆条目'},h('p',{className:'body-text'},item.content),
          h('p',{className:'muted'},`来源：${item.source?.label||'案件记录'} · 版本 ${item.revision} · ${new Date(item.updated_at).toLocaleDateString('zh-CN')}`),
          (item.source_warning||item.source_stale||item.source_changed)&&h('p',{className:'notice error'},`${item.source_warning||'来源记录已被更正，此记忆不再参与检索。'} 请重新选择本案当前记录；修订记忆不会更新来源。`),
          h('details',{onToggle:e=>{if(e.currentTarget.open)void readSource(item);}},h('summary',null,'查看保存时的来源原文'),h('p',{className:'muted'},item.source_note_id?`来自本案选中的${kinds[item.source?.kind]||'记录'}。后续对记忆的修订不会改写这份快照。`:'来自你确认的手工内容。'),h('pre',null,item.source?.snapshot||'来源原文暂不可用，请刷新重试。')),
          h('div',{className:'row'},h('button',{type:'button',disabled:busy,onClick:()=>{setEditing(item);setEditContent(item.content);setDeleting(null);setAdding(false);setError('');}},'修订记忆'),h('button',{type:'button',className:'danger',disabled:busy,onClick:()=>{setDeleting(item);setEditing(null);setAdding(false);setError('');}},'删除记忆'))))
          :h('p',{className:'empty'},loading?'正在读取本案记忆…':results?'没有匹配的本案记忆，请尝试其他关键词。':'本案还没有记忆。可选择一条案件记录，或手工填写有明确来源的内容。'),
        !results&&h('div',{className:'pager'},h('button',{type:'button',disabled:busy||offset===0,onClick:()=>setOffset(Math.max(0,offset-20))},'上一页记忆'),h('button',{type:'button',disabled:busy||catalog.next_offset==null,onClick:()=>setOffset(catalog.next_offset)},'下一页记忆')));
    }
    return function MemoryPanel({onClose,initialCase=null}){
      const dialog=React.useRef(null),alive=React.useRef(true),generation=React.useRef(0),selectedCase=React.useRef(null);
      const [cases,setCases]=React.useState({cases:[],total:0,next_offset:null}),[caseOffset,setCaseOffset]=React.useState(0),[caseQuery,setCaseQuery]=React.useState(''),[caseSearch,setCaseSearch]=React.useState('');
      const [chosen,setChosen]=React.useState(initialCase),[status,setStatus]=React.useState(null),[runtime,setRuntime]=React.useState(null);
      const [busy,setBusy]=React.useState(false),[error,setError]=React.useState(''),[notice,setNotice]=React.useState('');
      selectedCase.current=chosen?.id||null;
      React.useEffect(()=>{alive.current=true;const element=dialog.current,previous=document.activeElement;element.showModal();return()=>{alive.current=false;if(element.open)element.close();previous?.focus?.();};},[]);
      React.useEffect(()=>{const controller=new AbortController();void api(`list_cases?offset=${caseOffset}&query=${encodeURIComponent(caseSearch)}`,{signal:controller.signal}).then(setCases).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();},[caseOffset,caseSearch]);
      const refresh=React.useCallback(async()=>{
        const caseId=chosen?.id||null;
        if(!alive.current||selectedCase.current!==caseId)return;
        const turn=++generation.current;
        const [next,engine]=await Promise.all([api('status'+(chosen?'?case_id='+chosen.id:'')),api('runtime-status')]);
        if(alive.current&&selectedCase.current===caseId&&generation.current===turn){setStatus(next);setRuntime(engine);}
      },[chosen?.id]);
      React.useEffect(()=>{let cancelled=false,timer;setStatus(null);
        const poll=async()=>{try{await refresh();}catch(e){if(!cancelled)setError(e.message);}finally{if(!cancelled)timer=setTimeout(poll,5000);}};void poll();
        return()=>{cancelled=true;++generation.current;clearTimeout(timer);};
      },[refresh]);
      async function act(task){setBusy(true);setError('');try{await task();await refresh();}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
      const states={empty:'尚未加入记忆',disabled:'已关闭',unconfigured:'增强服务未配置 · 使用本机记忆',pending:'待同步 · 使用本机记忆',syncing:'正在同步 · 本机记忆可用',ready:'增强记忆已同步',error:'增强服务暂不可用 · 使用本机记忆'};
      const runtimeStates={'not-installed':'增强引擎尚未准备',installing:'正在下载和准备增强引擎',starting:'增强引擎正在启动',ready:'增强引擎已启动',error:'增强引擎准备未完成',stopped:'增强引擎已停止',unavailable:'当前环境未提供一键准备'};
      const preparing=runtime&&['installing','starting'].includes(runtime.phase);
      return h('dialog',{ref:dialog,className:'qx-memory','aria-labelledby':'qx-memory-heading',onCancel:e=>{e.preventDefault();onClose();}},h('style',null,css),
        h('header',null,h('h2',{id:'qx-memory-heading'},'案件记忆'),h('button',{type:'button',onClick:onClose,'aria-label':'关闭案件记忆'},'关闭')),
        h('div',{className:'qx-memory-body'},
          h('p',null,'按案件保存你明确选择的记录。默认开启，可随时关闭；各案分别保存，不自动收录全部聊天。'),
          h('p',{className:'muted'},'记忆是办案提示，不是证据。请核对来源原文；启用增强服务后，选定的记忆片段会发送给当前配置的 DeepSeek 处理。'),
          error&&h('p',{className:'notice error',role:'alert'},error),notice&&h('p',{className:'notice',role:'status'},notice),
          h('div',{className:'row'},h('label',{className:'check'},h('input',{type:'checkbox',checked:status?.global_enabled??false,disabled:busy||!status,onChange:e=>{const enabled=e.target.checked;void act(()=>post('settings',{enabled}));}}),'启用案件记忆（全局）'),
            h('span',{className:'muted',role:'status'},status?(status.global_enabled?'已开启':'已关闭'):'正在读取状态…')),
          h('section',{'aria-label':'增强记忆服务'},h('p',{className:'muted',role:'status'},runtime?runtimeStates[runtime.phase]||'正在读取增强服务状态…':'正在读取增强服务状态…'),
            runtime&&runtime.phase!=='ready'&&runtime.phase!=='unavailable'&&h('button',{type:'button',disabled:busy||preparing,onClick:()=>act(async()=>{await post('prepare',{});setNotice('已开始在后台准备增强引擎，可以继续使用本机记忆。');})},preparing?'正在准备…':'一键准备增强记忆'),
            h('details',{className:'muted'},h('summary',null,'增强服务与本机记录'),h('p',null,'增强引擎首次准备需要下载组件。增强索引可重建，本机保存的选定记录与来源仍为依据；服务不可用时，页面继续提供本机查看与关键词检索。'))),
          h('section',{className:'section','aria-label':'选择案件'},h('form',{className:'row',onSubmit:e=>{e.preventDefault();setCaseOffset(0);setCaseSearch(caseQuery.trim());}},h('input',{type:'search',value:caseQuery,maxLength:300,onChange:e=>setCaseQuery(e.target.value),'aria-label':'查找案件',placeholder:'按案件名称查找'}),h('button',{type:'submit'},'查找案件')),
            h('label',{className:'field'},h('span',null,'当前案件'),h('select',{'aria-label':'当前案件',className:'case-select',value:chosen?.id||'',disabled:busy,onChange:e=>{setStatus(null);setChosen(cases.cases.find(item=>item.id===e.target.value)||null);setNotice('');setError('');}},h('option',{value:''},'请选择案件'),chosen&&!cases.cases.some(item=>item.id===chosen.id)&&h('option',{value:chosen.id},chosen.title),cases.cases.map(item=>h('option',{key:item.id,value:item.id},`${item.title} · ${item.id.slice(0,8)}`)))),
            cases.total>20&&h('div',{className:'pager'},h('button',{type:'button',disabled:caseOffset===0,onClick:()=>setCaseOffset(Math.max(0,caseOffset-20))},'上一页案件'),h('button',{type:'button',disabled:cases.next_offset==null,onClick:()=>setCaseOffset(cases.next_offset)},'下一页案件')),
            !cases.total&&h('p',{className:'muted'},'没有找到案件。请先在办案流程中建立案件，再选择要保存的记录。')),
          chosen&&h(React.Fragment,null,h('div',{className:'row'},h('label',{className:'check'},h('input',{type:'checkbox',checked:status?.case_enabled??false,disabled:busy||!status||!status.global_enabled,onChange:e=>{const enabled=e.target.checked;void act(()=>post('settings',{case_id:chosen.id,enabled}));}}),'本案使用记忆'),
            h('span',{className:'muted',role:'status'},status?states[status.sync_state]||'正在读取本案状态…':'正在读取本案状态…'),
            h('button',{type:'button',disabled:busy||!status?.service_configured,onClick:()=>act(()=>post('sync',{case_id:chosen.id}))},'重试同步')),
            status?.pending_cleanup>0&&h('p',{className:'notice',role:'status'},`有 ${status.pending_cleanup} 份旧增强索引待清理。删除或修订已在本机生效，旧索引清理尚未确认。`),
            status?.last_error&&h('p',{className:'notice error'},status.last_error),
            h(CaseMemories,{key:chosen.id,caseId:chosen.id,enabled:Boolean(status?.enabled),onStatus:refresh})),
          !chosen&&h('p',{className:'empty'},'选择案件后查看该案记忆和可选来源。')));
    };
  }
  const MemoryPanel=createMemoryView(React);
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
  .qx-wordmark{font-family:inherit;font-size:16px;font-weight:600;letter-spacing:.02em;white-space:nowrap}
  .qx-brand-compact{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;height:34px}
  .qx-brand-logo{display:block;width:100%;height:100%;object-fit:contain}
  [data-slot="sidebar"] :has(> span > .qx-brand-compact){min-height:34px}
  span:has(> span > [data-slot="sidebar.brand.mark"]){min-height:34px}
    .qx-sidebar-account{width:100%;min-width:0}
    .qx-upgrade{display:flex;align-items:center;gap:10px;width:calc(100% - 8px);min-height:38px;margin:0 4px 6px;padding:8px 10px;border:1px solid #d4a72c;border-radius:6px;background:#ffdc69;color:#3b2b00;font-family:inherit;font-size:14px;font-weight:600;line-height:20px;cursor:pointer}
    .qx-upgrade:hover{background:#ffd34a}.qx-upgrade:focus-visible,.qx-update-panel button:focus-visible{outline:2px solid #785500;outline-offset:3px}
    .qx-sidebar-account-compact .qx-upgrade{width:36px;margin:0 0 6px;justify-content:center;padding:8px}
    .qx-update-panel{position:fixed;inset:auto auto 100px 250px;width:324px;max-width:calc(100vw - 24px);max-height:calc(100vh - 40px);margin:0;padding:18px;border:1px solid var(--dsw-alias-border-l,#d0d6df);border-radius:10px;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#20242b);font:14px/1.65 "Microsoft YaHei UI",sans-serif;overflow:auto}
    .qx-update-panel p{margin:12px 0}.qx-update-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.qx-update-heading strong{font-size:17px}.qx-update-muted{color:var(--dsw-alias-label-secondary,#596579);font-size:12px}.qx-update-notes{white-space:pre-wrap;overflow-wrap:anywhere;max-height:180px;overflow:auto}.qx-update-panel progress{width:100%;height:8px;accent-color:#b57e00}.qx-update-error{color:#a12e20}.qx-update-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}.qx-update-panel button{font:inherit;padding:6px 10px;min-height:34px;border:1px solid var(--dsw-alias-border-l,#bec7d2);border-radius:6px;background:var(--dsw-alias-bg-base,#fff);color:inherit;cursor:pointer}.qx-update-panel button:hover:enabled{background:var(--dsw-alias-interactive-bg-hover,#f3f5f8)}.qx-update-panel button:disabled{opacity:.55;cursor:default}.qx-update-heading button{border:0;font-size:12px}
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
  function UpdateEntry({wide}){
    const [state,setState]=React.useState(null),[open,setOpen]=React.useState(false);
    const panel=React.useRef(null),button=React.useRef(null);
    React.useEffect(()=>{
      const bridge=window.__QX_UPDATES__;if(!bridge)return;
      let alive=true;const update=value=>{if(alive)setState(value)};
      const unsubscribe=bridge.subscribe(update);bridge.read().then(update).catch(()=>{});
      const show=()=>setOpen(true);window.addEventListener('qx-open-update',show);
      return()=>{alive=false;unsubscribe();window.removeEventListener('qx-open-update',show)};
    },[]);
    React.useEffect(()=>{
      if(!open||!panel.current)return;
      const element=panel.current,anchor=button.current?.getBoundingClientRect();
      element.style.left=Math.max(12,Math.min(window.innerWidth-348,anchor?anchor.right+10:24))+'px';
      element.showPopover();
      const closed=event=>{if(event.newState==='closed')setOpen(false)};
      element.addEventListener('toggle',closed);
      return()=>{element.removeEventListener('toggle',closed);if(element.matches(':popover-open'))element.hidePopover()};
    },[open]);
    if(!state)return null;
    const busy=['checking','downloading','cancelling','confirming','installing'].includes(state.phase);
    const available=Boolean(state.availableVersion);
    const act=action=>{window.__QX_UPDATES__.act(action).then(value=>{if(value)setState(value)}).catch(()=>setState(previous=>({...previous,error:'操作未完成，请重试。'})))};
    const format=bytes=>(bytes/1024/1024).toFixed(1)+' MB';
    const label=state.phase==='downloading'?'下载中 '+Math.floor(state.progress)+'%':state.ready?'安装升级':'升级';
    return h(React.Fragment,null,
      available&&h('button',{ref:button,type:'button',className:'qx-upgrade','aria-label':label,'aria-expanded':open,title:'有新版本 '+state.availableVersion,onClick:()=>setOpen(!open)},
        h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.8,'aria-hidden':true},h('path',{d:'M12 17V4m-5 5 5-5 5 5M5 16v5h14v-5',strokeLinecap:'round',strokeLinejoin:'round'})),wide&&h('span',null,label)),
      open&&h('section',{ref:panel,popover:'auto',className:'qx-update-panel','aria-label':'软件更新'},
        h('div',{className:'qx-update-heading'},h('strong',null,available?'新版本 '+state.availableVersion:'软件更新'),h('button',{type:'button','aria-label':'关闭更新面板',onClick:()=>setOpen(false)},'关闭')),
        h('p',{className:'qx-update-muted'},'当前版本 '+state.version+' · 可继续使用旧版'),
        state.notes&&h('p',{className:'qx-update-notes'},state.notes),
        state.phase==='checking'&&h('p',{role:'status'},'正在检查更新…'),
        state.phase==='idle'&&h('p',{role:'status'},'当前已是最新版本。'),
        state.phase==='available'&&h('p',null,'优先下载变化部分，无法完成时自动下载完整安装包。完成后由你决定何时安装。'),
        ['downloading','cancelling'].includes(state.phase)&&h('div',null,h('progress',{max:100,value:state.progress,'aria-label':'更新下载进度'}),h('p',{role:'status'},state.phase==='cancelling'?'正在取消…':state.downloadMode==='retry'?'连接中断，正在重新尝试增量下载…':state.total?(state.downloadMode==='full'?'已改为完整安装包：':'')+format(state.transferred)+' / '+format(state.total):'正在准备更新…')),
        state.ready&&h('p',null,'更新已下载并校验，可稍后安装。'),
        state.phase==='installing'&&h('p',{role:'status'},'正在关闭后台并启动安装…'),
        state.error&&h('p',{className:'qx-update-error',role:'alert'},state.error),
        h('div',{className:'qx-update-actions'},
          state.phase==='downloading'?h('button',{type:'button',onClick:()=>act('cancel')},'取消下载'):
          state.ready?h('button',{type:'button',disabled:busy,onClick:()=>act('install')},'安装并重启'):
          available?h('button',{type:'button',disabled:busy,onClick:()=>act('download')},state.phase==='error'?'重试下载':'下载更新'):
          h('button',{type:'button',disabled:busy,onClick:()=>act('check')},'重新检查'),
          h('button',{type:'button',onClick:()=>setOpen(false)},'稍后再说'))));
  }
  function createComponentEntry(React){
    const h=React.createElement;
    const labels={idle:'首次使用时下载',cached:'已下载，使用前校验',checking:'正在检查组件…',connecting:'正在连接下载服务…',downloading:'正在下载组件',verifying:'下载完成，正在校验…',installing:'正在安装组件…',cancelling:'正在取消，请稍候…',cancelled:'已取消准备',ready:'组件已就绪',error:'组件准备未完成',unavailable:'组件暂不可用',external:'自定义环境，调用时检查'};
    const css=`.qx-components{position:fixed;inset:0;width:min(440px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;margin:auto;padding:24px;border:1px solid var(--dsw-alias-border-l,#bec7d2);border-radius:10px;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#18202a);font:14px/1.65 system-ui;box-sizing:border-box}.qx-components::backdrop{background:#18202a66}.qx-components h2{font-size:19px;margin:0}.qx-components p{margin:10px 0;overflow-wrap:anywhere}.qx-components header,.qx-component-actions{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}.qx-components button,.qx-component-notice button{font:inherit;min-height:36px;border:1px solid var(--dsw-alias-border-l,#bec7d2);border-radius:6px;padding:6px 12px;background:var(--dsw-alias-bg-base,#fff);color:inherit;cursor:pointer}.qx-components button:disabled{opacity:.6;cursor:default}.qx-components button:focus-visible,.qx-component-notice button:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#3f6cdb);outline-offset:3px}.qx-components progress{width:100%;height:12px;accent-color:var(--dsw-alias-state-business-primary,#3f6cdb)}.qx-component-muted{color:var(--dsw-alias-label-secondary,#626b78)}.qx-component-error{color:var(--dsw-alias-state-error,#a12c2c)}.qx-component-notice{position:fixed;right:16px;bottom:16px;z-index:1000;width:min(360px,calc(100vw - 32px));padding:14px 16px;box-sizing:border-box;border:1px solid var(--dsw-alias-border-l,#bec7d2);border-radius:8px;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#18202a);box-shadow:0 4px 18px #18202a20;font:14px/1.6 system-ui}.qx-component-notice p{margin:0 0 10px;overflow-wrap:anywhere}.qx-component-notice button{min-height:32px}.qx-component-block{border-top:1px solid var(--dsw-alias-border-l,#ddd);margin:16px 0;padding-top:16px}`;
    const format=bytes=>(bytes/1024/1024).toFixed(1)+' MB';
    return function ComponentEntry({wide}){
      const [state,setState]=React.useState(null),[open,setOpen]=React.useState(false),[problem,setProblem]=React.useState('');
      const [offline,setOffline]=React.useState(!navigator.onLine),[restored,setRestored]=React.useState(false),[acting,setActing]=React.useState(false),[dismissed,setDismissed]=React.useState('');
      const panel=React.useRef(null),entry=React.useRef(null),refresh=React.useRef(()=>{}),alive=React.useRef(false),serial=React.useRef(0),mutating=React.useRef(false);
      async function request(action,signal){
        const response=await fetch('/api/qx-components/'+action,{method:action==='status'?'GET':'POST',credentials:'same-origin',signal,headers:{'x-qx-components':'1'}});
        if(response.status===401||response.status===403)throw Error('工作台连接已失效，请在“工作台”菜单中重新连接。');
        if(response.status===404)throw Error('当前会话未启用组件服务，请检查功能设置或重新连接工作台。');
        if(!response.ok)throw Error('组件服务暂时无法连接，请重试。');
        return await response.json();
      }
      React.useEffect(()=>{
        alive.current=true;let timer;const controller=new AbortController();
        refresh.current=async()=>{
          if(controller.signal.aborted||mutating.current)return;
          const order=++serial.current;
          try{const next=await request('status',AbortSignal.any([controller.signal,AbortSignal.timeout(5000)]));if(alive.current&&order===serial.current){setState(next);setProblem('')}}
          catch(error){if(alive.current&&order===serial.current&&!controller.signal.aborted)setProblem(error.name==='TimeoutError'?'组件状态读取超时，请重试。':error.message==='Failed to fetch'?'暂时无法读取本机组件状态，请重试。':error.message)}
        };
        const tick=async()=>{if(document.visibilityState!=='hidden')await refresh.current();if(!controller.signal.aborted)timer=setTimeout(tick,1200)};
        const disconnected=()=>{setOffline(true);setRestored(false)};
        const connected=()=>{setOffline(false);setRestored(true);void refresh.current()};
        const visible=()=>{if(document.visibilityState==='visible')void refresh.current()};
        window.addEventListener('offline',disconnected);window.addEventListener('online',connected);document.addEventListener('visibilitychange',visible);void tick();
        return()=>{alive.current=false;controller.abort();clearTimeout(timer);window.removeEventListener('offline',disconnected);window.removeEventListener('online',connected);document.removeEventListener('visibilitychange',visible)};
      },[]);
      React.useEffect(()=>{
        if(!open)return;const element=panel.current;element.showModal();
        return()=>{if(element.open)element.close();entry.current?.focus()};
      },[open]);
      async function act(action){
        if(mutating.current)return;mutating.current=true;serial.current++;setActing(true);setProblem('');setRestored(false);
        setState(previous=>previous?{...previous,busy:true,phase:action==='cancel'?'cancelling':'checking',error:''}:previous);
        try{const next=await request(action,AbortSignal.timeout(10000));if(alive.current)setState(next)}
        catch(error){if(alive.current)setProblem(error.name==='TimeoutError'?'请求超时，正在核对后台状态。请勿重复点击。':error.message==='Failed to fetch'?'请求未能送达，请检查连接后重试。':error.message)}
        finally{mutating.current=false;if(alive.current){setActing(false);void refresh.current()}}
      }
      const busy=Boolean(state?.busy),retry=['error','cancelled'].includes(state?.phase),ready=state?.phase==='ready',networkFailure=['NETWORK','TIMEOUT','DOWNLOAD_HTTP'].includes(state?.code);
      const noticeKey=state?state.attempt+':'+(['error','ready','cancelled'].includes(state.phase)?state.phase:'working'):'';
      const notice=state&&state.mode==='on-demand'&&state.attempt>0&&noticeKey!==dismissed;
      const status=offline&&!ready?'网络已断开，尚未下载的组件需要联网；本机资料仍可查看。':labels[state?.phase]||'正在读取组件状态…';
      const primary=busy?'取消准备':retry?'重新下载':state?.phase==='cached'?'校验组件':'下载并启用';
      const canPrepare=state?.mode==='on-demand'&&!ready&&state.phase!=='unavailable';
      return h(React.Fragment,null,h('style',null,css),
        h('button',{ref:entry,type:'button',className:'qx-wechat-link',style:{width:'calc(100% - 8px)',border:0,background:'transparent',cursor:'pointer'},'aria-label':'功能组件','aria-haspopup':'dialog',onClick:()=>{setOpen(true);void refresh.current()}},
          h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.6,'aria-hidden':true},h('path',{d:'M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h6v6h-6z'})),wide&&h('span',null,'功能组件')),
        notice&&!open&&h('aside',{className:'qx-component-notice','aria-label':'组件准备状态'},h('p',{role:'status'},status),
          h('div',{className:'qx-component-actions'},h('button',{type:'button',onClick:()=>setOpen(true)},busy?'查看进度':retry?'查看并重试':'查看详情'),h('button',{type:'button',onClick:()=>setDismissed(noticeKey)},'收起'))),
        open&&h('dialog',{ref:panel,className:'qx-components','aria-labelledby':'qx-components-title',onCancel:event=>{event.preventDefault();setOpen(false)}},
          h('header',null,h('h2',{id:'qx-components-title'},'功能组件'),h('button',{type:'button',onClick:()=>setOpen(false),'aria-label':'关闭功能组件'},'关闭')),
          h('p',{className:'qx-component-muted'},'新安装默认全选、启用全部功能。已主动关闭的功能会保留你的设置。'),
          h('p',null,'合同审查、客户接待、知识库、文档处理和基础桌面操作随程序提供。'),
          h('section',{className:'qx-component-block','aria-label':'Windows 高级自动化'},h('strong',null,'Windows 高级自动化'),
            h('p',{role:'status'},status),
            state?.mode==='bundled'&&h('p',{className:'qx-component-muted'},'完整安装已包含此组件，无需首次下载。'),
            state?.mode==='external'&&h('p',{className:'qx-component-muted'},'使用当前配置的运行环境。'),
            state?.mode==='unavailable'&&h('p',{className:'qx-component-error'},'安装中缺少组件清单，请使用完整安装或联系维护人员修复。'),
            state?.mode==='on-demand'&&h('p',{className:'qx-component-muted'},ready?'此组件已保存在本机，后续使用无需再次下载。':'首次使用需联网下载'+(state.total?'约 '+format(state.total):'组件')+'。可以继续使用其他功能；准备成功后保存在本机。'),
            busy&&h('div',null,h('progress',{max:state.total||100,...(state.phase==='downloading'?{value:state.transferred}:{}),'aria-label':'组件准备进度'}),h('p',{className:'qx-component-muted'},state.phase==='downloading'?format(state.transferred)+' / '+format(state.total):'请稍候，完成后会显示结果。')),
            state?.error&&h('p',{role:'alert',className:'qx-component-error'},state.error),
            restored&&networkFailure&&h('p',{role:'status'},'网络连接已恢复，可以点击重新下载。'),
            ready&&state.attempt>0&&h('p',null,'组件已准备好。如原任务已结束，请重新发起；重试安装不会自动重发任务。'),
            problem&&h('p',{role:'alert',className:'qx-component-error'},problem),
            h('div',{className:'qx-component-actions'},canPrepare&&h('button',{type:'button',disabled:acting||state.phase==='cancelling'||(!busy&&offline&&state.phase!=='cached')||state.code==='CACHE_INVALID',onClick:()=>act(busy?'cancel':'prepare')},primary),
              h('button',{type:'button',disabled:acting,onClick:()=>void refresh.current()},'刷新状态')))));
    };
  }
  const ComponentEntry=createComponentEntry(React);
  function AccountFooter({wide}){
    const [knowledgeOpen,setKnowledgeOpen]=React.useState(false),[knowledgeScope,setKnowledgeScope]=React.useState('');
    const [memoryOpen,setMemoryOpen]=React.useState(false),[memoryCase,setMemoryCase]=React.useState(null);
    const [wechatOpen,setWechatOpen]=React.useState(false);
    React.useEffect(()=>{
      const open=()=>{window.__qxOpenWechatRequested=false;setWechatOpen(true)};
      window.addEventListener('qx-open-wechat',open);
      if(window.__qxOpenWechatRequested)open();
      return()=>window.removeEventListener('qx-open-wechat',open);
    },[]);
    return h('div',{className:'qx-sidebar-account'+(wide?'':' qx-sidebar-account-compact')},
      h(UpdateEntry,{wide}),
      h(ComponentEntry,{wide}),
      h('button',{type:'button',className:'qx-wechat-link',style:{width:'calc(100% - 8px)',border:0,background:'transparent',cursor:'pointer'},'aria-label':'知识库',title:'知识库',onClick:()=>setKnowledgeOpen(true)},h('svg',{width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.6,'aria-hidden':true},h('path',{d:'M4 3h12a2 2 0 0 1 2 2v16H6a2 2 0 0 1-2-2V3zm0 13h14M8 7h6M8 11h6'})),wide&&h('span',null,'知识库')),
      knowledgeOpen&&h(KnowledgeBoundary,{onClose:()=>setKnowledgeOpen(false)},h(KnowledgePanel,{initialProject:knowledgeScope,onScopeChange:setKnowledgeScope,onClose:()=>{setKnowledgeOpen(false);setKnowledgeScope('');},onMemory:chosen=>{setMemoryCase(chosen);setKnowledgeOpen(false);setMemoryOpen(true);}})),
      memoryOpen&&h(MemoryPanel,{initialCase:memoryCase,onClose:()=>{setMemoryOpen(false);setKnowledgeOpen(true);}}),
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
  function LegalSearchRow({toolName,block,phase}){
    const [open,setOpen]=React.useState(false);
    const read=toolName==='legal_search_read',title=read?'读取法律检索资料':'法律资料检索';
    let args={},data=null;
    try{args=JSON.parse(block?.call?.argsRaw??block?.argsRaw??'{}');}catch{}
    try{data=JSON.parse((block?.content??[]).filter(x=>x.type==='text').map(x=>x.text).join(''));}catch{}
    if(!args||typeof args!=='object')args={};
    if(!data||typeof data!=='object')data=null;
    const queries=Array.isArray(args.queries)?args.queries.filter(x=>typeof x==='string'):[];
    const rows=Array.isArray(data?.items)?data.items.filter(x=>x&&typeof x.url==='string'):[];
    const outcomes=Array.isArray(data?.queries)?data.queries.filter(x=>x&&typeof x==='object'):[];
    const settled=Boolean(block&&'kind' in block),status=block?.isError?'调用失败':data?.status==='failed'?'渠道暂不可用':data?.status==='partial'?'已保留部分结果':data?.status==='empty'?'未找到结果':data?.status==='cancelled'?'已取消':settled?'已完成':'检索中';
    const detail=read?(!Number.isInteger(args.entry)?'查看已保存的结果目录':`查看第 ${args.entry+1} 条资料`):queries.join('；');
    return h('div',{className:'qx-legal-search-row','data-tool':toolName,'data-state':status},
      h('button',{type:'button',className:'qx-legal-search-toggle','aria-expanded':open,onClick:()=>setOpen(x=>!x)},
        h('span',{'aria-hidden':true},open?'▾':'▸'),h('span',null,title),h('span',{className:'qx-legal-search-detail'},phase==='preparing'?'准备检索':detail),h('span',null,status)),
      open&&h('div',{className:'qx-legal-search-body'},
        Number.isFinite(data?.total)&&h('p',null,`已保存 ${data.total} 条来源；当前显示 ${rows.length} 条。`),
        outcomes.map((q,i)=>h('p',{key:i},`${q.provider==='so360'?'360 备用检索':'现有检索'}：${q.status==='success'?'已找到来源':q.status==='empty'?'未找到结果':'暂未取得结果'}${Array.isArray(q.attempts)&&q.attempts.some(a=>['CAPTCHA','COOLDOWN'].includes(a?.code))?'（备用渠道要求验证，已暂停重试）':''}`)),
        rows.length>0&&h('ol',null,rows.map((item,i)=>h('li',{key:i},/^https?:\/\//i.test(item.url)?h('a',{href:item.url,target:'_blank',rel:'noopener noreferrer'},typeof item.title==='string'?item.title:item.url):h('span',null,'来源链接不可用'),typeof item.snippet==='string'&&h('p',null,item.snippet)))),
        typeof data?.text==='string'&&h('p',{style:{whiteSpace:'pre-wrap'}},data.text),
        typeof data?.note==='string'&&h('p',null,data.note),
        !data&&h('p',null,settled?'未取得可展示结果，可在调用轨迹中查看详情。':'正在检索，已返回的资料会保存在本机。')));
  }
  function installReconnect(ctx){
    const connection=ctx.get('connection');if(!connection)return()=>{};
    let pending,cancel;
    const reconnect=()=>pending??=(new Promise(resolve=>{
      const previous=connection.generation.getSnapshot()?.id;
      let done=false,stopState=()=>{},stopGeneration=()=>{},timer;
      const finish=value=>{if(done)return;done=true;clearTimeout(timer);stopState();stopGeneration();resolve(value);};
      cancel=()=>finish(false);
      const check=()=>{const generation=connection.generation.getSnapshot();if(connection.state.getSnapshot()==='connected'&&generation&&generation.id!==previous)finish(true);};
      stopState=connection.state.subscribe(check);stopGeneration=connection.generation.subscribe(check);
      timer=setTimeout(()=>finish(false),15000);
      try{connection.reconnect();check();}catch{finish(false);}
    })).finally(()=>{pending=null;cancel=null;});
    window.__qxReconnectInPlace=reconnect;
    return()=>{cancel?.();if(window.__qxReconnectInPlace===reconnect)delete window.__qxReconnectInPlace;};
  }
  return {inject:['sessions','uiWorkspace','slots','sidebarRight'],apply(ctx){
    ctx.effect(()=>{
      let dispose,stopped=false;const script=document.createElement('script');script.src='/api/qx-compare/client.js';
      script.onload=()=>{if(!stopped)dispose=window.qxInstallContractComparison(ctx,React);};
      script.onerror=()=>console.warn('合同对比暂未加载，请刷新工作台后重试。');
      document.head.append(script);return()=>{stopped=true;dispose?.();script.remove();};
    },'qunxing: contract comparison');
    ctx.effect(()=>installReconnect(ctx),'qunxing: reconnect in place');
    ctx.effect(()=>{
      const css=document.createElement('style');css.textContent='.qx-legal-search-row{margin:6px 0;color:var(--dsw-alias-label-secondary,#687282);font-size:13px}.qx-legal-search-toggle{display:flex;align-items:center;gap:8px;width:100%;border:0;padding:6px 0;background:transparent;color:inherit;text-align:left;cursor:pointer;font:inherit}.qx-legal-search-toggle:focus-visible{outline:2px solid #3563a5;outline-offset:2px}.qx-legal-search-detail{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}.qx-legal-search-body{padding:4px 16px 8px;border-left:1px solid var(--dsw-alias-border-default,#d8dde5);overflow-wrap:anywhere}.qx-legal-search-body p{margin:6px 0}.qx-legal-search-body a{color:var(--dsw-alias-link,#3563a5)}';document.head.append(css);return()=>css.remove();
    },'qunxing: legal search cards');
    for(const key of ['legal_search','legal_search_read'])ctx.slots.inject('tool.call.toolview',()=>ctx.slots.register({name:'tool.call.toolview',key},LegalSearchRow));
    ctx.effect(()=>{
      let notice,timer;
      const pending=new Map(),controller=new AbortController();
      const preview={open(sessionId,file){
        if(typeof sessionId!=='string'||!sessionId)return Promise.resolve(false);
        const key=JSON.stringify([sessionId,file]);if(pending.has(key))return pending.get(key);
        const operation=(async()=>{
          try{
            const response=await fetch('/api/qx-preview/attachment-path',{method:'POST',credentials:'same-origin',
              headers:{'content-type':'application/json'},body:JSON.stringify(file),signal:controller.signal});
            if(!response.ok)throw Error('Preview unavailable');
            const result=await response.json();if(typeof result.path!=='string'||!result.path)throw Error('Preview unavailable');
            if(controller.signal.aborted)return false;
            const address='dsh-resource://file/session/'+encodeURIComponent(sessionId)+'/'+result.path.replace(/\\/g,'/').split('/').map(encodeURIComponent).join('/');
            ctx.sidebarRight.openResource(address);return true;
          }catch(error){
            if(error.name==='AbortError')return false;
            if(!notice){notice=document.createElement('div');notice.setAttribute('role','alert');
              Object.assign(notice.style,{position:'fixed',bottom:'24px',left:'50%',transform:'translateX(-50%)',maxWidth:'calc(100vw - 48px)',
                padding:'12px 16px',borderRadius:'8px',background:'#26334a',color:'#fff',font:'14px/1.6 system-ui',zIndex:'10000'});document.body.append(notice);}
            notice.textContent='附件预览未能打开，请确认上传已完成后重试。';
            clearTimeout(timer);timer=setTimeout(()=>{notice?.remove();notice=null},8000);return false;
          }finally{pending.delete(key)}
        })();pending.set(key,operation);return operation;
      }};
      const dispose=ctx.reflect.provide('qxUploadedPreview',preview);
      return()=>{controller.abort();dispose();clearTimeout(timer);notice?.remove();};
    },'qunxing: uploaded file preview');
    ctx.effect(()=>{
      const script=document.createElement('script');script.src='/api/qx-privacy/client.js';script.async=true;
      script.onerror=()=>console.warn('群兴：上传脱敏组件暂未加载，可刷新工作台重试；当前上传保持原流程。');
      document.head.append(script);
      return()=>{window.qxPrivacy?.dispose();script.remove();};
    },'qunxing: optional upload privacy');
    ctx.effect(()=>{
      let dispose,stopped=false;const script=document.createElement('script');script.src='/api/qx-content-watch/client.js';
      script.onload=()=>{if(!stopped&&typeof window.qxInstallContentWatch==='function')dispose=window.qxInstallContentWatch(ctx,React);};
      script.onerror=()=>console.warn('拓客内容暂未加载，请刷新工作台后重试。');
      document.head.append(script);
      return()=>{stopped=true;dispose?.();script.remove();};
    },'qunxing: content watch');
    ctx.effect(()=>{const style=document.createElement('style');style.dataset.qxChrome='true';style.textContent=styles;document.head.append(style);return()=>style.remove();},'qunxing: concise desktop chrome');
    ctx.slots.inject('sidebar.brand.mark',()=>ctx.slots.register({name:'sidebar.brand.mark',priority:-100},()=>h('span',{className:'qx-brand-compact'},h('img',{className:'qx-brand-logo',src:'/api/qx-brand/logo.png?v=20261103',alt:'群兴律师事务所标识',draggable:false}))));
    ctx.slots.inject('sidebar.brand.name',()=>ctx.slots.register({name:'sidebar.brand.name',priority:-100},()=>h('span',{className:'qx-wordmark'},'AI师兄法律助手平台')));
    ctx.slots.inject('conversation.hero.brand.mark',()=>ctx.slots.register({name:'conversation.hero.brand.mark',priority:-100},()=>null));
    ctx.effect(()=>{
      let dispose,stopped=false;const script=document.createElement('script');script.src='/api/qx-business/client.js';
      script.onload=()=>{if(!stopped)dispose=window.qxInstallBusiness(ctx,React);};
      script.onerror=()=>console.warn('业务引导暂未加载，请刷新工作台后重试。');
      document.head.append(script);
      return()=>{stopped=true;dispose?.();script.remove();};
    },'qunxing: guided business conversations');
    ctx.effect(()=>{
      let dispose,stopped=false;const script=document.createElement('script');script.src='/api/qx-layered/client.js';
      script.onload=()=>{if(!stopped)dispose=window.qxInstallKnowledge(ctx,React);};
      script.onerror=()=>console.warn('知识关系图暂未加载，请刷新工作台后重试。');
      document.head.append(script);return()=>{stopped=true;dispose?.();script.remove();};
    },'qunxing: layered knowledge');
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
