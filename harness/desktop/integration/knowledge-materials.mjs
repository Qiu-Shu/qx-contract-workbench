export function materialCategory(name=''){
  if(/合同|协议|contract|agreement/i.test(name))return '合同与协议';
  if(/判决|裁定|起诉|答辩|诉状|庭审/.test(name))return '诉讼文书';
  if(/证据|票据|发票|流水|收据/.test(name))return '证据材料';
  if(/范本|模板|template/i.test(name))return '范本与模板';
  if(/纪要|记录|笔记/.test(name))return '沟通与记录';
  return '工作资料';
}
export function attachmentReference(value){
  if(value?.mediaType?.startsWith('image/')){
    if(!['image/png','image/jpeg','image/webp','image/gif'].includes(value.mediaType)||!/^sha256:[a-f0-9]{64}$/.test(value.attachmentId||'')||!Number.isSafeInteger(value.bytes)||value.bytes<0||![value.width,value.height].every(n=>Number.isSafeInteger(n)&&n>0))return null;
    const name=typeof value.name==='string'&&value.name&&!/[\\/:*?"<>|\x00-\x1f]/.test(value.name)?value.name.slice(0,255):'图片 · '+value.attachmentId.slice(7,15);
    return {attachmentId:value.attachmentId,name,bytes:value.bytes,mediaType:value.mediaType,width:value.width,height:value.height};
  }
  if(!value||typeof value!=='object'||!/^sha256:[a-f0-9]{64}$/.test(value.attachmentId||'')||
    typeof value.name!=='string'||!value.name||value.name.length>255||/[\\/:*?"<>|\x00-\x1f]/.test(value.name)||
    value.name==='.'||value.name==='..'||/[. ]$/.test(value.name)||!Number.isSafeInteger(value.bytes)||value.bytes<0)return null;
  return {attachmentId:value.attachmentId,name:value.name,bytes:value.bytes};
}
