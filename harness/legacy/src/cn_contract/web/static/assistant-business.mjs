// Local preparation has no model permit; an uncertain POST is recovered by GET only.
// Only the current instruction is interpreted here; backend replay keeps its legacy helpers.
const rightsWords=['商标','专利','著作权','版权','商业秘密'];
const ipWords=['商标侵权','商标初筛','商标分析','商标筛查','商标因素','分析商标','筛查商标',
  '侵权初筛','侵权筛查','侵权分析','侵权因素','知识产权初筛','知识产权分析','知识产权侵权',
  '专利侵权','著作权侵权','版权侵权','商业秘密侵权','IP初筛','IP分析'];
const workflowPatterns={
  sales:['客户咨询','接待客户','客户接待','客户的咨询','客户诉求','理清诉求','诉求澄清','接待跟进','销售接待'],
  case:['整理案件','案件整理','整理这个案件','整理材料','整理证据','梳理事实','材料线索','时间线','事实线索','起草起诉状','起草答辩状',...ipWords],
  contract:['审查合同','审查这个合同','审阅合同','审查这份合同','合同审查','重新审查'],
  court:['模拟法庭','模拟开庭','模拟对方律师','法官角度','对方律师和法官','庭审准备'],
};
const conditionPattern=/如果|假如|要是|除非|只有|一旦|若/;
const actionPattern=/审查(?!起诉)|审阅|分析|整理|处理|接待|诉求|庭审|模拟|起草|初筛|筛查/;
const continuationPattern=/继续|补充|这次任务|这个任务|上述|刚才/;
const negationPrefix=/(?:不需要|无需|不用|不要|别|暂不|暂时不|不再|先不|禁止|取消|停止|暂停|撤回)[^，,。.!！?？；;\n]{0,10}$/;
const ipNegationPrefix=/(?:不做|不进行)[^，,。.!！?？；;\n]{0,10}$/;
const currentNegationPrefix=/(?:不需要|无需|不用|不要|别|暂不|暂时不|不再|先不|禁止|取消|停止|暂停|撤回|不做|不进行|不予)[^\n]*(?![\s\S])/;
function directText(value){
  return value.replace(/“[^”]*”|‘[^’]*’|「[^」]*」|"[^"]*"/g,'').replace(/https?:\/\/[^\s，。；！？]+/g,'');
}
// A full stop or a newline starts an independent statement; a semicolon, comma or
// quotation cannot release a condition. Quotes stay whole, so punctuation inside a
// quotation never splits a sentence or promotes a quoted action to a command.
function currentSegments(content){
  const segments=[];let conditional=false,hasCondition=false,start=0;
  const take=part=>{
    conditional=conditional||conditionPattern.test(directText(part));
    hasCondition=hasCondition||conditional;
    if(!conditional&&part.trim())segments.push(part);
  };
  for(const match of content.matchAll(/“[^”]*”|‘[^’]*’|「[^」]*」|"[^"]*"|https?:\/\/[^\s，。；！？]+|[。.!！?？；;\n]/g)){
    const char=match[0],index=match.index;
    if(char.length!==1)continue;
    if(/[.!?]/.test(char)&&/[A-Za-z0-9]/.test(content.slice(Math.max(0,index-1),index)+content.slice(index+1,index+2)))continue;
    take(content.slice(start,index));start=index+1;
    if(/[。.!！?？\n]/.test(char))conditional=false;
  }
  take(content.slice(start));
  return {segments,hasCondition};
}
function currentClauses(content){
  const clauses=[];let start=0;
  for(const match of content.matchAll(/“[^”]*”|‘[^’]*’|「[^」]*」|"[^"]*"|https?:\/\/[^\s，。；！？]+|[，,]/g)){
    if(match[0].length===1){clauses.push(content.slice(start,match.index));start=match.index+1;}
  }
  clauses.push(content.slice(start));return clauses;
}
function currentReportParts(content){
  // A comma cannot turn an unquoted report into a direct instruction.
  const parts=[];let reporting=false;
  for(const clause of currentClauses(content)){
    if(reporting){parts.push(['',clause]);continue;}
    const marker=[...clause.matchAll(/“[^”]*”|‘[^’]*’|「[^」]*」|"[^"]*"|https?:\/\/[^\s，。；！？]+|(?<report>对方说|客户说(?:明)?|转述|引用)/g)]
      .find(match=>match.groups.report!==undefined);
    if(!marker)parts.push([clause,'']);
    else{
      const tail=clause.slice(marker.index+marker[0].length);
      reporting=!/^\s*[:：]?\s*(?:“[^”]*”|‘[^’]*’|「[^」]*」|"[^"]*")\s*$/.test(tail);
      parts.push([clause.slice(0,marker.index),tail]);
    }
  }
  return parts;
}
function currentCommandText(content){
  return currentSegments(content).segments.flatMap(part=>currentReportParts(part))
    .map(([direct])=>directText(direct)).join('\n');
}
function isNegated(value,index,word){
  const prefix=value.slice(Math.max(0,index-16),index);
  return negationPrefix.test(prefix)||
    (ipWords.includes(word)||rightsWords.includes(word))&&ipNegationPrefix.test(prefix);
}
function latestCommand(content,words){
  const value=currentCommandText(content);
  let latest=null;
  for(const word of words)for(let index=value.indexOf(word);index!==-1;index=value.indexOf(word,index+1))
    if(!latest||index>latest.index)latest={index,word};
  if(!latest)return null;
  const prefix=value.slice(0,latest.index).split('\n').at(-1);
  if(currentNegationPrefix.test(prefix)||prefix.endsWith('不'))return false;
  return !isNegated(value,latest.index,latest.word);
}
function commanded(content,words){
  const value=currentCommandText(content);
  return words.some(word=>{
    for(let index=value.indexOf(word);index!==-1;index=value.indexOf(word,index+1))
      if(!isNegated(value,index,word))return true;
    return false;
  });
}
function workflowCommand(content,workflow){
  let words=workflowPatterns[workflow];
  if(workflow==='contract')return latestCommand(content,words)===true||
    commanded(content,['我是甲方','我是乙方','代表甲方','代表乙方'])&&latestCommand(content,['审查','审阅','修改'])===true;
  if(workflow==='case'&&latestCommand(content,ipWords.filter(word=>word.includes('商标')))===true&&
      latestCommand(content,['商标'])!==false)return true;
  if(workflow==='case'&&latestCommand(content,['商标'])===false)
    words=words.filter(word=>!ipWords.includes(word)||['专利','著作权','版权','商业秘密'].some(right=>word.includes(right)));
  return latestCommand(content,words)===true;
}
function legacyHold(value){
  let held=false;
  const action=/审查|审阅|分析|整理|处理|接待|诉求|庭审|模拟|起草/;
  for(const original of value.split(/\r?\n/)){
    const line=directText(original);
    if(/^\s*(?:请|现在)?(?:停止|暂停|取消|撤回)[。！!\s]*$/.test(line)||
        /只(?:接收|收集|保存|接收并保存)材料|(?:停止|暂停|取消|撤回)(?:本次)?(?:处理|分析|任务|指令)|(?:不要|不需要|无需|不用|别|暂不|暂时不|不再|先不)[^，,。.!！?？；;\n]{0,6}(?:分析|处理)/.test(line)||
        conditionPattern.test(line)&&action.test(line)||
        line.split(/[，,。.!！?？；;]/).some(clause=>/对方说|客户说|转述|引用/.test(clause)&&action.test(clause))||
        line!==original&&action.test(original)&&!action.test(line))held=true;
  }
  return held;
}
function currentExecutionHold(value){
  const {segments,hasCondition}=currentSegments(value);
  const hasRequest=segments.some(part=>Object.keys(workflowPatterns).some(workflow=>workflowCommand(part,workflow)));
  let held=hasCondition&&!hasRequest;
  for(const original of segments){
    const line=directText(original);
    if(line!==original&&(actionPattern.test(original)&&!actionPattern.test(line)||
        !hasRequest&&continuationPattern.test(original)&&!continuationPattern.test(line)))held=true;
    for(const [direct,reported] of currentReportParts(original)){
      const clause=directText(direct),report=reported.replace(/https?:\/\/[^\s，。；！？]+/g,'');
      if([clause,directText(reported)].some(part=>legacyHold(part)||
          /^\s*(?:请|现在|先|好的|好|暂时)*(?:停止|暂停|取消|撤回|停)(?:一下)?\s*$/.test(part)||
          /^\s*(?:请|现在|先)*(?:别做了|别处理了|只收材料)\s*$/.test(part))||
          actionPattern.test(report)||!hasRequest&&continuationPattern.test(report))held=true;
      else if(/^(?:现在|请|重新开始|继续|接着|开始|重新|做)*(?:审查|审阅|整理|梳理|起草|模拟|庭审|客户接待|接待客户|理清|诉求澄清|案件整理|合同审查|商标)/.test(clause.trim())&&
          Object.keys(workflowPatterns).some(workflow=>workflowCommand(clause,workflow)))held=false;
    }
  }
  return held;
}
function classifyBusiness(value){
  if(currentExecutionHold(value))return null;
  const choices=Object.keys(workflowPatterns).filter(workflow=>workflowCommand(value,workflow));
  return choices.length===1?choices[0]:choices.length?'ambiguous':null;
}
function startsNewTask(value){
  return !currentExecutionHold(value)&&latestCommand(value,['重新审查','新建任务','开始新任务'])===true;
}
export function rejectedBusinessWorkflow(value,workflow){
  const words=workflowPatterns[workflow];
  return currentExecutionHold(value)||Boolean(words&&(latestCommand(value,words)===false||
    workflow==='case'&&latestCommand(value,['商标'])===false)&&
    !(workflow==='case'&&workflowCommand(value,workflow)));
}
export function negativeBusinessInstruction(value){
  if(currentExecutionHold(value))return true;
  return classifyBusiness(value)===null&&Object.keys(workflowPatterns).some(workflow=>rejectedBusinessWorkflow(value,workflow));
}
export function businessWorkflow(state) {
  const value=state.text||'';
  if(negativeBusinessInstruction(value))return null;
  const explicit={client_reply:'sales',material_organize:'case',contract_review:'contract',mock_trial:'court'}[state.skill];
  if(explicit)return explicit;
  if(state.skill || state.context?.selected?.length)return null;
  const classified=classifyBusiness(value);
  if(classified)return classified==='ambiguous'?'clarify':classified;
  if(state.materials?.items?.length)return 'continue';
  if(state.business?.selectedTask)return 'continue';
  return /继续|补充|这次任务|这个任务|上述|刚才/.test(currentCommandText(value))&&state.business?.items?.some(item=>item.task_id)?'continue':null;
}

export function createBusinessController(api,host) {
  const {state,readonly,uuid,notify}=host;
  let epoch=0,work=null,pending=null,accepted=null,acceptedContent='',explicitSelection=false;
  const initial=()=>({phase:'idle',canSend:false,active:false,items:[],error:null,selectedTask:null});
  state.business=initial();
  const token=()=>({epoch,host:host.token(),cid:state.id});
  const current=t=>t.epoch===epoch && host.current(t.host) && (!t.cid || t.cid===state.id);
  const usable=()=>!readonly&&!state.loading&&!state.conflict&&!host.blocked()&&
    !['saving','revoked','readonly','error'].includes(state.status)&&!!state.text.trim();
  function sync(){
    state.business.active=Boolean(api.submitBusiness&&(pending||businessWorkflow(state)));
    state.business.canSend=state.business.active&&!work&&!pending&&usable();
  }
  function selectOnlyTask(){
    const tasks=new Set(state.business.items.map(item=>item.task_id).filter(Boolean));
    if(!explicitSelection)state.business.selectedTask=tasks.size===1?[...tasks][0]:null;
    else if(!tasks.has(state.business.selectedTask)){state.business.selectedTask=null;explicitSelection=false;}
  }
  function failed(error,t){
    if(!current(t))return false;
    if(error.status===401||error.status===403)return host.fail(error,t.host);
    state.business.error={code:error.code||'REQUEST_FAILED',status:error.status||0};
    state.business.phase=pending?'unknown':'error';notify();return false;
  }
  function perform(action){
    if(work)return work;
    const t=token();
    work=Promise.resolve().then(()=>action(t)).catch(error=>failed(error,t)).finally(()=>{
      work=null;if(current(t)){sync();notify();}
    });
    notify();return work;
  }
  async function accept(result,t){
    const action=pending;
    if(!current(t))return false;
    if(!result||result.request_id!==action.body.request_id||result.scope?.conversation_id!==action.cid||
        result.scope.input_revision!==action.body.expected_scope.input_revision+1)throw {code:'INVALID_RESPONSE'};
    host.accept(action.body,{scope:result.scope},state.text===action.body.content);
    pending=null;state.business.phase='idle';state.business.error=null;
    accepted=result;acceptedContent=action.body.content;
    state.business.items=[...state.business.items.filter(item=>item.run_id!==result.run_id),result];
    if(explicitSelection)state.business.selectedTask=result.task_id||null;
    selectOnlyTask();
    await host.refreshDraft();return true;
  }
  async function recover(t){
    const result=await api.findBusiness(pending.cid,pending.body.request_id);
    if(!current(t))return false;
    if(!result){state.business.phase='unknown';return false;}
    return accept(result,t);
  }
  function send(suggestion=null){
    if(pending)return perform(recover);
    if(!api.submitBusiness||!usable()||!(businessWorkflow(state)||suggestion))return Promise.resolve(false);
    return perform(async t=>{
      if(!await host.saveDraft()||!current(t))return false;
      const inferred=businessWorkflow(state);
      if(negativeBusinessInstruction(state.text))return false;
      const route=suggestion&&!rejectedBusinessWorkflow(state.text,suggestion)&&
        (!inferred||inferred==='continue'&&!state.business.items.some(item=>item.task_id))?suggestion:inferred;
      const workflow=['sales','case','contract','court'].includes(route)?route:null;
      const fresh=startsNewTask(state.text);
      let selected=state.business.items.find(item=>item.task_id===state.business.selectedTask);
      if(!selected&&route==='continue'&&!fresh){
        const candidates=new Map(state.business.items.filter(item=>item.task_id).map(item=>[item.task_id,item]));
        if(candidates.size===1)selected=candidates.values().next().value;
      }
      const task=route!=='clarify'&&selected&&(!workflow||selected.workflow===workflow)&&!fresh?selected.task_id:null;
      pending={cid:state.id,body:{request_id:uuid(),expected_scope:{...state.view.scope},
        expected_composer_revision:state.view.composer_revision,content:state.text,workflow,
        ...(task?{task_id:task}:{}),...(fresh?{new_task:true}:{})}};
      state.business.phase='submitting';notify();
      try{return await accept(await api.submitBusiness(pending.cid,pending.body),t);}
      catch(error){if(error.status>=400&&error.status<500){pending=null;state.business.phase='error';}throw error;}
    });
  }
  function refresh(){
    if(pending)return perform(recover);
    if(!api.getBusinessHistory||!state.id)return Promise.resolve(true);
    return perform(async t=>{
      const items=await api.getBusinessHistory(state.id);
      if(!current(t))return false;
      if(!Array.isArray(items)||items.some(item=>item.scope?.conversation_id!==state.id))throw {code:'INVALID_RESPONSE'};
      state.business.items=items;selectOnlyTask();return true;
    });
  }
  return {sync,send,refresh,unknown:()=>Boolean(pending),blocked:()=>Boolean(work||pending),busy:()=>Boolean(work),
    select(id){
      if(work||pending||readonly)return;
      const item=state.business.items.find(item=>item.task_id===id);
      if(id&&!item)return;
      state.business.selectedTask=id||null;
      explicitSelection=Boolean(id);
      if(id&&!state.text.trim()){
        const last=state.business.items.at(-1);
        const message=last&&!last.task_id?state.view?.messages?.find(message=>message.id===last.message_id):null;
        if(message)state.text=message.content;
      }
      sync();notify();
    },
    wait:()=>work||Promise.resolve(),handles:()=>state.business.active,lastAccepted:()=>accepted,lastAcceptedContent:()=>acceptedContent,
    reset(){epoch++;work=null;pending=null;accepted=null;acceptedContent='';explicitSelection=false;state.business=initial();}};
}
