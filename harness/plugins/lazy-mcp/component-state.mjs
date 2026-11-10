import {resolveOptionalComponent,describeComponent} from './components.mjs';

export function createComponentManager({config,resolve=resolveOptionalComponent,describe=describeComponent}){
  let state={id:'windows-python',label:'Windows 高级自动化',selected:true,phase:'idle',mode:'checking',transferred:0,total:0,attempt:0},active,disposed=false;
  const read=()=>({...state,busy:Boolean(active)});
  const status=async()=>{
    if(state.mode==='checking'){
      const description=await describe(config);
      if(state.mode==='checking')state={...state,...description,...(active?{phase:state.phase}:{})};
    }
    return read();
  };
  async function prepare({signal}={}){
    signal?.throwIfAborted();if(disposed)throw Error('组件服务已关闭。');
    if(!active){
      const operation={controller:new AbortController(),waiters:0};active=operation;
      state={...state,phase:'checking',transferred:0,error:'',code:'',attempt:state.attempt+1,startedAt:Date.now()};
      operation.promise=(async()=>{
        try{
          await status();operation.controller.signal.throwIfAborted();
          const result=await resolve(config,{signal:operation.controller.signal,onProgress:progress=>{
            if(operation.controller.signal.aborted)return;
            if(['checking','connecting','downloading','verifying','installing'].includes(progress.phase)){
              state={...state,phase:progress.phase};
              if(Number.isSafeInteger(progress.total)&&progress.total>0)state.total=progress.total;
              if(Number.isSafeInteger(progress.transferred)&&progress.transferred>=0)state.transferred=Math.min(progress.transferred,state.total);
            }
          }});
          operation.controller.signal.throwIfAborted();state={...state,phase:'ready',error:'',code:''};return result;
        }catch(error){
          state={...state,phase:operation.controller.signal.aborted?'cancelled':'error',
            error:operation.controller.signal.aborted?'准备已取消，可稍后重新下载。':error.message,
            code:operation.controller.signal.aborted?'CANCELLED':error.code||'PREPARE_FAILED'};throw error;
        }finally{if(active===operation)active=null}
      })();
    }
    const operation=active;operation.waiters++;let abort;
    try{
      if(!signal)return await operation.promise;
      return await Promise.race([operation.promise,new Promise((_,reject)=>{
        abort=()=>reject(signal.reason);signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort();
      })]);
    }finally{
      if(abort)signal.removeEventListener('abort',abort);
      operation.waiters--;if(!operation.waiters&&active===operation)cancel();
    }
  }
  function cancel(){if(active){state={...state,phase:'cancelling'};active.controller.abort()}}
  return {read,status,prepare,cancel,async dispose(){disposed=true;cancel();await active?.promise.catch(()=>{})}};
}

export function registerComponentRoutes(ctx,manager){
  for(const action of ['status','prepare','cancel'])ctx.connection.fetch.register({
    path:'/api/qx-components/'+action,methods:[action==='status'?'GET':'POST'],requestBody:'buffered',
    fetch:async request=>{
      const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store','x-content-type-options':'nosniff'}});
      if(action!=='status'){
        const url=new URL(request.url),host=request.headers.get('host');if(host)url.host=host;
        if(request.headers.get('x-qx-components')!=='1'||(request.headers.get('origin')&&request.headers.get('origin')!==url.origin))return json({error:'请在本机工作台中操作组件。'},403);
      }
      try{
        if(action==='status')return json(await manager.status());
        if(action==='cancel')manager.cancel();else void manager.prepare().catch(()=>{});
        return json(manager.read(),202);
      }catch{return json({error:'组件状态暂不可用，请重试。'},503)}
    },
  });
}
