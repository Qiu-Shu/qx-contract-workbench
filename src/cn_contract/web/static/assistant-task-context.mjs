// Source and fact controls stay in the conversation; all decisions remain explicit.
export async function renderTaskContext({execution,host,api,node,button,submit,valid,tell,readonly}) {
  const context=await api.request('/api/task-executions/'+execution.id+'/context');
  if(!valid())return;
  const anchors=new Map(context.parses.flatMap(parse=>parse.anchors).map(anchor=>[anchor.id,anchor]));
  if(context.facts){
    const details=node('details');details.append(node('summary','核对事实 · '+(context.review?'当次第 ':'当前第 ')+context.facts.version+' 版'));
    const decisions=[];
    for(const fact of context.facts.facts){
      const fields={total_price:'合同总价',attachment_price:'附件金额',addendum_price:'附件金额',payment_ratio_1:'第一项付款比例',payment_ratio_2:'第二项付款比例',payment_ratio:'付款比例',contract_period:'期间或期限',other_literal:'其他原文约定'};
      const statuses={unconfirmed:'待核对',confirmed:'已确认',corrected:'已更正',rejected:'已拒绝'};
      const row=node('fieldset');row.append(node('legend',fields[fact.field]||'待核对事实'));
      const value=fact.typed_value;
      row.append(node('p','候选值：'+String(value.amount??value.value??'待核对')+' '+(fact.unit||'')),node('p','当前状态：'+(statuses[fact.confirmation_status]||'待核对')));
      for(const id of fact.anchor_ids){
        const anchor=anchors.get(id);row.append(node('blockquote',anchor?.quote||'当前执行材料未包含此来源，请先核对。'));
      }
      if(!readonly&&execution.state==='awaiting_facts'){
        const label=node('label','本次核对'),select=node('select');select.setAttribute('aria-label','本次核对');label.append(select);
        for(const [value,text] of [['','保留当前状态'],['confirmed','确认原值'],['rejected','拒绝候选']]){
          const option=node('option',text);option.value=value;select.append(option);
        }
        const reasonLabel=node('label','核对理由'),reason=node('input');reason.type='text';reason.maxLength=1000;
        reasonLabel.append(reason);row.append(label,reasonLabel);decisions.push({fact,select,reason});
      }
      details.append(row);
    }
    if(decisions.length)details.append(button('保存本次事实核对',()=>{
      const chosen=decisions.filter(item=>item.select.value);
      if(!chosen.length||chosen.some(item=>!item.reason.value.trim())){tell('请选择需要核对的事实，并填写对应理由。');return;}
      return submit('/api/matters/'+execution.matter_id+'/facts/confirm','POST',{
        fact_version:context.facts.version,decisions:chosen.map(({fact,select,reason})=>({fact_id:fact.id,
          decision:select.value,confirmed_value:fact.typed_value,reason:reason.value.trim()}))});
    }));
    host.append(details);
    if(!readonly&&execution.state==='awaiting_facts')host.append(button('运行模拟审查',()=>{
      if(!context.facts.facts.length||context.facts.facts.some(f=>!['confirmed','corrected','rejected'].includes(f.confirmation_status))){
        details.open=true;tell('请先在上方逐项核对事实；系统不会代替律师确认。');return;
      }
      return submit('/api/task-executions/'+execution.id+'/review','POST',{
        request_id:crypto.randomUUID(),review:{fact_version:context.facts.version,document_hashes:execution.document_versions}});
    }));
  }
  if(context.review){
    const details=node('details');details.open=true;details.append(node('summary','本次模拟审查结果 · '+({completed:'已完成',failed:'已停止'}[context.review.status]||'待核对')));
    details.append(node('p','这是既有合成审查结果，须核对来源与规则，不代表真实模型分析。'));
    for(const finding of context.review.findings){
      const issueNames={untrusted_instruction:'原文包含越权操作指令',missing_appendix:'附件材料缺失',obligation_direction:'通知义务与履行安排',guarantee_material:'保证安排证据待核实',payment_ratio_sum:'付款比例合计不一致',payment_math_insufficient:'付款数学证据不足',amount_conflict:'正文与附件金额冲突',confidentiality_training:'保密义务与训练授权关系',license_termination:'成果许可与终止交接关系'};
      const row=node('article');row.append(node('strong',issueNames[finding.issue_type]||finding.issue_type||'风险项'));
      for(const [name,label] of Object.entries({analysis:'分析',business_effect:'交易影响',recommendation:'修改建议',replacement_text:'建议条款',fallback:'备选方案'})){
        if(finding[name])row.append(node('p',label+'：'+finding[name]));
      }
      for(const id of finding.anchor_ids){const anchor=anchors.get(id);row.append(node('blockquote',anchor?.quote||'请核对本次执行的原文位置。'));}
      details.append(row);
    }
    for(const limitation of context.review.limitations)details.append(node('p',typeof limitation==='string'?limitation:JSON.stringify(limitation)));
    host.append(details);
  }
}

export function renderNewMatter({execution,host,node,button,submit,tell}) {
  const details=node('details');details.open=true;details.append(node('summary','在本对话建立合成审查档案'));
  const title=node('input');title.type='text';title.maxLength=300;title.value=execution.manifest.instruction?.slice(0,100)||'合成合同审查';
  const label=node('label','档案名称');label.append(title);details.append(label);
  const choice=(caption,options)=>{const label=node('label',caption),select=node('select');select.setAttribute('aria-label',caption);
    for(const [value,text] of [['','请选择'],...options]){const option=node('option',text);option.value=value;select.append(option);}
    label.append(select);details.append(label);return select;};
  const type=choice('合同类型',[['sales','买卖'],['service','服务'],['lease','租赁'],['nda','保密'],['unknown','其他或尚未确定']]);
  const role=choice('我方角色',[['buyer','买方'],['seller','卖方'],['customer','委托方'],['provider','服务方'],['lessor','出租人'],['lessee','承租人'],['discloser','披露方'],['recipient','接收方'],['mutual','双方'],['party_a','甲方'],['party_b','乙方']]);
  const mode=choice('合同状态',[['pre_sign','签署前'],['post_sign','签署后']]);
  details.append(button('保存档案并读取事实',()=>{
    if(!title.value.trim()||!type.value||!role.value||!mode.value){tell('请补充档案名称、合同类型、我方角色和合同状态。');return;}
    return submit('/api/task-executions/'+execution.id+'/create-and-prepare','POST',{
      request_id:crypto.randomUUID(),matter:{title:title.value.trim(),contract_type:type.value,
        position:role.value,review_mode:mode.value,objectives:['按当前任务指令核对合同']}});
  }));host.append(details);
}
