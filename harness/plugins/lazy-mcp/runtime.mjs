import {isDeepStrictEqual} from 'node:util';
import {loadMcpSdk,scrubbedParentEnv} from './dependencies.mjs';
import {resolveOptionalComponent} from './components.mjs';

const signature=tool=>({name:tool.name,inputSchema:tool.inputSchema,outputSchema:tool.outputSchema,execution:tool.execution});
export function createLazyConnection({config,catalog,prepare=resolveOptionalComponent}){
  let generation=null,pending=null,disposed=false;
  let preparation=null,waiters=0;
  const lifetime=new AbortController();
  const timeout=config.toolCallTimeoutMs??120000,startupTimeout=config.startupTimeoutMs??30000;
  const expected=new Map(catalog.tools.map(tool=>[tool.name,tool]));
  async function close(current){
    if(!current)return;
    current.closing??=(async()=>{
      const pid=current.transport.pid,attached=current.client.transport!==undefined;
      await current.client.close();await current.transport.close();
      // The SDK clears transport.pid before the child emits close; wait for its actual close signal.
      if((pid||attached)&&!current.down){
        let timer;
        try{await Promise.race([current.closed,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('工具进程尚未退出，请重新加载该工具后重试。')),5000)})]);}
        finally{clearTimeout(timer)}
      }
    })();
    await current.closing;
    if(generation===current)generation=null;
  }
  function open(){
    if(disposed)return Promise.reject(Error('工具已关闭。'));
    if(pending)return pending;
    if(generation&&!generation.down&&!generation.closing)return Promise.resolve(generation);
    pending=(async()=>{
      if(generation)await close(generation);
      if(disposed)throw Error('工具已关闭。');
      const controller=new AbortController();preparation=controller;
      let runtime;
      try{runtime=await prepare(config,{signal:AbortSignal.any([lifetime.signal,controller.signal])})}
      finally{if(preparation===controller)preparation=null}
      if(disposed)throw Error('工具已关闭。');
      // Bundled servers use the SDK's legacy-compatible negotiation; auto probes spawn twice.
      const {Client,StdioClientTransport}=loadMcpSdk();
      const client=new Client({name:'qx-lazy-mcp',version:'1.0.0'},{capabilities:{}});
      const transport=new StdioClientTransport({command:runtime.command,args:runtime.args||[],cwd:runtime.cwd||undefined,
        env:{...scrubbedParentEnv(),...(runtime.env||{})},stderr:'pipe'});
      const closed=Promise.withResolvers();
      const current={client,transport,down:false,closing:null,closed:closed.promise};generation=current;
      client.onclose=()=>{current.down=true;closed.resolve();};
      // Tool stderr may contain client material. Drain it without persisting it.
      transport.stderr?.resume();
      try{
        await client.connect(transport,{timeout:startupTimeout});
        const listed=await client.listTools(undefined,{timeout:startupTimeout});
        const live=new Map(listed.tools.map(tool=>[tool.name,tool]));
        if(live.size!==listed.tools.length||live.size!==expected.size||[...expected].some(([name,tool])=>!isDeepStrictEqual(signature(tool),signature(live.get(name)||{}))))
          throw Error('工具目录与运行组件不一致，请更新工作台工具组件后重试。');
        if(disposed||current.down)throw Error('工具连接已关闭。');
        return current;
      }catch(error){await close(current);throw error;}
    })().finally(()=>{pending=null;});
    return pending;
  }
  async function ensure(signal){
    signal?.throwIfAborted();waiters++;
    let abort;
    try{
      const connection=open();
      if(!signal)return await connection;
      return await Promise.race([connection,new Promise((_,reject)=>{
        abort=()=>reject(signal.reason);signal.addEventListener('abort',abort,{once:true});
        if(signal.aborted)abort();
      })]);
    }finally{
      if(abort)signal.removeEventListener('abort',abort);
      waiters--;if(!waiters)preparation?.abort();
    }
  }
  return {
    async call(name,args,exec={}){
      exec.signal?.throwIfAborted();
      if(!expected.has(name))throw Error('未登记的工具。');
      const current=await ensure(exec.signal);exec.signal?.throwIfAborted();
      if(disposed||current.down)throw Error('工具连接已关闭，请重新发起操作。');
      // Never retry tools/call: a transport failure may follow a completed action.
      return current.client.callTool({name,arguments:args},{signal:exec.signal,timeout,toolDefinition:expected.get(name)});
    },
    async resource(request,exec={}){
      exec.signal?.throwIfAborted();const current=await ensure(exec.signal);exec.signal?.throwIfAborted();
      const options={signal:exec.signal,timeout};
      if(!current.client.getServerCapabilities()?.resources){
        if(request.method==='resources/list')return {resources:[]};
        if(request.method==='resources/templates/list')return {resourceTemplates:[]};
        throw Error('该工具服务不提供资源读取。');
      }
      if(request.method==='resources/list')return current.client.listResources(request.cursor?{cursor:request.cursor}:undefined,options);
      if(request.method==='resources/templates/list')return current.client.listResourceTemplates(request.cursor?{cursor:request.cursor}:undefined,options);
      if(request.method==='resources/read')return current.client.readResource({uri:request.uri},options);
      throw Error('不支持的资源请求。');
    },
    async dispose(){disposed=true;lifetime.abort();await close(generation);await pending?.catch(()=>{});},
  };
}
