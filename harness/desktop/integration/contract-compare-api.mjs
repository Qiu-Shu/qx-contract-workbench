import {readFile} from 'node:fs/promises';
import {compareContracts,resolveContractReference,confinedPath,comparisonError,indexedContractPaths} from './contract-compare.mjs';
const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store','x-content-type-options':'nosniff'}});
export function installContractComparison(ctx){
  async function scope(sessionId){
    if(typeof sessionId!=='string'||!sessionId||sessionId.length>200)throw comparisonError('请选择当前对话',400);
    const live=ctx.sessions.get(sessionId),header=live?.header||(await ctx.sessionQuery.listSessions()).find(s=>s.header.id===sessionId)?.header;
    if(!header?.cwd)throw comparisonError('当前对话没有可用的工作区',404);
    let root=live&&ctx.workingDirectory?ctx.workingDirectory.get(live):header.cwd;
    if(!live&&ctx.sessionQuery.listEvents){const changed=(await ctx.sessionQuery.listEvents(sessionId)).findLast(event=>event.type==='working-directory/change');if(changed)root=(await ctx.sessionQuery.readEvent({sessionId,seq:changed.seq,before:0,after:0})).target.data.cwd;}
    const fileScope={sessionId,workspaceRoot:root};
    return {root,sessionId,authorize:path=>ctx.workspaceFiles.stat(fileScope,path),fileScope};
  }
  async function execute(action,args){
    const current=await scope(args.sessionId);let result;
    if(action==='compare')result=await compareContracts(current,args.before,args.after);
    else if(action==='locate')result=await resolveContractReference(current,args.reference);
    else{
      const directory=await confinedPath(current.root,args.path||'',{directory:true});
      result=await ctx.workspaceFiles.list(current.fileScope,directory.path);
      result={...result,entries:result.entries.filter(e=>!e.name.startsWith('.')&&(e.type==='directory'||/\.(txt|md|docx?|pdf|rtf|odt)$/i.test(e.name)))};
      if(!directory.key)for(const path of await indexedContractPaths(current.root))if(path.includes('/'))result.entries.push({name:path.split('/').at(-1),path,type:'file',indexed:true});
    }
    if((await scope(args.sessionId)).root!==current.root)throw comparisonError('工作区已变化，请重新选择合同',409);
    return result;
  }
  for(const action of ['list','compare','locate'])ctx.connection.fetch.register({path:'/api/qx-compare/'+action,methods:['POST'],requestBody:'buffered',fetch:async request=>{
    try{
      const expected=new URL(request.url);if(request.headers.get('host'))expected.host=request.headers.get('host');
      if(request.headers.get('x-qx-compare')!=='1'||request.headers.get('origin')&&request.headers.get('origin')!==expected.origin)throw comparisonError('请从当前工作台操作',403);
      if(!request.headers.get('content-type')?.startsWith('application/json'))throw comparisonError('请求格式无效');
      const raw=await request.text();if(raw.length>16000)throw comparisonError('请求过大',413);
      const args=JSON.parse(raw);if(!args||typeof args!=='object'||Array.isArray(args))throw comparisonError('请求格式无效');
      return json(await execute(action,args));
    }catch(error){return json({error:error.status?error.message:'对比未完成，请检查文件是否存在，或先在对话中读取并解析材料。'},error.status||400);}
  }});
  ctx.connection.fetch.register({path:'/api/qx-compare/client.js',methods:['GET'],requestBody:'buffered',fetch:async()=>new Response(await readFile(new URL('./contract-compare-client.js',import.meta.url)),{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}})});
  ctx.tools.register({name:'contract_compare',description:'只读比较当前工作区的两份合同文字，返回增删及绑定原件摘要、页码或段落的引用。Office/PDF先用已有材料工具按original视图解析；部分结果不表示全文无差异。此工具不会生成或应用修订，批注和修订继续使用现有合同审查工具。',parameters:{type:'object',properties:{before:{type:'string'},after:{type:'string'},start:{type:'integer',minimum:0}},required:['before','after'],additionalProperties:false},output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},isConcurrencySafe:()=>true,presentCall:()=>({card:'generic',kind:'read',title:'对比合同文字'}),execute:async(args,exec)=>{
    try{
      const result=await execute('compare',{...args,sessionId:exec.agent?.session?.id});const start=Number.isSafeInteger(args.start)&&args.start>=0?args.start:0;
      const changes=result.changes.slice(start,start+4).map(change=>({before:change.before&&{...change.before,text:change.before.text.slice(0,800)},after:change.after&&{...change.after,text:change.after.text.slice(0,800)}}));
      return JSON.stringify({...result,changes,totalChanges:result.changes.length,nextStart:start+4<result.changes.length?start+4:null,note:'长段摘录最多800字符；完整对比及原文定位见工作台的合同对比入口。'});
    }catch(error){throw comparisonError(error.status?error.message:'对比未完成，请先读取并解析材料');}
  }});
}
