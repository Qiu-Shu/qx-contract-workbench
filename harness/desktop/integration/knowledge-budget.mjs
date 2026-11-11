import {createHash} from 'node:crypto';
export const knowledgeLimits=Object.freeze({start:4096,recall:6144,read:4096,turn:16384});
export const jsonBytes=value=>Buffer.byteLength(JSON.stringify(value),'utf8');
export function clipUtf8(value,limit){
  const text=String(value??'');if(Buffer.byteLength(text,'utf8')<=limit)return text;
  let result='',bytes=0;for(const character of text){const size=Buffer.byteLength(character,'utf8');if(bytes+size>limit)break;result+=character;bytes+=size;}return result;
}
export function takeKnowledge(budget,value,limit=knowledgeLimits.read){
  const output=JSON.stringify(value),bytes=Buffer.byteLength(output,'utf8');
  if(bytes>limit)throw Object.assign(Error('本次结果超过分层读取上限，请缩小关键词或按片段读取。'),{status:413});
  const key=createHash('sha256').update(output).digest('hex');budget.delivered??=new Set();
  if(budget.delivered.has(key))return JSON.stringify({alreadyReturned:true,notice:'这些片段已在本轮返回，请复用已有结果；需要更多内容时按下一位置读取。'});
  if(budget.used+bytes>knowledgeLimits.turn)throw Object.assign(Error('本轮知识片段已达到 16 KiB 上限，请先使用已返回内容；后续轮次可继续按位置读取。'),{status:413});
  budget.used+=bytes;budget.delivered.add(key);return output;
}
export function knowledgeIndex(entry){return {id:entry.id,kind:entry.kind,title:clipUtf8(entry.title,150),state:entry.state,revision:entry.revision,...entry.sourceStatus==='unavailable'?{sourceStatus:'unavailable',sourceNotice:'来源对话未迁入，保存正文已保留；原文暂不可追溯。'}:{}};}
export function knowledgeMatch(entry){return {...knowledgeIndex(entry),...entry.content?{content:clipUtf8(entry.content,420),hasMore:Buffer.byteLength(entry.content,'utf8')>420}:{},...entry.category?{category:entry.category,versions:entry.versions}:{}};}
