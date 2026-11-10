const $=id=>document.getElementById(id);
const state={tab:'topics',profile:null,project:null,source:null,event:null,rows:{},status:null,epoch:0};
const labels={queued:'等待处理',running:'处理中',cancel_requested:'已请求取消',cancelled:'已取消',succeeded:'已完成',failed:'失败',outcome_unknown:'结果未知，请核对回执，不要重复发送'};
const jobLabels={source_search:'官方检索',source_fetch:'官方原文读取',source_refresh:'来源刷新',interview:'补充问题',brief:'事实准备',script:'文稿生成',shooting_plan:'拍摄方案',export:'内容包导出'};
const kinds=['profile','memory','source','event','project','brief','script','shooting_plan','review','feedback'];
const notice=(text,error=false)=>{$('notice').textContent=text;$('notice').classList.toggle('error',error);};
function el(tag,text,attrs={}){const node=document.createElement(tag);if(text!=null)node.textContent=text;for(const [k,v]of Object.entries(attrs))node.setAttribute(k,v);return node;}
function button(text,fn,primary=false){const node=el('button',text,{type:'button'});if(primary)node.className='primary';node.onclick=()=>act(node,fn);return node;}
async function act(node,fn){node.disabled=true;try{await fn();}catch(e){notice(e.message,true);}finally{node.disabled=false;}}
async function api(action,args={}){const response=await fetch('/api/qx-media/action',{method:'POST',headers:{'content-type':'application/json','x-qx-media':'1'},body:JSON.stringify({action,args})});const value=await response.json();if(!value.ok)throw Object.assign(Error(value.error||'操作未完成'),{status:response.status});return value.result;}
function field(parent,label,name,value='',tag='input',options){const wrap=el('div');wrap.append(el('label',label,{for:name}));const input=el(tag,null,{id:name,name});
  if(options)for(const [v,t]of options)input.append(el('option',t,{value:v}));input.value=value;wrap.append(input);parent.append(wrap);return input;}
function row(parent,...items){const node=el('div',null,{class:'row'});node.append(...items);parent.append(node);return node;}
function selected(kind){return state.rows[kind]?.find(r=>r.value.project_ref?.entity_id===state.project);}
const sameRef=(a,b)=>a&&b&&['kind','entity_id','revision','content_sha256'].every(k=>a[k]===b[k]);
const project=()=>state.rows.project?.find(r=>r.ref.entity_id===state.project);
const profile=()=>state.rows.profile?.find(r=>r.ref.entity_id===state.profile);
function refOptions(select,items,label,selectedId){select.replaceChildren(el('option',label,{value:''}));for(const item of items)select.append(el('option',item.value.title||`${item.value.primary_business} · ${item.value.regions.join('、')}`,{value:item.ref.entity_id}));select.value=selectedId||'';}
async function load(){const epoch=++state.epoch;const [status,...rows]=await Promise.all([api('status'),...kinds.map(kind=>api('list',{kind}))]);if(epoch!==state.epoch)return;
  state.status=status;for(let i=0;i<kinds.length;i++)state.rows[kinds[i]]=rows[i];
  if(!state.profile&&rows[0].length)state.profile=rows[0][0].ref.entity_id;
  refOptions($('profile-select'),state.rows.profile,'先建立画像',state.profile);refOptions($('project-select'),state.rows.project,'选择项目',state.project);
  renderJobs();render();notice('记录已读取。内容修改会保存新版本；审阅状态随版本更新。');}
function renderJobs(){const node=$('jobs');node.replaceChildren();for(const job of state.status.jobs.slice(-8).reverse()){
  const item=el('div',null,{class:'job'});item.append(el('span',`${jobLabels[job.kind]||job.kind} · ${labels[job.state]||job.state}`));
  if(job.error)item.append(el('p',job.error));
  if(['queued','running'].includes(job.state))item.append(button('取消',async()=>{await api('cancel',{id:job.id});await load();}));
  if(job.kind==='export'&&job.state==='succeeded'&&job.output?.id)item.append(el('a','下载拍摄内容包',{href:'/api/qx-media/download?id='+job.output.id}));
  if(job.kind==='interview'&&job.output?.questions)for(const question of job.output.questions)item.append(el('p',question));
  node.append(item);
}if(!node.childNodes.length)node.append(el('p','尚无任务。'));}
async function submit(request){const active=state.project,request_id=crypto.randomUUID();sessionStorage.setItem('qx-media-request',request_id);let job;
  try{job=await api('submit',{request_id,...request});}catch(error){if(error.status>=400&&error.status<500&&error.status!==408){sessionStorage.removeItem('qx-media-request');throw error;}job=await api('job_by_request',{request_id}).catch(()=>null);if(!job)throw Error('提交结果尚未确认，已保留请求编号。请刷新任务记录，不要重复提交。');}
  sessionStorage.removeItem('qx-media-request');if(active!==state.project)return;notice('任务已受理，可继续查看资料。');
  for(let n=0;n<180;n++){await new Promise(resolve=>setTimeout(resolve,1000));const current=await api('job',{id:job.id});if(active!==state.project)return;
    notice(labels[current.state]||current.state);if(!['queued','running','cancel_requested'].includes(current.state)){await load();if(current.state==='failed'||current.state==='outcome_unknown')notice(current.error||labels[current.state],true);return;}}
  notice('任务仍在后台，请刷新任务记录查看；不会自动重复提交。');}
function switchTab(tab){state.tab=tab;for(const node of document.querySelectorAll('[data-tab]'))node.setAttribute('aria-current',node.dataset.tab===tab?'page':'false');render();}
function render(){const main=$('main');main.replaceChildren();$('project-note').textContent=project()?`当前项目：${project().value.title} · ${project().value.target_duration_ms/1000} 秒`:'先选画像，再建立一个内容项目。';
  ({profile:renderProfile,topics:renderTopics,content:renderContent,shooting:renderShooting,exports:renderExports}[state.tab])(main);}
function renderProfile(main){main.append(el('h2','我的 IP'),el('p','填写服务地区、业务、受众和表达风格即可开始。人生问询可以跳过。',{class:'hint'}));
  const fields=el('div',null,{class:'fields'}),value=profile()?.value||{};main.append(fields);
  field(fields,'服务地区（多个地区用逗号分开）','regions',(value.regions||[]).join('，'));
  field(fields,'主要业务','business',value.primary_business||'');field(fields,'目标受众','audience',value.audience||'');field(fields,'表达风格','style',value.style||'平实、清楚');
  row(main,button('保存画像',async()=>{const current=profile();const result=await api('save_profile',{value:{regions:$('regions').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),primary_business:$('business').value,secondary_business:value.secondary_business||[],audience:$('audience').value,style:$('style').value},expected_revision:current?.ref.revision||0,...current?{entity_id:current.ref.entity_id}:{}});state.profile=result.entity_id;await load();},true),button('新建另一画像',()=>{state.profile=null;render();}));
  if(!profile())return;
  main.append(el('h3','个人经历与表达资料'),el('p','保存后默认仅自己可见。只有你确认可公开的版本，才能用于内容；写作样本不会被当作你的经历。',{class:'hint'}));
  field(main,'资料类别','memory-kind','experience','select',[['experience','个人经历'],['opinion','个人观点'],['style_sample','表达样本'],['identity','身份与业务']]);field(main,'原话或资料摘录','memory-text','','textarea');
  row(main,button('保存为私人资料',async()=>{await api('add_memory',{profile_ref:profile().ref,category:$('memory-kind').value,original:$('memory-text').value});await load();}),button('生成最多三个补充问题',async()=>{if(!$('model-consent').checked)throw Error('请先确认本次模型调用。');await submit({kind:'interview',profile_ref:profile().ref,purpose:'media_interview',model_authorized:true});}));modelConsent(main);
  for(const memory of state.rows.memory.filter(m=>m.value.profile_ref.entity_id===state.profile)){const item=el('div',null,{class:'entry'});item.append(el('p',memory.value.original),el('p',{unconfirmed:'私人 · 尚未确认公开',confirmed:'已确认可公开',revoked:'已撤回公开'}[memory.value.confirmation],{class:'badge'}));
    const stale=memory.value.profile_ref.revision!==profile().ref.revision;
    row(item,button(stale?'按当前画像重新确认公开':memory.value.confirmation==='confirmed'?'撤回公开':'确认此版本可公开',async()=>{await api(!stale&&memory.value.confirmation==='confirmed'?'revoke_memory':'confirm_memory',{ref:memory.ref});await load();}));main.append(item);}}
function modelConsent(main){const label=el('label');const check=el('input',null,{type:'checkbox',id:'model-consent'});label.append(check,document.createTextNode('本次允许使用已配置的 DeepSeek 处理选中内容并产生用量（含最多一次格式修复）'));main.append(label);if(!state.status.model_configured)main.append(el('p','尚未配置模型；你仍可手工编辑与导出。',{class:'hint'}));}
function renderTopics(main){main.append(el('h2','今日选题'),el('p','来源日期与事件时间分别记录。列表和视频标题只作线索，使用前需核对正文。',{class:'hint'}));
  row(main,button('刷新公开来源',async()=>submit({kind:'source_refresh',source_ids:state.status.sources.map(s=>s.id),query:'公开来源列表'})));
  field(main,'按主题检索公开网页（最多 128 字）','search-query',profile()?.value.primary_business||'');
  const consent=el('label');consent.append(el('input',null,{type:'checkbox',id:'source-consent'}),document.createTextNode('允许本次官方检索或原文读取产生用量，每次按钮操作最多发送一次请求，不自动重试'));main.append(consent);
  row(main,button('用 DeepSeek 官方检索',async()=>{if(!$('source-consent').checked)throw Error('请先确认本次检索用途和用量。');await submit({kind:'source_search',query:$('search-query').value,purpose:'media_sources',model_authorized:true});}));
  if(profile()){
    const recommendations=el('section');main.append(recommendations);const epoch=state.epoch,profileId=state.profile;
    api('recommendations',{profile_ref:profile().ref}).then(items=>{if(!recommendations.isConnected||epoch!==state.epoch||profileId!==state.profile)return;recommendations.append(el('h3','按当前画像匹配的选题'),el('p','规则分用于解释匹配度，不预测播放量；热度未取得时留空。',{class:'hint'}));for(const item of items){const card=el('div',null,{class:'entry'});card.append(el('h3',item.value.title),el('p',`匹配 ${item.total_score}/100 · ${item.reasons.join('；')} · 热度：${item.heat??'未知'}`));card.append(button('使用此选题',()=>{state.event=item.ref.entity_id;state.source=item.value.source_refs[0]?.entity_id;state.project=null;switchTab('content');}));recommendations.append(card);}}).catch(e=>notice(e.message,true));
  }
  for(const health of state.status.source_health||[]){const name=state.status.sources.find(s=>s.id===health.source_id)?.title||health.source_id;main.append(el('p',`${name}：${{fresh:'已取得页面，正文与日期仍需核对',stale:'刷新失败，保留上次取得的内容',error:'暂未取得内容'}[health.state]} · 检查时间：${health.checked_at}`,{class:'hint'}));}
  const detail=el('details');detail.append(el('summary','手工导入 URL 或摘录'));field(detail,'来源标题','source-title');field(detail,'原文链接（可留空）','source-url');field(detail,'来源类型','source-kind','news','select',[['news','新闻'],['law','法律或政策'],['video','视频线索'],['manual','其他手工资料']]);field(detail,'原文摘录或本人提供的转写','source-text','','textarea');
  row(detail,button('保存来源',async()=>{const text=$('source-text').value;await api('import_source',{title:$('source-title').value,url:$('source-url').value||null,source_kind:$('source-kind').value,content_origin:text?'user_notes':'metadata',text});await load();}));main.append(detail);
  if(!state.rows.source.length)main.append(el('p','暂无来源。可以刷新公开来源，或手工加入一条你已找到的新闻和摘录。',{class:'empty'}));
  for(const source of state.rows.source){const item=el('section',null,{class:'entry'});item.append(el('h3',source.value.title),el('p',`${source.value.content_scope==='metadata'?'仅元数据 · 待核线索':'可得正文'} · ${source.value.verification==='verified'?'已人工核对':'尚待核对'} · 发布日期：${source.value.published_at||'未知'}`,{class:'badge'}));
    if(source.value.url)item.append(el('a','查看来源原页',{href:source.value.url,target:'_blank',rel:'noopener noreferrer'}));item.append(el('p',source.value.text.slice(0,500),{class:'quote'}));
    if(source.value.discovery_note)item.append(el('p','检索摘要（不可作为引文）：'+source.value.discovery_note,{class:'hint'}));
    row(item,button('用于新项目',()=>{state.source=source.ref.entity_id;state.event=null;state.project=null;switchTab('content');}));
    if(source.value.url)item.append(button('官方读取此页原文',async()=>{if(!$('source-consent').checked)throw Error('请先确认本次原文读取用途和用量。');await submit({kind:'source_fetch',source_ref:source.ref,purpose:'media_sources',model_authorized:true});}));
    if(source.value.text)renderEventForm(item,source);
    main.append(item);}}

function renderEventForm(parent,source){
  const detail=el('details');detail.append(el('summary','核对事件地区与业务归属'));const prefix='event-'+source.ref.entity_id;
  const title=field(detail,'选题标题',prefix+'-title',source.value.title);
  const quote=field(detail,'说明事件发生地或规则适用地区的原文片段',prefix+'-quote','','textarea');
  const region=field(detail,'地区全称（如：吉林省/长春市/朝阳区）',prefix+'-region',profile()?.value.regions[0]||'');
  const relation=field(detail,'与该地区的关系',prefix+'-relation','local_event','select',[['local_event','该地发生的事件'],['local_rule','该地适用的规则'],['national_local_angle','全国规则，本地可作解释'],['other_region','外地事件，仅供借鉴']]);
  const business=field(detail,'业务类别',prefix+'-business',profile()?.value.primary_business||'');
  const happened=field(detail,'事件时间（未知留空）',prefix+'-date','');happened.type='datetime-local';
  const label=el('label'),check=el('input',null,{type:'checkbox'});label.append(check,document.createTextNode('我已核对原文，并确认这里指事件或规则地区；同名地区已辨明，不是报道机构地址'));detail.append(label);
  detail.append(button('保存已核对选题',async()=>{if(!check.checked)throw Error('请先核对地区依据。');let ref=source.ref;if(source.value.verification!=='verified')ref=await api('confirm_source',{ref});await api('save_event',{value:{title:title.value,source_refs:[ref],claims:[],regions:[{region_key:region.value,relation:relation.value,source_ref:ref,evidence_quote:quote.value,status:'unconfirmed'}],business_tags:[business.value],event_at:happened.value?new Date(happened.value).toISOString():null,published_at:source.value.published_at},confirm_regions:true,expected_revision:0});await load();}));parent.append(detail);
}
function renderContent(main){main.append(el('h2',project()?project().value.title:'建立内容项目'));
  if(!profile()){main.append(el('p','先填写最小画像，即可开始选题。'));main.append(button('填写画像',()=>switchTab('profile'),true));return;}
  if(!project()){
    field(main,'选题名称','project-title',state.rows.source.find(s=>s.ref.entity_id===state.source)?.value.title||'');field(main,'目标秒数','duration','60');
    row(main,button('建立项目',async()=>{const ref=await api('save_project',{value:{profile_ref:profile().ref,title:$('project-title').value,audience:profile().value.audience,target_duration_ms:Number($('duration').value)*1000},expected_revision:0});state.project=ref.entity_id;await load();},true));return;}
  const brief=selected('brief'),script=selected('script');
  if(!sameRef(project().value.profile_ref,profile().ref)){
    main.append(el('p','画像已经更新。确认项目采用新画像后，请依次重新保存事实、文稿和拍摄方案；历史版本会保留。',{class:'hint'}));
    main.append(button('项目采用当前画像',async()=>{const current=project();await api('save_project',{value:{...current.value,profile_ref:profile().ref,audience:profile().value.audience},entity_id:current.ref.entity_id,expected_revision:current.ref.revision});await load();},true));return;
  }
  const facts=el('details');facts.open=!brief;facts.append(el('summary',brief?'事实与来源（编辑会使已有文稿需重新核对）':'先准备事实 brief'));
  const sourceSelect=field(facts,'本次依据','brief-source',state.source||brief?.value.claims[0]?.source_ref.entity_id||'','select',[['','常青选题 / 个人观点（不引用新闻事实）'],...state.rows.source.map(s=>[s.ref.entity_id,s.value.title])]);
  field(facts,'原文中的准确片段','quote',brief?.value.claims[0]?.evidence_quote||'','textarea');field(facts,'本次表达的事实或法律规则','claim',brief?.value.claims[0]?.text||'','textarea');
  field(facts,'选题角度','angle',brief?.value.angle||'');field(facts,'尚待核实的问题（没有可留空）','pending',(brief?.value.pending||[]).join('\n'),'textarea');
  field(facts,'若为法源，效力状态','law-status',brief?.value.claims[0]?.law_status||'unverified','select',[['unverified','尚待核实'],['effective','已核实现行有效'],['draft','草案'],['pending','尚未生效'],['repealed','已失效']]);field(facts,'法律适用范围（法源必填）','law-scope',brief?.value.claims[0]?.applicability||'');
  const confirm=el('label');confirm.append(el('input',null,{id:'source-confirm',type:'checkbox'}),document.createTextNode('我已核对原文片段及其含义'));facts.append(confirm);
  const memories=state.rows.memory.filter(m=>m.value.confirmation==='confirmed'&&sameRef(m.value.profile_ref,profile().ref));
  if(memories.length){facts.append(el('p','选择本次允许引用的公开资料：'));for(const memory of memories){const label=el('label');const check=el('input',null,{type:'checkbox','data-memory-id':memory.ref.entity_id});check.checked=Boolean(brief?.value.memory_refs.some(r=>r.entity_id===memory.ref.entity_id));label.append(check,document.createTextNode(memory.value.summary));facts.append(label);}}
  row(facts,button('保存事实 brief',async()=>{
    let source=state.rows.source.find(s=>s.ref.entity_id===sourceSelect.value);const claims=[];
    if(source){
      if(!source.value.text.includes($('quote').value)||!$('quote').value.trim())throw Error('引用片段必须能在已取得的来源正文中找到。');
      let ref=source.ref;if($('source-confirm').checked&&source.value.verification!=='verified')ref=await api('confirm_source',{ref});
      const law=source.value.source_kind==='law';claims.push({id:brief?.value.claims[0]?.id||crypto.randomUUID(),text:$('claim').value,source_ref:ref,evidence_quote:$('quote').value,status:$('source-confirm').checked?'confirmed':'unconfirmed',kind:law?'law':'fact',...law?{law_name:source.value.title,law_status:$('law-status').value,applicability:$('law-scope').value}: {}});
    }
    const memory_refs=[...facts.querySelectorAll('[data-memory-id]:checked')].map(n=>memories.find(m=>m.ref.entity_id===n.dataset.memoryId).ref);
    await api('save_content',{kind:'brief',value:{project_ref:project().ref,profile_ref:project().value.profile_ref,angle:$('angle').value,audience:project().value.audience,event_ref:state.rows.event.find(e=>e.ref.entity_id===state.event)?.ref||brief?.value.event_ref||null,claims,memory_refs,pending:$('pending').value.split('\n').filter(Boolean)},expected_revision:brief?.ref.revision||0,...brief?{entity_id:brief.ref.entity_id}:{}});await load();},true));main.append(facts);
  if(!brief)return;
  main.append(el('h3','内容稿'));field(main,'三个标题候选（每行一个）','titles',(script?.value.titles||['','','']).join('\n'),'textarea');const speech=field(main,'口播稿（空行分段）','speech',(script?.value.segments||[]).map(s=>s.text).join('\n\n'),'textarea');speech.classList.add('speech');field(main,'图文 / 发布说明','caption',script?.value.caption||'','textarea');field(main,'封面文字','cover',script?.value.cover_text||'');
  row(main,button('保存文稿',async()=>{const old=script?.value.segments||[];const segments=$('speech').value.split(/\n\s*\n/).filter(s=>s.trim()).map((text,i)=>({id:old[i]?.id||crypto.randomUUID(),text,kind:brief.value.claims.some(c=>c.kind==='law')?'law':brief.value.claims.length?'fact':'opinion',claim_refs:brief.value.claims.map(c=>c.id),memory_refs:brief.value.memory_refs.filter(r=>!['style_sample','client_question'].includes(state.rows.memory.find(m=>m.ref.entity_id===r.entity_id)?.value.category))}));await api('save_content',{kind:'script',value:{project_ref:project().ref,brief_ref:brief.ref,titles:$('titles').value.split('\n').filter(Boolean),segments,caption:$('caption').value,cover_text:$('cover').value,timing_basis:'estimated'},expected_revision:script?.ref.revision||0,...script?{entity_id:script.ref.entity_id}:{}});await load();},true),button('生成文稿草案',async()=>{if(!$('model-consent').checked)throw Error('请先确认本次模型调用。');await submit({kind:'script',project_ref:project().ref,input_refs:[brief.ref],purpose:'media_content',model_authorized:true,expected_output_revision:script?.ref.revision||0,output_ref:script?.ref||null});}));modelConsent(main);
}
function renderShooting(main){main.append(el('h2','拍摄方案'));const script=selected('script'),plan=selected('shooting_plan');
  if(project())renderConstraints(main);
  if(!script){main.append(el('p','先保存一份口播稿，再准备拍摄方案。'));main.append(button('编辑内容稿',()=>switchTab('content')));return;}
  main.append(el('p','默认：一人、一部手机、固定支撑、办公室。时长为计划估计；拍摄前试读。',{class:'hint'}));
  row(main,button('整理固定机位自拍方案',async()=>{const duration=project().value.target_duration_ms,count=script.value.segments.length;const base=Math.floor(duration/count);if(base<1000)throw Error('台词分段过多，请合并后再整理。');const shots=script.value.segments.map((s,i)=>({id:crypto.randomUUID(),script_segment_ids:[s.id],estimated_duration_ms:base+(i===count-1?duration-base*count:0),shot_size:i===0?'medium':'close',camera_position:'手机固定，镜头与眼睛大致同高；改变景别时暂停录制后调整距离',subject_action:'面向镜头口播',spoken_cue:s.text,movement_intent:'static',lighting_note:'面向窗侧柔光，避免背光',audio_note:'安静环境，先录十秒试听',props:[],equipment_required:['phone','tripod'],simple_alternative:'用稳固支撑固定手机，保持同一景别'}));await api('save_content',{kind:'shooting_plan',value:{project_ref:project().ref,script_ref:script.ref,constraints:project().value.constraints,timing_basis:'estimated',planned_duration_ms:duration,shots,shooting_checklist:['核对已审台词','清理背景，不出现客户资料','固定手机与机位','试听收音','按镜头顺序录制，保留停顿余量']},expected_revision:plan?.ref.revision||0,...plan?{entity_id:plan.ref.entity_id}:{}});await load();},true),button('生成个性化拍摄建议',async()=>{if(!$('model-consent').checked)throw Error('请先确认本次模型调用。');await submit({kind:'shooting_plan',project_ref:project().ref,input_refs:[script.ref],purpose:'media_content',model_authorized:true,expected_output_revision:plan?.ref.revision||0,output_ref:plan?.ref||null});}));modelConsent(main);
  if(plan){const wrap=el('div',null,{class:'table-scroll',tabindex:'0',role:'region','aria-label':'分镜表，可横向滚动'}),table=el('table');const head=el('tr');for(const text of ['镜头','台词','机位与动作','建议秒数','收音 / 替代'])head.append(el('th',text));table.append(head);plan.value.shots.forEach((s,i)=>{const tr=el('tr');for(const text of [String(i+1),s.spoken_cue,s.camera_position+'；'+s.subject_action,String(s.estimated_duration_ms/1000),s.audio_note+'；'+s.simple_alternative])tr.append(el('td',text));table.append(tr);});wrap.append(table);main.append(wrap);main.append(el('h3','拍摄清单'));const list=el('ul');for(const text of plan.value.shooting_checklist)list.append(el('li',text));main.append(list);renderPlanEditor(main,plan);}}
function renderConstraints(main){const current=project(),value=current.value.constraints,detail=el('details');detail.append(el('summary','编辑拍摄条件'));
  field(detail,'拍摄方式','capture-mode',value.capture_mode,'select',[['phone_tripod','单人手机固定拍摄'],['assisted','有人协助拍摄']]);
  field(detail,'拍摄人数','people-count',value.people_count);field(detail,'机位数量','camera-count',value.camera_count);field(detail,'拍摄地点','shoot-location',value.location);
  field(detail,'可用设备（逗号分开；phone 手机，tripod 支架）','equipment',value.equipment.join(','));field(detail,'可用分钟数','available-minutes',value.available_minutes);field(detail,'计划时长（秒）','shoot-duration',current.value.target_duration_ms/1000);
  detail.append(el('p','修改条件会更新项目版本，请重新保存事实、文稿和分镜后再审阅。',{class:'hint'}));
  detail.append(button('保存拍摄条件',async()=>{await api('save_project',{value:{...current.value,target_duration_ms:Number($('shoot-duration').value)*1000,constraints:{capture_mode:$('capture-mode').value,camera_count:Number($('camera-count').value),people_count:Number($('people-count').value),location:$('shoot-location').value,equipment:$('equipment').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),available_minutes:Number($('available-minutes').value)}},entity_id:current.ref.entity_id,expected_revision:current.ref.revision});await load();}));main.append(detail);
}
function renderPlanEditor(main,plan){const detail=el('details');detail.append(el('summary','编辑分镜与清单'));const edits=plan.value.shots.map((shot,i)=>{const item=el('fieldset');item.append(el('legend',`镜头 ${i+1}`));detail.append(item);const inputs={};
  for(const [key,label]of Object.entries({camera_position:'机位',subject_action:'人物动作',spoken_cue:'台词提示',lighting_note:'灯光',audio_note:'收音',simple_alternative:'简单替代方案'}))inputs[key]=field(item,`镜头 ${i+1} ${label}`,`shot-${i}-${key}`,shot[key],'textarea');
  const seconds=field(item,`镜头 ${i+1} 建议秒数`,`shot-${i}-seconds`,shot.estimated_duration_ms/1000);
  return ()=>({...shot,...Object.fromEntries(Object.entries(inputs).map(([k,n])=>[k,n.value])),estimated_duration_ms:Number(seconds.value)*1000});});
  const checklist=field(detail,'拍摄清单（每行一项）','edit-checklist',plan.value.shooting_checklist.join('\n'),'textarea');
  detail.append(button('保存分镜修改',async()=>{await api('save_content',{kind:'shooting_plan',value:{...plan.value,shots:edits.map(read=>read()),shooting_checklist:checklist.value.split('\n').map(s=>s.trim()).filter(Boolean)},entity_id:plan.ref.entity_id,expected_revision:plan.ref.revision});await load();}));main.append(detail);
}
function renderExports(main){main.append(el('h2','审阅与导出'));const script=selected('script'),plan=selected('shooting_plan');if(!script||!plan){main.append(el('p','请先保存内容稿和拍摄方案。'));return;}
  const feedback=selected('feedback'),feedbackBox=el('details');feedbackBox.append(el('summary','人工记录采用或发布情况'));const status=field(feedbackBox,'记录状态','feedback-status',feedback?.value.status||'adopted','select',[['adopted','已采用'],['ignored','暂不采用'],['published','本人已手工发布']]);const note=field(feedbackBox,'记录备注','feedback-note',feedback?.value.note||'','textarea');feedbackBox.append(el('p','这里只保存记录，不会向任何平台发布。',{class:'hint'}));feedbackBox.append(button('保存使用记录',async()=>{await api('save_feedback',{value:{project_ref:project().ref,status:status.value,note:note.value},expected_revision:feedback?.ref.revision||0,...feedback?{entity_id:feedback.ref.entity_id}:{}});await load();}));main.append(feedbackBox);
  main.append(el('p','确认事实、法律适用、个人经历与拍摄条件后，批准当前版本。之后修改文稿或来源，需要重新审阅。'),el('p','内容包包含 Word、Markdown、提词文本、分镜 CSV、拍摄清单和来源版本记录。',{class:'hint'}));
  const check=el('label');check.append(el('input',null,{type:'checkbox',id:'review-confirm'}),document.createTextNode('我已审阅当前文稿、依据和拍摄方案'));main.append(check);
  const refs=[script.ref,plan.ref];row(main,button('导出标记草稿的内容包',async()=>submit({kind:'export',project_ref:project().ref,mode:'draft',expected_refs:refs})),button('批准并导出当前版本',async()=>{if(!$('review-confirm').checked)throw Error('请先完成内容审阅。');const review=await api('approve',{project_ref:project().ref,refs});await submit({kind:'export',project_ref:project().ref,mode:'approved',expected_refs:refs,review_ref:review});},true));
  main.append(el('h3','导出记录'));for(const job of state.status.jobs.filter(j=>j.kind==='export'&&j.input.project_ref.entity_id===state.project)){const item=el('div',null,{class:'entry'});item.append(el('p',`${job.input.mode==='draft'?'草稿':'已审版本'} · ${labels[job.state]}`));if(job.output?.id)item.append(el('a','下载拍摄内容包',{href:'/api/qx-media/download?id='+job.output.id}));main.append(item);}}
for(const node of document.querySelectorAll('[data-tab]'))node.onclick=()=>switchTab(node.dataset.tab);
$('profile-select').onchange=()=>{state.profile=$('profile-select').value;render();};
$('project-select').onchange=()=>{state.project=$('project-select').value;state.epoch++;if(project())state.profile=project().value.profile_ref.entity_id;render();};
$('refresh').onclick=()=>act($('refresh'),async()=>{const request_id=sessionStorage.getItem('qx-media-request');if(request_id){const job=await api('job_by_request',{request_id});if(job)sessionStorage.removeItem('qx-media-request');}await load();});
load().catch(error=>notice(error.message,true));
