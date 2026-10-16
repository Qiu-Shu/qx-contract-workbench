'use strict';
// Each reception has a full-page, fixed scope. No browser storage holds case text.
(() => {
  const byId = id => document.getElementById(id);
  const scope = document.body.dataset.intake;
  const base = scope ? '/api/intakes/' + encodeURIComponent(scope) : '';
  const states = {open:'待跟进', waiting:'等待补充', closed:'已结束', converted:'已转合同'};
  const errors = {AUTHORIZATION_REQUIRED:'登录已失效。请在另一个窗口重新登录，再核对本页记录。',
    CROSS_MATTER_DENIED:'当前账户无权操作这条记录。请返回工作区核对账户与权限。',
    VERSION_CONFLICT:'版本或状态已变化。请先保留未保存文字，再刷新核对；本次没有覆盖已有记录。',
    STATE_CONFLICT:'请检查必填项、长度和当前状态后重试。',
    DATA_POLICY_UNAPPROVED:'当前入口不支持所选材料用途，请核对后重试。',
    FILE_LIMIT:'文字过长，请缩短后重试。'};
  let saved = null, dirty = false, busy = false, historyRequest = 0;
  function element(tag, text, cls) {const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(cls)node.className=cls; return node;}
  function link(text,url) {const node=element('a',text);node.href=url;return node;}
  function tell(text,error=false) {byId('message').textContent=text;byId('message').classList.toggle('error',error);}
  async function request(url, method='GET', data, blob=false) {
    const csrf=document.cookie.split('; ').find(v=>v.startsWith('qx_csrf='))?.slice(8)||'';
    let result;
    try {result=await fetch(url,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});}
    catch {throw new Error('连接中断，操作结果尚未确认。请保留文字并核对已保存记录，不要连续提交。');}
    if(!result.ok) {const error=await result.json().catch(()=>({}));throw new Error(errors[error.code]||'操作未完成，请保留文字并刷新核对。');}
    return blob ? result.blob() : result.json();
  }
  function on(id,event,handler) {byId(id)?.addEventListener(event,async e=>{e.preventDefault();try{await handler(e);}catch(error){tell(error.message,true);}});}
  async function transaction(action) {
    if(busy)return;
    busy=true;controls();
    try {return await action();} finally {busy=false;controls();}
  }
  function controls() {
    if(!scope)return;
    const editable=!!saved&&!saved.matter_id&&!busy;
    byId('draft-fields').disabled=!editable;
    byId('save-intake').disabled=!editable||!dirty;
    byId('convert-fields').disabled=!editable||dirty;
    for(const id of ['copy-client','copy-internal','export-client','export-internal'])byId(id).disabled=!saved||dirty||busy;
    byId('export-client').disabled ||= !byId('client-checked').checked;
    byId('save-state').textContent=busy?'正在保存或处理，请稍候…':!saved?'尚未载入':dirty?'有未保存修改，导出和转案暂不可用':'第 '+saved.revision+' 版已保存';
  }
  function markDirty() {dirty=true;byId('client-checked').checked=false;controls();}
  window.addEventListener('beforeunload',e=>{if(dirty||busy){e.preventDefault();e.returnValue='';}});
  on('workspace-logout','click',async()=>{if(dirty&&!window.confirm('存在未保存文字。仍要退出登录吗？'))return;await request('/api/logout','POST');dirty=false;location.assign('/login');});
  request('/api/session').then(value=>{byId('account-name').textContent=value.username;}).catch(error=>tell(error.message,true));

  if(!scope) {
    let items=[],next=0;const createId=crypto.randomUUID();
    function renderList() {
      const filter=byId('intake-filter').value,host=byId('intake-list');host.replaceChildren();
      const visible=items.filter(v=>filter==='all'||(filter==='active'?['open','waiting'].includes(v.status):filter==='materials'?v.materials_needed>0&&['open','waiting'].includes(v.status):v.status===filter));
      for(const record of visible) {
        const row=element('div',undefined,'record-row'),info=element('div');
        info.append(link(record.title,'/intakes/'+encodeURIComponent(record.id)));
        const time=record.follow_up_at?new Date(record.follow_up_at).toLocaleString('zh-CN'):'未安排跟进时间';
        info.append(element('p',time+' · 待补材料 '+record.materials_needed+' 项','muted'));
        row.append(info,element('span',states[record.status],'state'));host.append(row);
      }
      if(!visible.length)host.append(element('p',items.length?'当前已加载记录中没有匹配项，可切换显示范围或加载更多。':'还没有接待记录。点击“新增接待”，保留咨询原话并安排下一步。','muted'));
      byId('list-scope').textContent='已加载 '+items.length+' 条，按登记时间排序；筛选作用于已加载记录。';
      byId('load-more').hidden=next===null;
    }
    async function load() {const data=await request('/api/intakes?offset='+next);items.push(...data.items);next=data.next_offset;renderList();}
    on('intake-filter','change',renderList);
    on('load-more','click',async()=>{byId('load-more').disabled=true;try{await load();}finally{byId('load-more').disabled=false;}});
    on('open-create','click',()=>{byId('new-intake').open=true;byId('new-intake').scrollIntoView({block:'start'});byId('create-intake').elements.title.focus();});
    on('create-intake','submit',async e=>{
      const form=e.currentTarget,button=form.querySelector('button');button.disabled=true;
      try {const f=new FormData(form);const result=await request('/api/intakes','POST',{request_id:createId,draft:{title:f.get('title'),contact:f.get('contact'),consultation:f.get('consultation')}});location.assign('/intakes/'+encodeURIComponent(result.id));}
      finally{button.disabled=false;}
    });
    load().catch(error=>tell(error.message,true));
    request('/api/matters').then(matters=>{const host=byId('recent-matters');host.replaceChildren();for(const m of matters){const row=element('div',undefined,'record-row');row.append(link(m.title,'/matters/'+encodeURIComponent(m.id)));host.append(row);}if(!matters.length)host.append(element('p','尚无合同案件。可从接待转案，或在合同工作台新建。','muted'));}).catch(error=>tell(error.message,true));
    request('/api/workspace/tasks').then(tasks=>{const host=byId('running-tasks');host.replaceChildren();for(const t of tasks){const row=element('div',undefined,'record-row');row.append(link(t.title,'/matters/'+encodeURIComponent(t.matter_id)),element('span',t.stage,'state'));host.append(row);}if(!tasks.length)host.append(element('p','当前没有正在执行的任务。','muted'));}).catch(error=>tell(error.message,true));
    return;
  }

  const form=byId('intake-form');
  function materialRow(value={name:'',state:'needed'}) {
    if(byId('materials').children.length>=30){tell('材料清单最多30项。',true);return;}
    const row=element('div',undefined,'material-row');
    const name=element('input');name.value=value.name;name.required=true;name.maxLength=300;name.setAttribute('aria-label','材料名称');
    const state=element('select');state.setAttribute('aria-label','材料状态');
    for(const [key,text] of [['needed','待补'],['received','已收到待核'],['checked','已核对']]){const option=element('option',text);option.value=key;state.append(option);}state.value=value.state;
    const remove=element('button','移除','secondary');remove.type='button';remove.setAttribute('aria-label','移除这项材料');remove.addEventListener('click',()=>{row.remove();markDirty();});
    row.append(name,state,remove);byId('materials').append(row);
  }
  function localDate(iso) {if(!iso)return '';const date=new Date(iso);return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);}
  function showSource(record) {
    byId('history-state').textContent='第 '+record.revision+' 版 · '+new Date(record.saved_at).toLocaleString('zh-CN')+' · 待核验';
    byId('source-text').textContent=record.consultation||'本版尚未登记咨询原话。';
    const materials=record.materials.map(m=>m.name+'（'+{needed:'待补',received:'已收到待核',checked:'已核对'}[m.state]+'）').join('\n');
    byId('history-content').textContent='咨询主题：'+record.title+'\n联系备注：'+(record.contact||'尚未填写')+
      '\n本版接待状态：'+states[record.status]+'\n\n追问：\n'+(record.questions.join('\n')||'尚未填写')+
      '\n\n材料清单：\n'+(materials||'尚未填写')+'\n\n跟进时间：'+(record.follow_up_at?new Date(record.follow_up_at).toLocaleString('zh-CN'):'尚未安排')+
      '\n跟进说明：'+(record.follow_up_note||'尚未填写')+'\n\n客户回复：\n'+record.client_reply+'\n\n律师内部意见：\n'+record.internal_notes;
  }
  function populate(record) {
    saved=record;dirty=false;historyRequest++;
    for(const name of ['title','contact','consultation','follow_up_note','status','client_reply','internal_notes'])form.elements[name].value=record[name];
    form.elements.questions.value=record.questions.join('\n');form.elements.follow_up_at.value=localDate(record.follow_up_at);
    byId('materials').replaceChildren();record.materials.forEach(materialRow);
    byId('record-title').textContent=record.title;
    byId('record-state').textContent='第 '+record.revision+' 版 · '+(record.matter_id?'已转合同':states[record.status])+' · 来源与法律依据待核';
    byId('history-revision').value=record.revision;byId('history-revision').max=record.revision;
    byId('client-checked').checked=false;showSource(record);
    byId('convert-form').elements.title.value=record.title;
    byId('convert-panel').hidden=!!record.matter_id;
    const notice=byId('converted-notice');notice.hidden=!record.matter_id;notice.replaceChildren();
    if(record.matter_id)notice.append(document.createTextNode('这条接待已转为合同案件，接待版本保留只读。'),link('打开合同案件','/matters/'+encodeURIComponent(record.matter_id)));
    controls();
  }
  function draft() {
    const f=new FormData(form),value={};
    for(const name of ['title','contact','consultation','follow_up_note','status','client_reply','internal_notes'])value[name]=f.get(name);
    value.questions=f.get('questions').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    value.materials=[...byId('materials').children].map(row=>({name:row.querySelector('input').value,state:row.querySelector('select').value}));
    value.follow_up_at=f.get('follow_up_at')?new Date(f.get('follow_up_at')).toISOString():null;
    return value;
  }
  form.addEventListener('input',markDirty);form.addEventListener('change',markDirty);
  on('add-material','click',()=>{materialRow();markDirty();});
  on('intake-form','submit',async()=>{const value=draft();await transaction(async()=>{const record=await request(base,'PUT',{expected_revision:saved.revision,draft:value});populate(record);tell('这一版已保存，历史原话和旧版记录保留。');});});
  on('client-checked','change',controls);
  async function current() {if(!saved||dirty)throw new Error('请先保存当前修改。');const record=await request(base);if(record.revision!==saved.revision)throw new Error(errors.VERSION_CONFLICT);return record;}
  for(const audience of ['client','internal']) {
    on('copy-'+audience,'click',()=>transaction(async()=>{const record=await current();const text=audience==='client'?record.client_reply:record.internal_notes;if(!text.trim())throw new Error('这一栏尚未填写。');try{await navigator.clipboard.writeText(text);}catch{throw new Error('复制未成功，请选中对应栏文字后手动复制。');}tell(audience==='client'?'已复制客户回复；不含内部意见。':'已复制律师内部意见。');}));
    on('export-'+audience,'click',()=>transaction(async()=>{await current();const blob=await request(base+'/export','POST',{revision:saved.revision,audience,text_checked:audience==='internal'||byId('client-checked').checked},true);const url=URL.createObjectURL(blob),anchor=link('',url);anchor.download=(audience==='client'?'客户回复':'内部接待')+'-v'+saved.revision+'.docx';document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);tell('已生成第 '+saved.revision+' 版'+(audience==='client'?'客户回复':'内部接待')+' Word，请核对下载结果。');}));
  }
  on('history-form','submit',async()=>{const sequence=++historyRequest;const version=Number(byId('history-revision').value);const record=await request(base+'/revisions/'+version);if(sequence===historyRequest)showSource(record);});
  on('reading-size','change',()=>{document.body.classList.toggle('read-large',byId('reading-size').value==='large');document.body.classList.toggle('read-largest',byId('reading-size').value==='largest');});
  on('toggle-source','click',()=>{const panel=byId('source-panel');panel.hidden=!panel.hidden;byId('toggle-source').textContent=panel.hidden?'展开原话与版本':'收起原话与版本';byId('toggle-source').setAttribute('aria-expanded',String(!panel.hidden));});
  const positions={sales:[['buyer','买方'],['seller','卖方']],service:[['customer','委托方'],['provider','服务方']],lease:[['lessee','承租方'],['lessor','出租方']],nda:[['recipient','接收方'],['discloser','披露方']]};
  function setPositions() {const select=byId('convert-position');select.replaceChildren();for(const [key,label] of positions[byId('convert-form').elements.contract_type.value]){const option=element('option',label);option.value=key;select.append(option);}}
  byId('convert-form').elements.contract_type.addEventListener('change',setPositions);setPositions();
  on('convert-form','submit',async()=>{const f=new FormData(byId('convert-form'));const matter={};for(const name of ['title','contract_type','position','review_mode','material_mode'])matter[name]=f.get(name);matter.objectives=[f.get('objective')];await transaction(async()=>{await current();const result=await request(base+'/convert','POST',{expected_revision:saved.revision,matter});dirty=false;busy=false;location.assign('/matters/'+encodeURIComponent(result.matter_id));});});
  request(base).then(populate).catch(error=>tell(error.message,true));
})();
