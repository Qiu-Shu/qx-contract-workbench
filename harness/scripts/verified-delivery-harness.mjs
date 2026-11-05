// Evaluation adapter: exercise the installed LLM service and production plugin.
// No credentials or network operations; caller supplies audited provider chunks.
import {createRequire} from 'node:module';
import {realpathSync,readdirSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import * as plugin from '../plugins/verified-delivery/index.mjs';
import {deliveriesInTurn} from '../plugins/verified-delivery/core.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const local=createRequire(join(root,'package.json'));
const dsh=createRequire(realpathSync(local.resolve('@deepseek-ai/dsh/package.json')));
const base=createRequire(dsh.resolve('@deepseek-ai/dsh-base/package.json'));
const {Context}=await import(pathToFileURL(base.resolve('@deepseek-ai/cordis')).href);
export const llm=await import(pathToFileURL(base.resolve('@deepseek-ai/dsh-llm')).href);
const sessionDir=readdirSync(join(root,'node_modules/.pnpm')).find(n=>n.startsWith('@deepseek-ai+dsh-session@'));
export const {Session}=await import(pathToFileURL(join(root,'node_modules/.pnpm',sessionDir,'node_modules/@deepseek-ai/dsh-session/lib/index.js')).href);
export function providerMessages(messages){
 return messages.map(m=>{
  const content=m.content?[{type:'text',text:m.content}]:[];
  if(m.role==='assistant')return llm.createAssistantMessage({content:[...content,...(m.tool_calls||[]).map(c=>({type:'tool-call',id:c.id,name:'mcp__qx_legal__'+c.function.name,arguments:c.function.arguments}))],source:{provider:'fixture',model:'fixture'}});
  if(m.role==='tool'){
   const relay=JSON.parse(m.content),value=relay.result;
   return {role:'tool',toolCallId:m.tool_call_id,source:{kind:'tool',callId:m.tool_call_id},isError:!!relay.is_error,
    content:[{type:'text',text:JSON.stringify({content:[{type:'text',text:JSON.stringify(value??relay)}],structuredContent:value})}]};
  }
  return {role:m.role,content,...(m.role==='user'?{source:{kind:'user'}}:{})};
 });
}
export async function deliverProviderResponse(messages,result,workspace){
 const raw=result.choices[0].message,chunks=[];
 let index=0;
 if(raw.content){chunks.push({type:'block-start',index,blockType:'text'},{type:'text-delta',index,text:raw.content},{type:'block-end',index,block:{type:'text',text:raw.content}});index++;}
 for(const c of raw.tool_calls||[]){
  const block={type:'tool-call',id:c.id,name:'mcp__qx_legal__'+c.function.name,arguments:c.function.arguments};
  chunks.push({type:'block-start',index,blockType:'tool-call'},{type:'tool-call-delta',index,id:c.id,name:block.name,argumentsDelta:block.arguments},{type:'block-end',index,block});index++;
 }
 if(result.usage)chunks.push({type:'usage',usage:{inputTokens:result.usage.prompt_tokens,outputTokens:result.usage.completion_tokens}});
 chunks.push({type:'finish',reason:{kind:({stop:'stop',tool_calls:'tool-calls',length:'max-tokens'})[result.choices[0].finish_reason]||'error'}});
 const history=providerMessages(messages),protectedTurn=!!deliveriesInTurn(history);
 const delivered=await runHarnessStream(history,chunks,workspace);
 const finish=delivered.visible.findLast(c=>c.type==='finish');
 if(['error','aborted','max-tokens'].includes(finish?.reason.kind))throw Error('Delivery stream ended without a complete response: '+JSON.stringify(finish.reason));
 const session=Session.create('delivery-evaluation');
 session.append('assistant/message',{turn:0,step:0,message:delivered.message,stream:delivered.stream},{surfaceOp:'append'});
 return {...delivered,protectedTurn,events:session.snapshotEvents(),text:delivered.message.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')};
}
export async function runHarnessStream(messages,chunks,workspace,{agentLoop=true,prepared=false}={}){
 const ctx=new Context();
 new llm.LlmRuntime(ctx);
 class Adapter extends llm.LlmAdapter{
  async prepareCall(){return {model:{provider:'fixture',id:'fixture',name:'fixture'},stream:async function*(){yield* chunks;}};}
 }
 const dispose=ctx.llm.registerAdapter(['fixture'],new Adapter());
 plugin.apply(ctx,{workspace});
 const options={provider:'fixture',model:'fixture',messages,signal:new AbortController().signal};
 if(agentLoop)llm.markAgentLoopRequest(options);
 try{
  const visible=[],accumulator=new llm.AssistantStreamAccumulator();
  const preparedCall=prepared?await ctx.llm.prepareCall({provider:options.provider,model:options.model},options.signal):null;
  for await(const chunk of preparedCall?preparedCall.stream(options):ctx.llm.stream(options)){
   visible.push(chunk);accumulator.push({time:Date.now(),chunk});
  }
  const stream=accumulator.snapshot();
  const assembled=llm.assembleAssistantStream(stream);
  const message=llm.createAssistantMessage({content:assembled.blocks(),source:{provider:'fixture',model:'fixture',...(assembled.replayState?{replayState:assembled.replayState}:{})}});
  return {visible,stream,message};
 }finally{dispose();await ctx.fiber.dispose();}
}
