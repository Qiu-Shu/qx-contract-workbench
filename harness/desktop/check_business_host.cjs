// Real Harness host with a loopback-only model fixture and isolated synthetic data.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {initialize,runHost}=require('./installed-runtime.cjs');
const root=path.resolve(__dirname,'..'),payload=process.env.QX_QA_PAYLOAD||path.join(root,'.local/package-updates-0.2.3/workbench');
const data=process.env.QX_QA_DATA||path.join(root,'.local/business-workflows-qa/data');
if(!path.resolve(data).startsWith(path.join(root,'.local')+path.sep))throw Error('QA data must stay in the project scratch directory');
fs.mkdirSync(data,{recursive:true});
let calls=0;
const mock=http.createServer((request,response)=>{
  let body='';request.on('data',chunk=>body+=chunk);request.on('end',()=>{
    if(request.method==='GET'){response.setHeader('content-type','application/json');response.end(JSON.stringify({object:'list',data:[{id:'deepseek-v4-flash',object:'model',created:0,owned_by:'fixture'}]}));return;}
    const input=JSON.parse(body),system=typeof input.system==='string'?input.system:JSON.stringify(input.system);
    const combined=system+'\n'+JSON.stringify(input.messages),start=combined.lastIndexOf('当前对话已由律师'),workflow=start<0?'':combined.slice(start);
    calls++;fs.writeFileSync(path.join(data,`mock-${calls}.json`),JSON.stringify({system,messages:input.messages,workflow}));
    const text=workflow.includes('业务 reception')?'【可发送回复】\n您好，您可以先把合同和相关记录发来。方便的话，我们再约个时间沟通具体诉求。\n【律师参考】\n待核实：合同主体及关键期限。建议下一步：确认咨询时间。':workflow.includes('不得开始正式审查')?'已收到合同。甲方为测试甲公司，乙方为测试乙公司。请在下方选择我们代表哪一方，再确认审查程度。':'已按您确认的选项开始处理。这是本机测试回复。';
    response.writeHead(200,{'content-type':'text/event-stream'});
    const events=[['message_start',{type:'message_start',message:{id:'msg_business_'+calls,type:'message',role:'assistant',content:[],model:'deepseek-v4-flash',stop_reason:null,stop_sequence:null,usage:{input_tokens:1,output_tokens:0}}}],['content_block_start',{type:'content_block_start',index:0,content_block:{type:'text',text:''}}],['content_block_delta',{type:'content_block_delta',index:0,delta:{type:'text_delta',text}}],['content_block_stop',{type:'content_block_stop',index:0}],['message_delta',{type:'message_delta',delta:{stop_reason:'end_turn',stop_sequence:null},usage:{output_tokens:1}}],['message_stop',{type:'message_stop'}]];
    for(const [event,value] of events)response.write(`event: ${event}\ndata: ${JSON.stringify(value)}\n\n`);response.end();
  });
});
mock.listen(0,'127.0.0.1',async()=>{
  process.env.DEEPSEEK_BASE_URL=`http://127.0.0.1:${mock.address().port}/anthropic`;
  process.env.QX_INSTALL_DATA=data;process.env.QX_PAYLOAD_ROOT=payload;
  try{
    initialize(payload,data);
    const config=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),patch=require(path.join(payload,'node_modules/yaml')).parse(fs.readFileSync(config,'utf8'),{customTags:[{tag:'tag:yaml.org,2002:js',resolve:value=>({__jsExpr:value})}]});
    function change(entries){for(const entry of entries){if(entry.id==='qx-desktop-session')entry.name=path.join(root,'desktop/integration/index.mjs').replaceAll('\\','/');if(entry.insert)change(entry.insert);}}
    change(patch);
    patch.push({id:'llm-deepseek',config:{baseURL:process.env.DEEPSEEK_BASE_URL}});
    fs.writeFileSync(config,JSON.stringify(patch));
    await runHost({payload,data,store:{withSecret:async consume=>{await consume('sk-synthetic-business-test');return {status:'saved'}}},app:{exit:code=>process.exit(code)}});
  }catch(error){console.error(error);process.exit(1)}
});
