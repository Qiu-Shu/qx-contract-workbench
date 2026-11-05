import {readFile} from 'node:fs/promises';
import {attachmentPreviewPath} from './attachment-preview.mjs';
import {installWorkflows} from './business-workflows.mjs';
import {installKnowledge} from './knowledge-api.mjs';
import {createKnowledgeModel} from './knowledge-model.mjs';
export const name='qunxing-desktop-session';
export const inject=['connection','attachments','sessions','systemPrompt','sessionQuery','tools','llm'];
export function apply(ctx){
  installWorkflows(ctx);
  installKnowledge(ctx,{model:createKnowledgeModel(ctx)});
  ctx.connection.fetch.register({path:'/api/qx-business/client.js',methods:['GET'],requestBody:'buffered',fetch:async()=>new Response(await readFile(new URL('./business-client.js',import.meta.url)),{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}})});
  ctx.connection.fetch.register({path:'/api/qx-preview/attachment-path',methods:['POST'],requestBody:'buffered',fetch:async request=>{
    try{
      const body=await request.text();if(body.length>4096)throw Error('Invalid attachment');
      const path=attachmentPreviewPath(ctx.attachments,JSON.parse(body));
      return Response.json({path},{headers:{'cache-control':'no-store','x-content-type-options':'nosniff'}});
    }catch{return Response.json({error:'附件预览暂不可用，请确认文件已上传完成后重试。'},{status:400})}
  }});
  ctx.connection.fetch.register({path:'/api/qx-brand/logo.png',methods:['GET'],requestBody:'buffered',fetch:async()=>
    new Response(await readFile(new URL('./assets/qunxing-black-gold.png',import.meta.url)),{
      headers:{'content-type':'image/png','cache-control':'public, max-age=86400','x-content-type-options':'nosniff'}
    })});
}
