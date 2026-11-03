/** Local burst collection: accept durably first, run one model turn at a time. */
import {randomUUID} from 'node:crypto';

export function messageControl(text='') {
  const clauses=String(text).split(/[，,。.!！?？；;\n]/).map(s=>s.replace(/\s/g,''));
  const hold=/^(?:我|我们|材料|附件)?(?:还没发完|尚未发完|没有发完|没发完|先别处理|先不要处理|先别开始|先不要开始|不要开始|暂不开始|请等待|请稍等|稍等|等一下|先等等)$/;
  if(clauses.some(s=>hold.test(s)))return 'hold';
  if(/[?？]/.test(text))return null;
  const release=/^(?:我|我们|材料|附件)?(?:已经|已|现在)?(?:发完了|发送完毕|就这些|可以开始(?:了|处理|审查)?|请开始(?:处理|审查)?|开始处理|开始审查)$/;
  return clauses.some(s=>release.test(s))?'release':null;
}

export class MessageCoalescer {
  constructor({process,persist,state,now=Date.now,setTimer=setTimeout,clearTimer=clearTimeout,onError=()=>{},quietMs=8000,mediaQuietMs=12000}) {
    this.process=process;this.persist=persist;this.now=now;this.setTimer=setTimer;this.clearTimer=clearTimer;this.onError=onError;
    this.quietMs=quietMs;this.mediaQuietMs=mediaQuietMs;
    this.state=state??{version:1,pending:[],active:null,history:[],failed:[]};
    this.serial=Promise.resolve();this.task=Promise.resolve();this.paused=true;this.receiving=0;this.timer=null;
  }
  async change(fn) {
    const operation=this.serial.then(async()=>{
      const before=structuredClone(this.state);
      try{const result=fn();await this.persist(this.state);return result;}catch(error){this.state=before;throw error;}
    });
    this.serial=operation.catch(()=>{});return operation;
  }
  async recover() {
    if(this.state.version!==1||!Array.isArray(this.state.pending)||!Array.isArray(this.state.failed)||!Array.isArray(this.state.history))throw Error('微信待处理记录格式异常，原记录已保留');
    if(this.state.active)await this.change(()=>{
      this.state.failed.push({...this.state.active,status:'interrupted',error:'上次处理在重启前尚未确认完成，不自动重发；请在工作台查看。'});this.state.active=null;
    });
  }
  has(id) {
    return [this.state.active,...this.state.pending,...this.state.failed,...this.state.history].filter(Boolean)
      .some(b=>(b.items??[]).some(item=>item.id===id)||(b.messageIds??[]).includes(id));
  }
  async add(item) {
    const accepted=await this.change(()=>{
      if(this.has(item.id))return false;
      let batch=this.state.pending.at(-1);
      if(!batch||batch.key!==item.key||batch.ready){batch={id:randomUUID(),key:item.key,sessionId:item.sessionId,accountId:item.accountId,items:[],firstAt:this.now(),dueAt:this.now(),held:false};this.state.pending.push(batch);}
      batch.items.push(item);
      const control=messageControl(item.text);
      if(control==='hold')batch.held=true;
      if(control==='release'){batch.held=false;batch.ready=true;}
      const hasMedia=batch.items.some(i=>i.hasMedia);
      batch.dueAt=control==='release'?this.now():this.now()+(hasMedia?this.mediaQuietMs:this.quietMs);
      return true;
    });
    this.schedule();return accepted;
  }
  beginReceive(){this.receiving++;this.cancelTimer();}
  endReceive(){this.receiving=Math.max(0,this.receiving-1);this.schedule();}
  pause(){this.paused=true;this.cancelTimer();}
  resume(){this.paused=false;this.schedule();}
  cancelTimer(){if(this.timer!==null)this.clearTimer(this.timer);this.timer=null;}
  schedule() {
    this.cancelTimer();const batch=this.state.pending[0];
    if(this.paused||this.receiving||this.state.active||!batch||batch.held)return;
    this.timer=this.setTimer(()=>this.flush().catch(this.onError),Math.max(0,batch.dueAt-this.now()));
  }
  async flush() {
    const batch=await this.change(()=>{
      const head=this.state.pending[0];
      if(this.paused||this.receiving||this.state.active||!head||head.held||head.dueAt>this.now())return null;
      this.state.active={...this.state.pending.shift(),status:'dispatched',startedAt:this.now()};return this.state.active;
    });
    if(!batch){this.schedule();return;}
    // Never await the model in the receive path; new messages keep their own quiet window.
    this.task=(async()=>{
      let error;try{await this.process(batch);}catch(cause){error=String(cause.message??cause);}
      await this.change(()=>{
        if(error)this.state.failed.push({...batch,status:'failed',error});
        this.state.history=[...this.state.history.slice(-99),{id:batch.id,status:error?'failed':'completed',sessionId:batch.sessionId,messageIds:batch.items.map(i=>i.id),warningCount:batch.items.filter(i=>i.error).length,finishedAt:this.now(),...(error?{error}:{})}];
        this.state.active=null;
      });
    })().catch(this.onError).finally(()=>this.schedule());
  }
  async idle(){await this.task;await this.serial;}
  snapshot(){return{active:Boolean(this.state.active),pendingMessages:this.state.pending.reduce((n,b)=>n+b.items.length,0),held:this.state.pending.some(b=>b.held),failed:this.state.failed.length,lastBatch:this.state.history.at(-1)??null};}
}
