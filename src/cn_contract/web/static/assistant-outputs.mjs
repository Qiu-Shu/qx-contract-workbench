// Copy and download only a server projection of an exact saved source and audience.
const sourceKey=source=>JSON.stringify([source?.kind,source?.output_id || null,source?.profile_revision || null]);
const binding=state=>JSON.stringify([state.id,state.view?.scope?.workspace_id,state.view?.scope?.scope_kind,
  state.view?.scope?.scope_ref,state.view?.scope?.binding_revision]);
const invalid=()=>Object.assign(new Error('output projection'),{code:'VERSION_CONFLICT',status:409});

function browserDownload(blob,name) {
  const url=URL.createObjectURL(blob),link=globalThis.document.createElement('a');
  link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function copyNow(text,isActive,document=globalThis.document) {
  // The copy event and payload assignment happen in the same JS task. There is
  // no pending browser permission Promise that can copy after a case switch.
  let copied=false;
  const listener=event=>{
    if(!isActive() || !event.clipboardData)return;
    event.clipboardData.setData('text/plain',text);event.preventDefault();copied=true;
  };
  document.addEventListener('copy',listener);
  try {if(!document.execCommand('copy') || !copied)throw new Error('clipboard unavailable');}
  finally {document.removeEventListener('copy',listener);}
}

export function bindOutputs({controller,api,document=globalThis.document,readonly=false,onOpen=()=>{},
    saveBlob=browserDownload}) {
  const byId=id=>document.getElementById(id);
  let epoch=0,key=null,busy=false,disposed=false,items=[],next=null,projection=null;
  const panel=byId('output-panel'),source=byId('output-source'),audience=byId('output-audience');
  const notice=text=>{byId('output-notice').textContent=text;};
  const selected=()=>{
    const item=source.value===''?null:items[Number(source.value)];
    return item?.audiences.includes(audience.value)?{source:item.source,audience:audience.value}:null;
  };
  const available=()=>!disposed && !readonly && controller.state.id && controller.state.view && controller.state.status!=='revoked';
  function controls() {
    byId('show-outputs').disabled=!available() || controller.state.loading;
    source.disabled=busy || !items.length;
    audience.disabled=busy || source.value==='';
    byId('output-refresh').disabled=busy || !available();
    byId('output-more').hidden=!next;byId('output-more').disabled=busy;
    byId('output-preview').disabled=busy || !selected() || !available();
    for(const id of ['output-copy','output-download'])byId(id).disabled=busy || !projection || !available();
  }
  function clearPreview() {
    projection=null;
    for(const id of ['output-text','output-meta','output-notes','output-citations'])byId(id).textContent='';
    byId('output-result').hidden=true;
  }
  function close(focus=false) {
    ++epoch;busy=false;clearPreview();items=[];next=null;source.replaceChildren();source.value='';audience.replaceChildren();audience.value='';
    panel.hidden=true;notice('');byId('show-outputs').setAttribute('aria-expanded','false');
    document.body.classList.remove('source-open');controls();
    if(focus)byId('show-outputs').focus();
  }
  function chooseAudience() {
    ++epoch;busy=false;clearPreview();notice('');
    const item=source.value===''?null:items[Number(source.value)];
    audience.replaceChildren();
    for(const value of item?.audiences || []) {
      const option=document.createElement('option');option.value=value;option.textContent=value==='client'?'客户版 · 仅客户回复':'内部版 · 律师工作稿';audience.append(option);
    }
    audience.value=item?.audiences[0] || '';
    controls();
  }
  function checked(value,choice,cid) {
    if(!value || value.conversation_id!==cid || value.selection?.audience!==choice.audience ||
        sourceKey(value.selection?.source)!==sourceKey(choice.source) || !/^[a-f0-9]{64}$/.test(value.content_sha256) ||
        typeof value.id!=='string' || typeof value.text!=='string' || !value.text.trim() ||
        typeof value.title!=='string' || typeof value.source_label!=='string' || value.review_status!=='unverified' ||
        !Array.isArray(value.notes) || !value.notes.every(x=>typeof x==='string') ||
        !Array.isArray(value.citations) || !value.citations.every(x=>typeof x==='string'))throw invalid();
    return value;
  }
  function show(value) {
    projection=value;
    byId('output-meta').textContent=value.title+' · '+value.source_label;
    byId('output-text').textContent=value.text;
    byId('output-notes').textContent=value.notes.join('\n');
    byId('output-citations').textContent=value.citations.join('\n');
    byId('output-result').hidden=false;
  }
  const active=(token,cid)=>token===epoch && available() && !panel.hidden && cid===controller.state.id && binding(controller.state)===key;
  function failure(error) {
    clearPreview();
    if(controller.revoke(error))return;
    notice(error.code==='VERSION_CONFLICT'?'所选版本不可用或内容已变化。请重新读取；客户版需要档案中单独保存的客户回复。':
      error.code==='BLOCKED_LIVE'?'当前副本不能创建新的导出。':
      '读取或导出未完成，请重新核对。不会因此重新调用模型。');
  }
  async function refresh(more=false) {
    if(!available() || busy || panel.hidden)return;
    const token=++epoch,cid=controller.state.id,cursor=more?next:null;
    busy=true;clearPreview();notice('正在读取已保存成果…');controls();
    try {
      const value=await api.listOutputs(cid,cursor);
      if(!active(token,cid))return;
      if(value?.conversation_id!==cid || !Array.isArray(value.items) || value.items.some(item=>
        !['model','profile'].includes(item.source?.kind) || !Array.isArray(item.audiences) ||
        !item.audiences.length || item.audiences.some(a=>!['client','internal'].includes(a)) ||
        (item.source.kind==='model' && item.audiences.some(a=>a!=='internal'))))throw invalid();
      items=more?[...items,...value.items]:value.items;next=value.next_before;
      source.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent='请选择已保存成果';source.append(empty);
      items.forEach((item,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=item.label;source.append(option);});
      source.value='';audience.replaceChildren();audience.value='';
      notice(items.length?'客户版只包含档案中单独保存的客户回复。请选定成果和受众后预览。':'尚无可导出成果。请先保存回答，或在档案草稿中填写客户回复。');
    }catch(error){if(active(token,cid))failure(error);}
    finally{if(token===epoch){busy=false;controls();}}
  }
  async function open() {
    if(!available())return;
    close();onOpen();panel.hidden=false;document.body.classList.add('source-open');
    byId('show-outputs').setAttribute('aria-expanded','true');await refresh();
    if(!panel.hidden)source.focus();
  }
  async function preview() {
    const choice=selected();if(!choice || busy || !available() || panel.hidden)return;
    const token=++epoch,cid=controller.state.id;busy=true;clearPreview();notice('正在核对保存版本与受众…');controls();
    try {
      const value=await api.previewOutput(cid,choice);
      if(!active(token,cid))return;
      show(checked(value,choice,cid));notice('请核对下方正文，再复制或导出 Word。');
    }catch(error){if(active(token,cid))failure(error);}
    finally{if(token===epoch){busy=false;controls();}}
  }
  async function perform(kind) {
    if(!projection || busy || !available() || panel.hidden)return;
    const saved=projection,choice=selected();if(!choice)return;
    const token=++epoch,cid=controller.state.id;busy=true;notice('正在重新核对权限与预览版本…');controls();
    const body={...choice,expected_content_sha256:saved.content_sha256};
    try {
      if(kind==='copy') {
        const value=await api.copyOutput(cid,body);
        if(!active(token,cid))return;
        checked(value,choice,cid);
        if(value.id!==saved.id || value.content_sha256!==saved.content_sha256 || value.text!==saved.text)throw invalid();
        const text=[value.title,value.source_label,...value.notes,value.text,...value.citations].join('\n\n');
        try {copyNow(text,()=>active(token,cid),document);}
        catch {if(active(token,cid))notice('浏览器未允许复制，请在下方预览中手动选择文字复制。');return;}
        if(active(token,cid))notice('已复制所选版本。发送给客户前请再次核对。');
      } else {
        const blob=await api.downloadOutput(cid,body);
        if(!active(token,cid))return;
        saveBlob(blob,saved.title+'-'+saved.content_sha256.slice(0,8)+'.docx');notice('Word 文件已交给浏览器下载。');
      }
    }catch(error){if(active(token,cid))failure(error);}
    finally{if(token===epoch){busy=false;controls();}}
  }
  byId('show-outputs').addEventListener('click',open);
  byId('close-outputs').addEventListener('click',()=>close(true));
  byId('output-refresh').addEventListener('click',()=>refresh());
  byId('output-more').addEventListener('click',()=>refresh(true));
  source.addEventListener('change',chooseAudience);
  audience.addEventListener('change',()=>{++epoch;busy=false;clearPreview();notice('');controls();});
  byId('output-preview').addEventListener('click',preview);
  byId('output-copy').addEventListener('click',()=>perform('copy'));
  byId('output-download').addEventListener('click',()=>perform('docx'));
  return {open,close,refresh,preview,copy:()=>perform('copy'),download:()=>perform('docx'),
    state(state){const nextKey=binding(state);if(nextKey!==key || state.status==='revoked' || readonly){key=nextKey;close();}controls();},
    dispose(){disposed=true;close();}};
}
