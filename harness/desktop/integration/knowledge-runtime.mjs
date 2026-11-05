import {createHash} from 'node:crypto';
import {fail,text,id} from './knowledge-store.mjs';
export const digest=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const defaults={enabled:true,day:0,hour:20,maxCalls:100};
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
  store.setting('settings',next);return next;
}
export function cleanText(value){return value.replace(/\b(?:sk-|Bearer\s+)[A-Za-z0-9_\-]{16,}/gi,'[凭据已隐藏]').replace(/((?:api[_ -]?key|password|密码)\s*[:=：]\s*)[^\s，。;]+/gi,'$1[已隐藏]');}
export function eventText(event){
  const blocks=event.type==='user/message'?event.data?.content:event.type==='assistant/message'?event.data?.message?.content:[];
  return (Array.isArray(blocks)?blocks:[]).filter(b=>b.type==='text'&&typeof b.text==='string').map(b=>b.text).join('\n');
}
export function createSessionSource(ctx){
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
    list:async()=>(await ctx.sessionQuery.listSessions()).map(r=>({id:r.header.id})),
    async describe(session){const list=await ctx.sessionQuery.listEvents(id(session));const current=await records(session,list);
      const request=list.findLast(r=>r.type==='request/header');let route;
      if(request){const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq:request.seq,before:0,after:0})).target;const config=event.data?.config; if(config?.provider&&config?.model)route={provider:config.provider,model:config.model};}
      return {version:digest(current),records:current,route};
    },
    async current(session){const list=await ctx.sessionQuery.listSessions();if(!list.some(r=>r.header.id===session))return null;return digest(await records(session));},
    async *messages(session,description){for(const row of description.records){const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq:row.seq,before:0,after:0})).target;
      const value=cleanText(eventText(event));if(value.trim())yield {seq:row.seq,role:event.type==='user/message'&&event.data?.source?.kind==='user'?'user':'assistant',text:value,offset:0};}},
    async read(session,seq,offset=0){const metadata=await records(session);if(!metadata.some(r=>r.seq===seq))fail('该来源已被更正或移除',409);
      const event=(await ctx.sessionQuery.readEvent({sessionId:session,seq,before:0,after:0})).target;const raw=cleanText(eventText(event));return {seq,offset,text:raw.slice(offset,offset+1600),next:offset+1600<raw.length?offset+1600:null};}
  };
}
export async function* splitMessages(messages){
  let batch=[];
  for await(const message of messages){for(let offset=0;offset<message.text.length;offset+=6000){const part={...message,text:message.text.slice(offset,offset+6000),offset:(message.offset||0)+offset};if(JSON.stringify([...batch,part]).length>24000){yield batch;batch=[];}batch.push(part);}}
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
export class KnowledgeRunner{
  constructor({store,source,model,now=()=>Date.now()}){Object.assign(this,{store,source,model,now});this.running=null;this.controller=null;}
  pause(){this.controller?.abort();}
  async reconcile(){const all=await this.source.list();const set=new Set(all.map(r=>r.id));for(const old of this.store.origins())if(!old.deleted&&!set.has(old.session))this.store.invalidate(old.session,true);return all;}
  async fresh(session){
    const old=this.store.db.prepare('SELECT * FROM origins WHERE session=?').get(session);if(!old||old.deleted)return false;
    const version=await this.source.current(session);if(version===old.version)return true;
    if(version===null){this.store.invalidate(session,true);return false;}
    const d=await this.source.describe(session),before=this.store.setting('source-meta:'+session);
    if(before&&d.records.length>=before.length&&digest(d.records.slice(0,before.length))===digest(before)){
      this.store.source(session,d.version,{preserve:true});this.store.setting('source-meta:'+session,d.records);return true;
    }
    this.store.invalidate(session,false);return false;
  }
  async tick(){const opts=settings(this.store);const last=this.store.setting('lastAttempt')||0;if(!opts.enabled||this.running||this.now()-last<3600000||this.store.setting('completedWeek')===weekKey(this.now(),opts))return;return this.run();}
  run(){if(this.running)return this.running;this.controller=new AbortController();this.running=this.execute(this.controller.signal).finally(()=>{this.running=null;this.controller=null;});return this.running;}
  async execute(signal){
    const opts=settings(this.store),week=weekKey(this.now(),opts),report={state:'running',started:this.now(),completed:0,skipped:0,failed:0,pending:0,calls:0,errors:[],usage:[]};
    let budget=this.store.setting('budget');if(budget?.week!==week)budget={week,calls:0};
    this.store.setting('lastAttempt',this.now());this.store.setting('report',report);
    try{
      const all=await this.reconcile();report.pending=all.length;
      for(const {id:session} of all){signal.throwIfAborted();
        try{
          const d=await this.source.describe(session);const before=this.store.setting('source-meta:'+session);
          const prefix=before&&d.records.length>=before.length&&digest(d.records.slice(0,before.length))===digest(before);
          this.store.source(session,d.version,{preserve:!!prefix});this.store.setting('source-meta:'+session,d.records);
          const bound=this.store.binding(session);
          const progress=this.store.setting('source-progress:'+session),messages=this.source.messages(session,d);
          async function* unread(){for await(const m of messages){if(progress&&m.seq<progress.seq)continue;if(progress&&m.seq===progress.seq){if(m.text.length<=progress.offset)continue;yield {...m,text:m.text.slice(progress.offset),offset:progress.offset};}else yield m;}}
          for await(const batch of splitMessages(unread())){
            signal.throwIfAborted();const key=digest(batch);if(this.store.hasBatch(session,key)){report.skipped++;continue;}
            if(budget.calls>=opts.maxCalls){report.state='budget';this.store.setting('report',report);return report;}
            budget.calls++;report.calls++;this.store.setting('budget',budget);
            const output=await this.model({batch,route:d.route,session,signal});
            const items=validateExtraction(output,batch);signal.throwIfAborted();
            if(await this.source.current(session)!==d.version||this.store.binding(session)!==bound)fail('整理期间来源或项目发生变化，本批未保存',409);
            const last=batch.at(-1);this.store.upsertBatch(session,d.version,key,items,{seq:last.seq,offset:last.offset+last.text.length});
            report.completed++;if(output?.usage)report.usage.push(output.usage);this.store.setting('report',report);
          }
          report.pending--;
        }catch(error){if(signal.aborted)throw error;report.failed++;report.errors.push({session,message:error.status?error.message:'该对话整理未完成，请检查模型配置后重试。'});report.errors=report.errors.slice(-20);}
      }
      report.state=report.failed?'partial':'complete';if(!report.failed)this.store.setting('completedWeek',week);
    }catch(error){report.state=signal.aborted?'paused':'failed';if(!signal.aborted)report.errors.push({message:'会话读取服务暂不可用，请稍后重试。'});}
    report.finished=this.now();this.store.setting('report',report);return report;
  }
}
