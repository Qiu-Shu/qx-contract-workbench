import {KnowledgeStore} from '../desktop/integration/knowledge-store.mjs';
import {installKnowledge} from '../desktop/integration/knowledge-api.mjs';
import {digest} from '../desktop/integration/knowledge-runtime.mjs';
export function fixture(options={}) {
  const sessions=new Map(),routes=new Map(),tools=new Map(),prompts=[],listeners=new Map();
  const source={
    list:async()=>[...sessions].map(([id,s])=>({id,title:s.title})),
    describe:async id=>{const s=sessions.get(id);if(!s)throw Error('missing');return {records:s.messages.map(m=>({seq:m.seq,type:m.role==='user'?'user/message':'assistant/message',hash:digest(m)})),version:digest(s.messages)};},
    current:async id=>sessions.has(id)?digest(sessions.get(id).messages):null,
    async *messages(id,d){for(const m of sessions.get(id).messages)if(d.records.some(r=>r.seq===m.seq))yield {...m,offset:0};},
    read:async(id,seq,offset=0)=>({seq,text:sessions.get(id).messages.find(m=>m.seq===seq).text.slice(offset,offset+1600),next:null}),
    materials:async id=>sessions.get(id).materials||[],
  };
  const ctx={connection:{fetch:{register:r=>routes.set(r.path,r)}},tools:{register:t=>tools.set(t.name,t)},systemPrompt:{context:p=>{prompts.push(p);return()=>{};}},effect:fn=>fn(),on:(name,fn)=>{listeners.set(name,fn);return()=>{};}};
  const store=new KnowledgeStore(':memory:');let modelCalls=0;
  const service=installKnowledge(ctx,{store,source,schedule:false,caseMemory:async()=>({memories:[]}),model:async()=>{modelCalls++;throw Error('unexpected model call');},...options});
  const add=(id,title='同名客户',messages=[{seq:1,role:'user',text:'审查虚构设备采购合同，关注验收期限。'}])=>sessions.set(id,{title,messages});
  const call=async(name,args,session)=>JSON.parse(await tools.get(name).execute(args,{agent:{session:{id:session}}}));
  const request=async(name,data)=>{const route=routes.get('/api/qx-layered/'+name.split('?')[0]);return route.fetch(new Request('http://localhost/api/qx-layered/'+name,{method:data===undefined?'GET':'POST',headers:{'x-qx-layered':'1','content-type':'application/json'},...(data===undefined?{}:{body:JSON.stringify(data)})}));};
  return {ctx,store,source,service,sessions,add,call,request,prompts,listeners,get modelCalls(){return modelCalls;}};
}
