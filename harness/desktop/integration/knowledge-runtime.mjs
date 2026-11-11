import {createHash} from 'node:crypto';
import {fail,text,id} from './knowledge-store.mjs';
import {attachmentReference} from './knowledge-materials.mjs';
export const digest=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const defaults={enabled:true,day:0,hour:20,maxCalls:100,summaryMode:'local'};
export function weekKey(now=Date.now(),{day=0,hour=20}={}){
  const date=new Date(now+8*3600000);const dayStart=Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),date.getUTCDate());
  let scheduled=dayStart-((date.getUTCDay()-day+7)%7)*86400000+hour*3600000;
  if(scheduled>now+8*3600000)scheduled-=7*86400000;
  return new Date(scheduled).toISOString().slice(0,10);
}
export function settings(store,patch){
  const old={...defaults,...store.setting('settings')};if(!patch)return old;
  if(Object.keys(patch).some(k=>!Object.hasOwn(defaults,k)))fail('设置字段无效');
  const next={...old,...patch};if(typeof next.enabled!=='boolean'||!Number.isInteger(next.day)||next.day<0||next.day>6||!Number.isInteger(next.hour)||next.hour<0||next.hour>23||!Number.isInteger(next.maxCalls)||next.maxCalls<1||next.maxCalls>1000)fail('整理时间或调用上限无效');
  if(!['local','model'].includes(next.summaryMode))fail('整理方式无效');
  store.setting('settings',next);return next;
}
export function cleanText(value){return value.replace(/\b(?:sk-|Bearer\s+)[A-Za-z0-9_\-]{16,}/gi,'[凭据已隐藏]').replace(/((?:api[_ -]?key|password|密码)\s*[:=：]\s*)[^\s，。;]+/gi,'$1[已隐藏]');}
export function eventText(event){
  const blocks=event.type==='user/message'?event.data?.content:event.type==='assistant/message'?event.data?.message?.content:[];
  return (Array.isArray(blocks)?blocks:[]).filter(b=>b.type==='text'&&typeof b.text==='string').map(b=>b.text).join('\n');
}
export function createSessionSource(ctx){
  const messageRows=list=>list.filter(r=>['user/message','assistant/message'].includes(r.type));
  async function metadata(session){const list=messageRows(await ctx.sessionQuery.listEvents(id(session)));return {records:list,version:digest(list)};}
  async function records(session,list){
    list??=await ctx.sessionQuery.listEvents(id(session));const result=[],checkpoints=new Map();
    async function isCheckpoint(seq){if(!checkpoints.has(seq)){const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq,before:0,after:0})).target;checkpoints.set(seq,event.type==='user/message'&&event.data?.source?.kind==='compact-checkpoint');}return checkpoints.get(seq);}
    for(const r of list){if(!['user/message','assistant/message'].includes(r.type))continue;
      if(r.type==='user/message'&&await isCheckpoint(r.seq))continue;
      if(r.surface==='current'){result.push(r);continue;}
      if(r.surface==='shadowed'&&ctx.sessionQuery.traceEvent){const trace=await ctx.sessionQuery.traceEvent({sessionId:session,seq:r.seq});
        if(trace.replacementChain?.length&&(await Promise.all(trace.replacementChain.map(isCheckpoint))).every(Boolean))result.push({...r,surface:'current'});
      }
    }return result;
  }
  return {
    metadata,
    async userTurn(session){const rows=(await metadata(session)).records.filter(r=>r.type==='user/message').reverse().slice(0,64);for(const row of rows){const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq:row.seq,before:0,after:0})).target;if(event.data?.source?.kind==='user')return row.seq;}return null;},
    list:async()=>(await ctx.sessionQuery.listSessions()).map(r=>({id:r.header.id,title:r.displayTitle||r.title||r.header.title})),
    title:async session=>(await ctx.sessionQuery.readTitleSnapshot?.(session))?.title?.title,
    async describe(session){const list=await ctx.sessionQuery.listEvents(id(session));const current=await records(session,list);
      const request=list.findLast(r=>r.type==='request/header');let route;
      if(request){const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq:request.seq,before:0,after:0})).target;const config=event.data?.config; if(config?.provider&&config?.model)route={provider:config.provider,model:config.model};}
      return {version:digest(messageRows(list)),records:current,rawRecords:messageRows(list),route};
    },
    async current(session){const list=await ctx.sessionQuery.listSessions();if(!list.some(r=>r.header.id===session))return null;return (await metadata(session)).version;},
    async materials(session,description){
      const result=[];for(const row of description.records){const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq:row.seq,before:0,after:0})).target;
        const blocks=event.type==='user/message'?event.data?.content:event.data?.message?.content;
        for(const block of Array.isArray(blocks)?blocks:[]){const attachment=['file','image'].includes(block.type)&&attachmentReference(block.attachment);if(attachment)result.push({seq:row.seq,attachment});}
      }return result;
    },
    materialPath(ref){return ref.mediaType?ctx.attachments?.imageHostPath?.(ref):ctx.attachments?.fileHostPath?.(ref);},
    async *messages(session,description){for(const row of description.records){const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq:row.seq,before:0,after:0})).target;
      const value=cleanText(eventText(event));if(value.trim())yield {seq:row.seq,role:event.type==='user/message'&&event.data?.source?.kind==='user'?'user':'assistant',text:value,offset:0};}},
    async read(session,seq,offset=0){const row=(await metadata(session)).records.find(r=>r.seq===seq);if(!row||!(await records(session,[row])).length)fail('该来源已被更正或移除',409);
      const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq,before:0,after:0})).target;const raw=cleanText(eventText(event));return {seq,offset,text:raw.slice(offset,offset+1600),next:offset+1600<raw.length?offset+1600:null};}
  };
}
export async function* splitMessages(messages,{chunkSize=6000,maxMessages=Infinity}={}){
  let batch=[];
  for await(const message of messages){for(let offset=0;offset<message.text.length;offset+=chunkSize){const part={...message,text:message.text.slice(offset,offset+chunkSize),offset:(message.offset||0)+offset};if(batch.length>=maxMessages||JSON.stringify([...batch,part]).length>24000){yield batch;batch=[];}batch.push(part);}}
  if(batch.length)yield batch;
}
export function validateExtraction(result,batch){
  if(typeof result==='string'){if(result.length>20000)fail('整理输出过长');result=JSON.parse(result.replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));}
  if(!Array.isArray(result?.items)||result.items.length>12)fail('模型未返回有效整理条目');
  return result.items.map(item=>{
    if(!['summary','decision','reflection','todo','rule','preference'].includes(item.kind))fail('模型返回未知知识类型');text(item.title,120);text(item.content,4000);
    if(!Array.isArray(item.sources)||!item.sources.length||item.sources.length>4)fail('模型未提供有效来源');
    const sources=item.sources.map(ref=>{text(ref.quote,400);const source=batch.find(m=>m.seq===ref.seq&&(ref.offset===undefined||m.offset===ref.offset)&&m.text.includes(ref.quote));if(!source)fail('引用未匹配原文');if(['rule','preference','decision'].includes(item.kind)&&source.role!=='user')fail('规则或决策缺少用户发言依据');return {seq:ref.seq,quote:ref.quote,offset:source.offset};});
    return {kind:item.kind,title:cleanText(item.title),content:cleanText(item.content),sources};
  });
}
export function localExtraction(batch){
  // Verbatim excerpts remain attributable records, never inferred facts or approved rules.
  return {items:batch.filter(m=>m.text.trim()).map(m=>({kind:'summary',
    title:(m.role==='user'?'用户交代：':'助手分析：')+m.text.replace(/\s+/g,' ').slice(0,48),
    content:(m.role==='user'?'用户原话（尚未核实）：\n':'助手分析（待核对）：\n')+m.text.slice(0,3600),
    sources:[{seq:m.seq,offset:m.offset,quote:m.text.slice(0,Math.min(200,m.text.length))}]})).slice(0,12)};
}
export class KnowledgeRunner{
  constructor({store,source,model,inheritFrom,now=()=>Date.now()}){Object.assign(this,{store,source,model,inheritFrom,now});this.running=null;this.controller=null;this.generation=0;this.sourceEpochs=new Map();}
  async ensureScope(session){
    const rows=await this.source.list(),row=rows.find(s=>s.id===session);if(!row)fail('该对话不存在',404);
    const scope=this.store.ensureSession(session,row),parent=this.inheritFrom?.(session);
    if(parent&&parent!==session&&rows.some(s=>s.id===parent)&&this.store.setting('automatic-scope:'+session)===scope){
      const target=this.store.ensureSession(parent,rows.find(s=>s.id===parent));
      if(target!==scope){this.store.bind(session,target);this.store.setting('automatic-scope:'+session,null);return target;}
    }
    return scope;
  }
  pause(){this.generation++;this.controller?.abort();}
  async verifySnapshot(session,version,epoch){
    if(await this.source.current(session)!==version||(this.sourceEpochs.get(session)||0)!==epoch)fail('资料来源正在更新，请稍后重试',409);
  }
  commitSnapshot(session,write){const result=write();this.sourceEpochs.set(session,(this.sourceEpochs.get(session)||0)+1);return result;}
  async describeSource(session){
    const epoch=this.sourceEpochs.get(session)||0,d=await this.source.describe(session);
    await this.verifySnapshot(session,d.version,epoch);
    const before=this.store.setting('source-meta:'+session);
    const prefix=before&&d.records.length>=before.length&&digest(d.records.slice(0,before.length))===digest(before);
    this.commitSnapshot(session,()=>{this.store.source(session,d.version,{preserve:!!prefix});this.store.setting('source-meta:'+session,d.records);if(d.rawRecords)this.store.setting('source-raw:'+session,d.rawRecords);});return d;
  }
  async syncMaterials(session,description){
    if(!this.source.materials)return;const d=description||await this.describeSource(session);
    if(this.store.setting('material-version:'+session)===d.version)return;
    const items=await this.source.materials(session,d);
    if(await this.source.current(session)!==d.version)fail('资料来源正在更新，请稍后重试',409);
    this.store.syncMaterials(session,d.version,items.filter(item=>d.records.some(r=>r.seq===item.seq)));
    this.store.setting('material-version:'+session,d.version);
  }
  async syncProjectMaterials(project,{foreground=false}={}){
    const live=new Set((await this.source.list()).map(s=>s.id));
    for(const session of this.store.sessionsForProject(project)){
      if(live.has(session)){
        if(foreground&&this.source.metadata&&(await this.source.metadata(session)).records.length>60){await this.fresh(session);continue;}
        await this.syncMaterials(session);
      }else this.store.missingSource(session);
    }
  }
  async reconcile(){
    const all=await this.source.list(),set=new Set(all.map(r=>r.id));
    for(const row of all){this.store.ensureSession(row.id,row);if(this.store.setting('source-unavailable:'+row.id))this.store.setting('source-unavailable:'+row.id,null);}
    for(const old of this.store.origins())if(!old.deleted&&!set.has(old.session))this.store.missingSource(old.session);
    return all;
  }
  async fresh(session){
    const epoch=this.sourceEpochs.get(session)||0;
    const old=this.store.db.prepare('SELECT * FROM origins WHERE session=?').get(session);if(!old||old.deleted)return false;
    const version=await this.source.current(session);if((this.sourceEpochs.get(session)||0)!==epoch)fail('资料来源正在更新，请稍后重试',409);if(version===old.version){this.store.setting('source-unavailable:'+session,null);return true;}
    if(version===null){await this.verifySnapshot(session,null,epoch);this.commitSnapshot(session,()=>this.store.missingSource(session));return false;}
    if(this.source.metadata){const raw=await this.source.metadata(session),before=this.store.setting('source-raw:'+session);
      if(before&&raw.records.length>=before.length&&digest(raw.records.slice(0,before.length))===digest(before)){await this.verifySnapshot(session,raw.version,epoch);this.commitSnapshot(session,()=>{this.store.source(session,raw.version,{preserve:true});this.store.setting('source-raw:'+session,raw.records);});return true;}
      // Compaction and legacy metadata can change raw rows without changing effective source text.
    }
    const d=await this.source.describe(session),before=this.store.setting('source-meta:'+session);
    await this.verifySnapshot(session,d.version,epoch);
    if(before&&d.records.length>=before.length&&digest(d.records.slice(0,before.length))===digest(before)){
      this.commitSnapshot(session,()=>{this.store.source(session,d.version,{preserve:true});this.store.setting('source-meta:'+session,d.records);if(d.rawRecords)this.store.setting('source-raw:'+session,d.rawRecords);});return true;
    }
    this.commitSnapshot(session,()=>this.store.invalidate(session,false));return false;
  }
  async tick(){const opts=settings(this.store);const last=this.store.setting('lastAttempt')||0;if(!opts.enabled||this.running||this.now()-last<3600000||this.store.setting('completedWeek')===weekKey(this.now(),opts))return;return this.run();}
  async tickIncremental(){
    if(!settings(this.store).enabled||this.running||this.now()-(this.store.setting('lastIncremental')||0)<60000)return;
    this.store.setting('lastIncremental',this.now());return this.run({incremental:true});
  }
  run({incremental=false,sessionId}={}){
    if(this.running){if(!sessionId)return this.running;const generation=this.generation;return this.running.then(result=>generation===this.generation?this.run({incremental,sessionId}):result);}
    this.controller=new AbortController();this.running=this.execute(this.controller.signal,incremental,sessionId).finally(()=>{this.running=null;this.controller=null;});return this.running;
  }
  async execute(signal,incremental=false,sessionId){
    const opts=settings(this.store),week=weekKey(this.now(),opts),report={state:'running',started:this.now(),completed:0,skipped:0,failed:0,pending:0,calls:0,errors:[],usage:[]};
    let budget=this.store.setting('budget');if(budget?.week!==week)budget={week,calls:0};
    report.mode=incremental?'incremental':'weekly';
    if(!incremental)this.store.setting('lastAttempt',this.now());this.store.setting('report',report);
    try{
      const sessions=await this.reconcile();
      const all=sessionId?sessions.filter(s=>s.id===sessionId):sessions;report.pending=all.length;
      for(const {id:session} of all){signal.throwIfAborted();
        if(incremental&&this.now()<(this.store.setting('source-retry:'+session)||0))continue;
        try{
          const bound=await this.ensureScope(session);
          const d=await this.describeSource(session);await this.syncMaterials(session,d);
          if(this.source.title)this.store.ensureSession(session,{title:await this.source.title(session)});
          const progress=this.store.setting('source-progress:'+session),messages=this.source.messages(session,d);
          async function* unread(){for await(const m of messages){if(progress&&m.seq<progress.seq)continue;if(progress&&m.seq===progress.seq){if(m.text.length<=progress.offset)continue;yield {...m,text:m.text.slice(progress.offset),offset:progress.offset};}else yield m;}}
          for await(const batch of splitMessages(unread(),opts.summaryMode==='local'?{chunkSize:3200,maxMessages:12}:{})){
            signal.throwIfAborted();const key=digest(batch);if(this.store.hasBatch(session,key)){report.skipped++;continue;}
            let output;
            if(opts.summaryMode==='model'){
              if(budget.calls>=opts.maxCalls){report.state='budget';this.store.setting('report',report);return report;}
              budget.calls++;report.calls++;this.store.setting('budget',budget);
              output=await this.model({batch,route:d.route,session,signal});
            }else output=localExtraction(batch);
            const items=validateExtraction(output,batch);signal.throwIfAborted();
            if(await this.source.current(session)!==d.version||this.store.binding(session)!==bound)fail('整理期间来源或项目发生变化，本批未保存',409);
            const last=batch.at(-1);this.store.upsertBatch(session,d.version,key,items,{seq:last.seq,offset:last.offset+last.text.length});
            report.completed++;if(output?.usage)report.usage.push(output.usage);this.store.setting('report',report);
          }
          this.store.setting('source-retry:'+session,null);report.pending--;
        }catch(error){if(signal.aborted)throw error;this.store.setting('source-retry:'+session,this.now()+3600000);report.failed++;report.errors.push({session,message:error.status?error.message:'该对话整理未完成，一小时后自动重试；也可检查模型配置后点击立即整理。'});report.errors=report.errors.slice(-20);}
      }
      report.state=report.pending?'partial':'complete';if(!report.failed&&!incremental)this.store.setting('completedWeek',week);
    }catch(error){report.state=signal.aborted?'paused':'failed';if(!signal.aborted)report.errors.push({message:'会话读取服务暂不可用，请稍后重试。'});}
    report.finished=this.now();this.store.setting('report',report);return report;
  }
}
