import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {bridge,scopeOf} from './dependencies.mjs';
import {createLazyConnection} from './runtime.mjs';
import {createComponentManager,registerComponentRoutes} from './component-state.mjs';
export const name='qx-lazy-mcp';
export const inject=['tools'];
export const Config=bridge.Config;
const owners=new WeakMap();
export function publicToolName(server,raw){
  const joined=`mcp__${server}__${raw}`,normalized=joined.replace(/[^A-Za-z0-9_-]/g,'_');
  if(normalized===joined&&normalized.length<=64)return normalized;
  return normalized.slice(0,51)+'_'+createHash('sha256').update(server+'\0'+raw).digest('hex').slice(0,12);
}
export async function apply(ctx,config){
  if(config.transport!=='stdio'||!/^[A-Za-z0-9_-]{1,32}$/.test(config.serverName))throw Error('按需启动仅适用于已登记的本机工具。');
  const catalog=JSON.parse(await readFile(new URL(`./catalogs/${config.serverName}.json`,import.meta.url),'utf8'));
  if(catalog.serverName!==config.serverName||!Array.isArray(catalog.tools)||!catalog.tools.length)throw Error('本机工具目录无效。');
  const component=config.serverName==='windows'?createComponentManager({config}):null;
  const connection=createLazyConnection({config,catalog,...(component?{prepare:(_config,options)=>component.prepare(options)}:{})});
  if(component){
    ctx.inject(['connection'],inner=>registerComponentRoutes(inner,component));
    ctx.effect(()=>()=>component.dispose(),'qx-lazy-mcp.component');
  }
  const server=config.serverName;
  ctx.effect(()=>{
    const owner=scopeOf(ctx)??ctx.root;let names=owners.get(owner);if(!names){names=new Set();owners.set(owner,names)}
    if(names.has(server))throw Error('本机工具名称重复。');names.add(server);
    return()=>names.delete(server);
  },'qx-lazy-mcp.namespace');
  ctx.effect(()=>()=>connection.dispose(),'qx-lazy-mcp.connection');
  ctx.on('internal/plugin',fiber=>{if(fiber===ctx.fiber&&fiber.uid===null)return connection.dispose();},{global:true});
  ctx.effect(()=>{
    const registrations=[];
    try{for(const tool of catalog.tools){
    registrations.push(ctx.tools.register(bridge.createMcpToolDefinition(ctx,{
      name:publicToolName(server,tool.name),rawName:tool.name,description:tool.description||'',inputSchema:tool.inputSchema,
      outputSchema:tool.outputSchema,taskRequired:tool.execution?.taskSupport==='required',
      call:(args,exec)=>connection.call(tool.name,args,exec),
    })));
    }}catch(error){for(const dispose of registrations)dispose();throw error;}
    return()=>{for(const dispose of registrations)dispose();};
  },'qx-lazy-mcp.tools');
  ctx.inject(['mcpResources'],inner=>inner.mcpResources.register(server,{request:(request,exec)=>connection.resource(request,exec)}));
  if(catalog.instructions)ctx.inject(['systemPrompt'],inner=>inner.systemPrompt.section({name:`mcp:${server}`,
    order:inner.systemPrompt.getSectionOrder('MCP_SERVERS'),interpolate:false,text:()=>`### MCP server: ${server}\n\n${catalog.instructions}`}));
}
