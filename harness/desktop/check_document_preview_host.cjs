// Isolated preview QA; model responses come exclusively from this loopback fixture.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {initialize,runHost}=require('./installed-runtime.cjs');
const root=path.resolve(__dirname,'..'),payload=path.join(root,'.local/package-updates-0.2.3/workbench');
const data=path.resolve(process.argv[2]);
if(!data.startsWith(path.join(root,'.local/document-preview-20261104')+path.sep))throw Error('Isolated test data required');
const mock=http.createServer((request,response)=>{
  request.resume();
  if(request.method==='GET'){response.setHeader('content-type','application/json');response.end(JSON.stringify({object:'list',data:[{id:'deepseek-v4-flash',object:'model',created:0,owned_by:'fixture'}]}));return;}
  response.writeHead(200,{'content-type':'text/event-stream'});
  const events=[['message_start',{type:'message_start',message:{id:'msg_preview_test',type:'message',role:'assistant',content:[],model:'deepseek-v4-flash',stop_reason:null,stop_sequence:null,usage:{input_tokens:1,output_tokens:0}}}],
    ['content_block_start',{type:'content_block_start',index:0,content_block:{type:'text',text:''}}],
    ['content_block_delta',{type:'content_block_delta',index:0,delta:{type:'text_delta',text:'这是本机预览测试的模拟回复。\n\n[生成的文档.docx]('+path.join(data,'workspace/drafts/生成的文档.docx').replace(/\\/g,'/')+')'}}],
    ['content_block_stop',{type:'content_block_stop',index:0}],['message_delta',{type:'message_delta',delta:{stop_reason:'end_turn',stop_sequence:null},usage:{output_tokens:1}}],['message_stop',{type:'message_stop'}]];
  for(const [event,value] of events)response.write(`event: ${event}\ndata: ${JSON.stringify(value)}\n\n`);
  response.end();
});
mock.listen(0,'127.0.0.1',async()=>{
  process.env.DEEPSEEK_BASE_URL=`http://127.0.0.1:${mock.address().port}/anthropic`;
  process.env.QX_INSTALL_DATA=data;process.env.QX_PAYLOAD_ROOT=payload;
  try{
    initialize(payload,data);
    const config=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),patch=JSON.parse(fs.readFileSync(config,'utf8'));
    patch.push({id:'llm-deepseek',config:{baseURL:process.env.DEEPSEEK_BASE_URL}},{id:'office-to-pdf',config:{maxConcurrentConversions:1,maxBackgroundConversions:0,timeoutMs:120000}});
    fs.writeFileSync(config,JSON.stringify(patch));
    fs.mkdirSync(path.join(data,'workspace/drafts'),{recursive:true});
    fs.copyFileSync(path.join(root,'.local/document-preview-20261104/fixtures/预览测试.docx'),path.join(data,'workspace/drafts/生成的文档.docx'));
    await runHost({payload,data,store:{withSecret:async consume=>{await consume('sk-synthetic-local-preview-test');return {status:'saved'}}},app:{exit:code=>process.exit(code)}});
  }catch(error){console.error(error);process.exit(1)}
});
