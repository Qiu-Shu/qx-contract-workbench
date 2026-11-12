// All names, contracts and authorities below are invented fixtures, not legal guidance.
const cases=[];
const methods=['authority-check','case-comparison','issue-memo','lecture-source-pack'];
for(const method of methods)for(const [i,status] of ['verified','partially_verified','unverified'].entries()){
 const id=`${method}-${i+1}`;
 cases.push({id,kind:'research',skill:'qx-'+method,status,
  material:`完全虚构的研究材料。委托人：测试公司甲${i+1}；相对人：测试公司乙${i+1}。\n事实发生日：2025-05-01；研究日：2026-11-12；适用区域：仅虚构试验区。\n虚构规则A第3条（旧版）：试验价款10000元。虚构规则A第3条（新版）：试验价款12000元。\n来源可核情况：${status}；没有真实法源链接。效力状态与时间适用范围仍待核。不得将本材料用于实际法律结论。`,
  note:`方法：${method}。材料自述状态：${status}；本轮真实法源评估：未核验。事实发生日：2025-05-01；研究日：2026-11-12；适用区域：仅虚构试验区。旧版10000元，新版12000元；适用版本待核。证据不足时不得说没有风险。\nsourceId: synthetic-${id}\nsourceType: 完全虚构的本地说明\ntitle: 虚构规则A\nissuer: 虚构主体，不是真实发布机关\narticle: 第3条\ncaseNo: 不适用（规则样本）\nfactDate: 2025-05-01\nresearchDate: 2026-11-12\nregion: 仅虚构试验区\nversion: 旧版/新版仅为材料陈述，真实发布、生效与过渡记录待核\neffect: 未核验\napplicability: 未核验\nevidence: 合成材料.txt，本轮 read_case_material 返回的原文与摘要另记 citations\nstatus: 未核验\nunresolved: 无真实官方原文或链接；离线没有执行联网检索。待补真实来源后复核，不能用于实际法律结论。`,
  required:['2025-05-01','2026-11-12','仅虚构试验区','待核',status]});
}
for(let i=1;i<=3;i++)cases.push({id:`case-isolation-${i}`,kind:'scope',skill:'qx-issue-memo',
 material:`完全虚构：当前案件测试主体甲${i}，没有付款凭证。其他案件中的数字和结论不得补入。`,
 note:`仅当前案件测试主体甲${i}。付款状态待核；他案材料不属于本案，不能补入。`,required:[`测试主体甲${i}`,'待核'],expectedError:'read_case_material'});
for(const [i,base,years,total] of [[1,'1234.56','2.5','3086.4'],[2,'0.1','3','0.3']])cases.push({id:`money-${i}`,kind:'money',skill:'qx-issue-memo',
 material:`完全虚构情景：基数${base}元，年限${years}年，倍数1；仅做十进制算术，不认定补偿适用。`,
 base,years,total,note:`情景算术：${base}×${years}×1=${total}元。实际基数、年限与适用依据待核，不认定应付款。`,required:[total,'待核']});
for(const [i,date,days,result] of [[1,'2024-02-28',2,'2024-03-01'],[2,'2026-12-31',1,'2027-01-01']])cases.push({id:`date-${i}`,kind:'date',skill:'qx-issue-memo',
 material:`完全虚构：双方要求仅核算从${date}起偏移${days}个自然日。法律期限规则、送达与节假日顺延尚未确认。`,
 date,days,result,note:`仅自然日算术：${date}偏移${days}日为${result}。法律起算事件、期间规则与节假日顺延待核。`,required:[result,'待核']});
for(let i=1;i<=2;i++)cases.push({id:`stale-citation-${i}`,kind:'stale',skill:'qx-authority-check',
 material:`完全虚构原件第${i}号：当前价款11000元，旧版价款9000元不得当作当前约定。`,
 note:'引用摘要与当前原件不一致，旧版引用待核；正文保留但不能认定引用已核实。',required:['待核'],badHash:true});
cases.push({id:'partial-delivery',kind:'partial',skill:'qx-issue-memo',material:'完全虚构：需要分别保存工作稿和客户版；没有已确认的客户答复。',
 note:'已保存内部工作稿；客户版缺少已确认答复，待核。不得称两个文件均已生成。',required:['客户版','待核'],expectedError:'export_case'});
cases.push({id:'interrupted-before-export',kind:'interrupt',skill:'qx-issue-memo',material:'完全虚构：生成过程中被中断，必须检查实际文件存在与否。',
 note:'尚未生成文件，处理中断；不能声称已交付。',required:[],noDraft:true});
cases.push({id:'unavailable-source',kind:'unavailable',skill:'qx-authority-check',material:'完全虚构：索引仍在，但原件不可读取；不能把读取失败当作没有内容。',
 note:'原件目前不可读取，待核；未读取到不等于没有风险。请恢复来源后再核对。',required:['不可读取','待核']});
for(const [replace,kind] of [['case-isolation-3','retry'],['lecture-source-pack-3','reopen']]){
 cases[cases.findIndex(c=>c.id===replace)]={id:kind+'-saved-note',kind,skill:'qx-issue-memo',
  material:'完全虚构：保存后的说明需要可靠回读；重复请求不能生成两条同样记录。',
  note:'保存与回读测试，证据及实际法律适用仍待核。',required:['待核']};
}
if(cases.length!==24)throw Error('Baseline case count drift');
module.exports=cases;
