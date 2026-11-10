import {fail,id,text} from './knowledge-store.mjs';
export const isCaseId=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
export function unpackKnowledgeResult(value){
  for(let n=0;n<6;n++){
    if(!value||typeof value!=='object'||value.isError||value.error)return;
    if(Object.hasOwn(value,'value')){value=value.value;continue;}
    if(value.structuredContent){value=value.structuredContent;continue;}
    if(!Array.isArray(value.content))return value;
    try{value=JSON.parse(value.content.filter(b=>b.type==='text').map(b=>b.text).join('\n'));}catch{return;}
  }
}
// Case storage owns its records, revision checks and synchronization. No paths or database access cross this interface.
export function createMemoryAccess({store,read,manage}){
  const catalogs=new Map();
  const item=(m,project)=>({id:'memory-'+m.id,project,kind:'case_memory',title:m.content.slice(0,36),content:m.content,revision:m.revision,state:m.kind==='manual'?'manual_confirmed':'saved',sourceLabel:String(m.source?.label||'').slice(0,1000),sourceNote:m.source_note_id||m.source?.note_id||'',recordKind:m.kind,updated:Date.parse(m.updated_at)||0,notice:'案件记忆是办案提示，不是独立证据；引用前核对来源。'});
  async function rows(project,{query,offset=0,memoryId}={}){
    store.getProject(project);if(!isCaseId(project))return {available:true,items:[],next:null};
    try{
      const r=await read(memoryId?'read':query?'recall':'list',{case_id:project,...memoryId?{memory_id:id(memoryId)}:query?{query:text(query,300)}:{offset:Number(offset)}});
      if(!r)return {available:false,items:[],notice:'案件记忆暂未连接，工作记录仍可使用。'};
      if(r.enabled===false)return {available:true,enabled:false,items:[],notice:'本案记忆已暂停，可在管理中查看和调整。'};
      const seen=new Set(),result=[];
      for(const m of memoryId?[r]:(r.matches||r.memories||[])){
        if(!m.id||typeof m.content!=='string'||m.source_stale||m.case_id!==project)continue;
        const key=m.source_note_id?JSON.stringify([m.case_id,m.source_note_id,m.revision,m.source_hash||m.source?.sha256||'',m.content]):m.id;
        if(seen.has(key))continue;seen.add(key);result.push({...item(m,project),content:memoryId?m.content:m.content.slice(0,800),...(memoryId?{sourceText:String(m.source?.snapshot||'')}: {})});
      }return {available:true,enabled:true,items:result,next:r.next_offset??null};
    }catch{return {available:false,items:[],notice:'案件记忆暂不可用，工作记录仍可使用。请稍后重试。'};}
  }
  async function catalog(offset=0,query=''){
    const args={offset:Number(offset),query:String(query).slice(0,300),limit:50},key=JSON.stringify(args),cached=catalogs.get(key);
    if(cached&&Date.now()-cached.at<30000)return cached.value;
    try{const r=await manage('list_cases',args);const value={items:(r?.cases||[]).filter(c=>isCaseId(c.id)).map(c=>({id:c.id,title:String(c.title).slice(0,120)})),next:r?.next_offset??null};catalogs.set(key,{at:Date.now(),value});if(catalogs.size>16)catalogs.delete(catalogs.keys().next().value);return value;}
    catch{return {items:[],next:null,notice:'已有案件暂不可用，当前工作仍可使用。'};}
  }
  async function ensureCase(caseId,title){
    if(!isCaseId(caseId))fail('案件编号无效');const state=await manage('status',{case_id:caseId});
    if(state?.case_id!==caseId)fail('案件不存在或暂不可用',409);
    catalogs.clear();
    if(!store.db.prepare('SELECT 1 FROM projects WHERE id=?').get(caseId))store.project({id:caseId,title:text(title,120)});
    return store.getProject(caseId);
  }
  async function update(project,memoryId,revision,content){
    if(!isCaseId(project))fail('当前工作尚未关联案件');store.getProject(project);
    const before=await rows(project,{memoryId});if(!before.items.length)fail('记忆已停用、删除或来源失效，请刷新',409);
    if(before.items[0].revision!==revision)fail('记忆已更新，请刷新后重试',409);
    await manage('update',{case_id:project,memory_id:id(memoryId),revision,content:text(content,16000)});
    const after=await rows(project,{memoryId});if(!after.items.length)fail('记忆已保存，请刷新核对当前状态',409);const {sourceText,...updated}=after.items[0];return updated;
  }
  return {rows,catalog,ensureCase,update};
}
