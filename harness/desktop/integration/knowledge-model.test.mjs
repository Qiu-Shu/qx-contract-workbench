import test from 'node:test';import assert from 'node:assert/strict';import {createKnowledgeModel} from './knowledge-model.mjs';
test('使用真实Harness消息与流组装器，保留既有路由并限制输出',async()=>{
  let request,config;const ctx={llm:{prepareCall:async value=>{config=value;return {config:value,stream:async function*(options){request=options;yield {type:'block-start',index:0,blockType:'text'};yield {type:'text-delta',index:0,text:'{"items":[]}'};yield {type:'block-end',index:0,block:{type:'text',text:'{"items":[]}'}};yield {type:'finish',reason:{kind:'stop'}};}};}}};
  const result=await createKnowledgeModel(ctx)({batch:[{seq:1,role:'user',text:'虚构测试'}],route:{provider:'configured',model:'chosen'},session:'synthetic',signal:new AbortController().signal});
  assert.deepEqual(result.items,[]);assert.equal(config.provider,'configured');assert.equal(config.reasoningEffort,'high');assert.equal(config.maxTokens,2000);assert.equal(request.messages.length,1);assert.ok(!request.tools);assert.equal(request.sessionId,'synthetic');
});

import {createRequire} from 'node:module';import {realpathSync} from 'node:fs';import {pathToFileURL} from 'node:url';
const local=createRequire(import.meta.url),dsh=createRequire(realpathSync(local.resolve('@deepseek-ai/dsh/package.json')));
const {DeepSeekAdapter,resolveAdapterOptions}=await import(pathToFileURL(dsh.resolve('@deepseek-ai/dsh-llm-deepseek')));

function deepseekContext(thinking){
  const options=resolveAdapterOptions({baseURL:'https://example.invalid/anthropic',...(thinking?{thinking}:{})});
  const adapter=new DeepSeekAdapter({options:()=>options,resolveFiles:()=>({}),resolveAuth:async()=>({headers:{'x-api-key':'synthetic'},dispose(){}}),prepareExtensions:async()=>({fields:{}}),resolveUserId:()=> 'synthetic'});
  return {llm:{async prepareCall(config,signal,transform){
    const prepared=await adapter.prepareCall(config.provider,config.model,signal);
    return {config:transform?transform(config,prepared.model):config,stream:prepared.stream};
  }}};
}
test('知识库使用真实DeepSeek序列化发送 enabled/High，不被档位首项Off或会话Off覆盖',async()=>{
  const original=globalThis.fetch;let body;
  globalThis.fetch=async(_url,request)=>{
    body=JSON.parse(request.body);
    const events=[['message_start',{type:'message_start',message:{id:'synthetic',type:'message',role:'assistant',content:[],model:'deepseek-flash',usage:{input_tokens:1,output_tokens:0}}}],
      ['content_block_start',{type:'content_block_start',index:0,content_block:{type:'text',text:''}}],
      ['content_block_delta',{type:'content_block_delta',index:0,delta:{type:'text_delta',text:'{"items":[]}'}}],
      ['content_block_stop',{type:'content_block_stop',index:0}],
      ['message_delta',{type:'message_delta',delta:{stop_reason:'end_turn'},usage:{output_tokens:5}}],['message_stop',{type:'message_stop'}]];
    return new Response(events.map(([event,data])=>`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(''),{headers:{'content-type':'text/event-stream'}});
  };
  try{
    const result=await createKnowledgeModel(deepseekContext())({batch:[],route:{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off'},session:'synthetic',signal:new AbortController().signal});
    assert.deepEqual(result.items,[]);assert.deepEqual(body.thinking,{type:'enabled'});assert.deepEqual(body.output_config,{effort:'high'});assert.equal(body.max_tokens,2000);
  }finally{globalThis.fetch=original;}
});
test('模型明确禁用思考时报告不支持High，不静默降级为Off',async()=>{
  const original=globalThis.fetch;let requests=0;
  globalThis.fetch=async()=>{requests++;throw Error('Unexpected request');};
  try{
    await assert.rejects(createKnowledgeModel(deepseekContext('disabled'))({batch:[],route:{provider:'deepseek-official',model:'deepseek-flash'},session:'synthetic',signal:new AbortController().signal}),error=>error.code==='UNSUPPORTED_REASONING_EFFORT');
    assert.equal(requests,0);
  }finally{globalThis.fetch=original;}
});
