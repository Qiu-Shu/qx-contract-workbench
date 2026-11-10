// Reference text stays data; a preview never calls a model or sends a client message.
const byId=id=>document.getElementById(id);
const identifier=document.body.dataset.intake;
const base='/api/intakes/'+encodeURIComponent(identifier)+'/assistant';
const selected=new Map();
let record=null,dirty=false,working=false,preview=null,chatRequest=null,sourcePage=null,readEpoch=0;
const errors={AUTHORIZATION_REQUIRED:'登录已失效，请重新登录。',CROSS_MATTER_DENIED:'当前账户无权读取这条接待或资料。',
  VERSION_CONFLICT:'接待或资料版本已变化，请核对后重新整理。',DATA_POLICY_UNAPPROVED:'资料完整性核对未通过，请联系维护者。',
  FILE_LIMIT:'内容超过当前上限，请减少所选资料。',STATE_CONFLICT:'请检查输入和当前状态。',NOT_SUPPORTED:'当前资料不可用。',BLOCKED_LIVE:'当前副本只读，不能进行此操作。'};
const node=(tag,text)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=text;return item;};
function status(text){byId('reception-status').textContent=text;}
async function request(url,method='GET',data){
  const csrf=document.cookie.split('; ').find(v=>v.startsWith('qx_csrf='))?.slice(8)||'';
  let result;
  try{result=await fetch(url,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});}
  catch{throw new Error('连接中断，结果尚未确认。请保留文字，并核对已保存记录后重试。');}
  if(!result.ok){const error=await result.json().catch(()=>({}));throw new Error(errors[error.code]||'操作尚未完成，请刷新核对。');}
  return result.json();
}
function controls(){
  const disabled=!record||dirty||working||Boolean(record.matter_id);
  byId('reception-preview').disabled=disabled;
  byId('reception-conversation').disabled=disabled;
  byId('reception-apply').disabled=disabled||!preview;
  byId('reception-preview-box').hidden=!preview;
  byId('reception-mode').disabled=working;
  for(const control of document.querySelectorAll('#reception-selected button,#reception-sources button,#reception-passages input,#reception-search input,#reception-search button,#reception-more'))control.disabled=working;
}
function invalidate(){preview=null;chatRequest=null;byId('reception-open-chat').hidden=true;controls();}
document.addEventListener('qx:intake-state',event=>{
  const value=event.detail;
  if(value.dirty||record?.revision!==value.record?.revision)invalidate();
  record=value.record;dirty=value.dirty||value.busy;controls();
});
function body(){return {expected_revision:record.revision,mode:byId('reception-mode').value,
  references:[...selected.values()].map(({source_id,paragraph,quote_sha256})=>({source_id,paragraph,quote_sha256}))};}
function selections(){
  const host=byId('reception-selected');host.replaceChildren();
  byId('reception-selection').textContent=selected.size?`已选 ${selected.size}/4 条参考片段；来源只写入内部稿。`:'本次未选参考片段；最多选择4条。';
  for(const [key,value] of selected){const remove=node('button',value.title+' · 片段'+value.paragraph+' ×');remove.type='button';remove.className='secondary';remove.addEventListener('click',()=>{selected.delete(key);invalidate();selections();for(const box of byId('reception-passages').querySelectorAll('input'))if(box.dataset.key===key)box.checked=false;});host.append(remove);}
  controls();
}
function renderPassages(items,append=false){
  const host=byId('reception-passages');if(!append)host.replaceChildren();
  if(!items.length&&!append)host.append(node('p','没有匹配片段。可换一个关键词，或直接打开上方原件目录。'));
  for(const item of items){
    const article=node('article'),label=node('label'),box=node('input'),key=item.source_id+':'+item.paragraph;
    box.type='checkbox';box.checked=selected.has(key);box.dataset.key=key;
    label.append(box,node('span',item.title+' · 片段'+item.paragraph+' · 待核实'));
    box.addEventListener('change',()=>{if(box.checked){if(selected.size>=4){box.checked=false;status('本次最多选择4条，请先移除一条。');return;}selected.set(key,item);}else selected.delete(key);invalidate();selections();});
    const text=node('div',item.text);text.className='reading-text';article.append(label,text);host.append(article);
  }
  controls();
}
async function readSource(id,start=0,append=false){
  const epoch=++readEpoch;
  const page=await request('/api/reception/knowledge/sources/'+encodeURIComponent(id)+'?start='+start);
  if(epoch!==readEpoch)return;
  sourcePage=page.next_start===null?null:{id,start:page.next_start};
  renderPassages(page.items,append);byId('reception-more').hidden=!sourcePage;
}
function on(id,event,action){byId(id).addEventListener(event,async e=>{e.preventDefault();try{await action(e);}catch(error){status(error.message);}});}
on('reception-search','submit',async()=>{
  const epoch=++readEpoch;
  const result=await request('/api/reception/knowledge/search?q='+encodeURIComponent(byId('reception-query').value));
  if(epoch!==readEpoch)return;
  sourcePage=null;byId('reception-more').hidden=true;renderPassages(result.items);
});
on('reception-more','click',async()=>{if(sourcePage)await readSource(sourcePage.id,sourcePage.start,true);});
on('reception-mode','change',invalidate);
async function transaction(action){if(working||dirty||!record||record.matter_id)return;working=true;controls();try{await action();}finally{working=false;controls();}}
on('reception-preview','click',()=>transaction(async()=>{
  const revision=record.revision;
  const result=await request(base+'/preview','POST',body());
  if(dirty||record.revision!==revision)return;
  preview=result;byId('reception-client').textContent=result.client_reply;byId('reception-internal').textContent=result.internal_notes;
  status('已按保存版本整理工作稿；未调用模型，尚未更改接待记录。');
}));
on('reception-apply','click',()=>{if(!preview||dirty||working)return;const packet=preview;document.dispatchEvent(new CustomEvent('qx:reception-apply',{detail:packet}));});
on('reception-conversation','click',()=>transaction(async()=>{
  const input=body();
  if(!chatRequest)chatRequest={...input,request_id:crypto.randomUUID()};
  const view=await request(base+'/conversation','POST',chatRequest);
  const link=byId('reception-open-chat');link.href='/assistant/'+encodeURIComponent(view.scope.conversation_id);link.hidden=false;
  status('任务已保存为独立对话草稿，尚未发送给模型。请打开草稿核对内容与生成条件。');
}));
request('/api/intakes/'+encodeURIComponent(identifier)).then(value=>{if(!record){record=value;controls();}}).catch(error=>status(error.message));
request('/api/reception/knowledge').then(catalog=>{
  byId('reception-knowledge-state').textContent=catalog.state==='ready'
    ?`已导入 ${catalog.original_documents} 份原件，去重后 ${catalog.sources.length} 份。仅检索正文和表格文字；身份、经历及案例待核实。`
    :'尚未导入律师资料。可先使用接待模板；本次不会声称已查阅知识库。';
  const host=byId('reception-sources');
  for(const source of catalog.sources){const button=node('button',source.title);button.type='button';button.className='secondary';button.addEventListener('click',()=>readSource(source.id).catch(error=>status(error.message)));host.append(button);}
}).catch(error=>{byId('reception-knowledge-state').textContent=error.message;});
controls();
