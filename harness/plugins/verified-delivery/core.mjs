import {readFile,realpath} from 'node:fs/promises';
import {isAbsolute,relative,resolve,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';

const protectedNames=new Set(['build_source_bound_litigation','assess_employment_termination','save_source_bound_register']);
const hash=value=>createHash('sha256').update(value).digest('hex');
const failure='未能确认本轮保存成果与当前文档一致。请回读当前案件记录和文件后重试；本次不交付未经核对的模型解释。';
const prefix='mcp__qx_legal__';
const deliveryKey=({name,args})=>JSON.stringify([args.case_id,name,
 name==='save_source_bound_register'?args.domain||'':name==='build_source_bound_litigation'?args.document_type||'':'']);
function unpack(message){
 if(message.isError)return null;
 try{
  let value=JSON.parse(message.content.filter(b=>b.type==='text').map(b=>b.text).join('\n'));
  for(let i=0;i<3;i++){
   if(value?.isError)return null;
   if(value?.structuredContent){value=value.structuredContent;continue;}
   if(Array.isArray(value?.content)){value=JSON.parse(value.content.filter(b=>b.type==='text').map(b=>b.text).join('\n'));continue;}
   return value;
  }
  return value;
 }catch{return null;}
}
export function deliveriesInTurn(messages){
 const start=messages.findLastIndex(m=>m.role==='user'&&(!m.source||m.source.kind==='user'));
 if(start<0)return null;
 const calls=new Map(),results=new Map(),exports=[];
 for(const message of messages.slice(start+1)){
  if(message.role==='assistant')for(const block of message.content||[]){
   if(block.type!=='tool-call'||!block.name.startsWith(prefix))continue;
   let args;try{args=JSON.parse(block.arguments);}catch{args={};}
   const name=block.name.slice(prefix.length);calls.set(block.id,{name,args});
   if(protectedNames.has(name))results.set(deliveryKey({name,args}),{call:{name,args},value:null});
  }
  if(message.role!=='tool')continue;
  const call=calls.get(message.toolCallId);
  if(!call)continue;
  const value=unpack(message);
  if(protectedNames.has(call.name))results.set(deliveryKey(call),{call,value});
  if(call.name==='export_case')exports.push({call,value});
 }
 return results.size?{results:[...results.values()],exports}:null;
}
async function safeFile(root,path){
 if(typeof path!=='string'||path.includes('\0'))throw Error('invalid path');
 const full=await realpath(isAbsolute(path)?path:resolve(root,path));
 const rel=relative(root,full);
 if(!rel||rel==='..'||rel.startsWith('..'+sep)||isAbsolute(rel))throw Error('outside workspace');
 return full;
}
async function checkFile(root,file){
 if(!/^[a-f0-9]{64}$/.test(file?.sha256||''))throw Error('missing digest');
 const path=await safeFile(root,file.path);
 if(hash(await readFile(path))!==file.sha256)throw Error('file changed');
 return path;
}
export async function canonicalDelivery(state,workspace){
 let db;
 try{
  const root=await realpath(workspace);
  db=new DatabaseSync(await safeFile(root,'.qx-materials/index.sqlite'),{readOnly:true});
  const sections=[];
  for(const {call,value} of state.results){
   const d=value?.delivery;
   if(value?.recorded===false||value?.saved===false||!d||d.version!==1||d.case_id!==call.args.case_id||
      typeof d.summary!=='string'||!d.summary.trim()||d.summary.length>200000||
      !Array.isArray(d.notes)||!Array.isArray(d.sources)||!Array.isArray(d.documents))throw Error('invalid receipt');
   if(!db.prepare('SELECT 1 FROM legal_cases WHERE id=?').get(d.case_id))throw Error('unknown case');
   for(const n of d.notes){
    const row=db.prepare('SELECT content FROM legal_notes WHERE case_id=? AND id=?').get(d.case_id,n.id);
    if(!row||hash(row.content)!==n.sha256||db.prepare('SELECT 1 FROM legal_notes WHERE case_id=? AND supersedes=?').get(d.case_id,n.id))throw Error('record changed');
   }
   for(const s of d.sources){
    const row=db.prepare('SELECT sha256 FROM legal_material_links WHERE case_id=? AND path=? ORDER BY version DESC LIMIT 1').get(d.case_id,s.path);
    if(!row||row.sha256!==s.sha256)throw Error('source relinked');
    await checkFile(root,s);
   }
   const docs=[...d.documents];
   const lastExport=d.notes.length?state.exports.findLast(({call:c})=>c.args.case_id===d.case_id&&
    (!Array.isArray(c.args.note_ids)||d.notes.some(n=>c.args.note_ids.includes(n.id)))):undefined;
   if(lastExport&&!lastExport.value)throw Error('last export failed');
   // A combined export may contain other current protected records, never unchecked additions.
   const allowed=state.results.filter(r=>r.value?.delivery?.case_id===d.case_id).flatMap(r=>r.value.delivery.notes||[]);
   const v=lastExport?.value;
   const last=v?.case_id===d.case_id&&v.audience==='internal'&&Array.isArray(v.note_versions)&&
    v.note_versions.length>0&&new Set(v.note_versions.map(n=>n.id)).size===v.note_versions.length&&
    v.note_versions.every(n=>allowed.some(x=>x.id===n.id&&x.sha256===n.sha256))&&
    d.notes.every(n=>v.note_versions.some(x=>x.id===n.id&&x.sha256===n.sha256))?lastExport:undefined;
   if(last)docs.push({...last.value,label:'已保存记录的 Word'});
   const links=[];
   for(const doc of docs){
    const path=await checkFile(root,doc);
    if(!path.toLowerCase().endsWith('.docx'))throw Error('unexpected artifact');
    const label=doc.label==='内部核对稿（勿外发）'?doc.label:doc.label==='已保存记录的 Word'?doc.label:'文稿';
    links.push(`[${label}](<${encodeURI(path.replaceAll('\\','/')).replaceAll('#','%23').replaceAll('?','%3F').replaceAll('>','%3E')}>)`);
   }
   sections.push(d.summary+'\n\n'+(links.length?links.join('\n\n'):'尚无本轮匹配的 Word 文件；已保存记录可在本案工作区查看。'));
  }
  return '以下说明由已保存成果生成；具体审查内容见对应文档。\n\n'+sections.join('\n\n');
 }catch{return failure;}finally{db?.close();}
}
function* textChunks(text){
 yield {type:'block-start',index:0,blockType:'text'};
 yield {type:'text-delta',index:0,text};
 yield {type:'block-end',index:0,block:{type:'text',text}};
}
export async function* guardStream(options,next,workspace){
 const state=deliveriesInTurn(options.messages);
 if(!state){yield* next();return;}
 // Buffer before any visible text or replay metadata reaches the session log.
 const chunks=[];let bytes=0;
 for await(const chunk of next()){
  options.signal?.throwIfAborted();bytes+=Buffer.byteLength(JSON.stringify(chunk));
  if(bytes>4*1024*1024)throw Error('受约束交付超过处理上限，未展示未核对解释。');
  chunks.push(chunk);
 }
 options.signal?.throwIfAborted();
 const finish=chunks.findLast(c=>c.type==='finish');
 if(!finish)throw Error('受约束交付未完整结束。');
 if(['error','aborted','max-tokens'].includes(finish.reason.kind)){
  for(const c of chunks)if(c.type==='usage')yield c;
  yield {type:'finish',reason:finish.reason};return;
 }
 const hasTools=chunks.some(c=>c.type==='tool-call-delta'||c.block?.type==='tool-call');
 if(hasTools){
  const textIndexes=new Set(chunks.filter(c=>c.type==='text-delta'||c.blockType==='text'||c.block?.type==='text').map(c=>c.index));
  for(const c of chunks)if(c.type!=='finish'&&!textIndexes.has(c.index))yield c;
 }else{
  const text=await canonicalDelivery(state,workspace);options.signal?.throwIfAborted();yield* textChunks(text);
  for(const c of chunks)if(c.type==='usage')yield c;
 }
 // Provider replay state describes discarded prose and must not reintroduce it.
 yield {type:'finish',reason:finish.reason};
}
