// Full resident Harness UI against isolated synthetic materials; never a model request.
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const app=process.env.QX_TEST_APP;if(!app)throw Error('QX_TEST_APP is required');
const root=path.resolve(__dirname,'..'),data=path.join(process.env.QX_TEST_OUTPUT_ROOT||path.join(root,'.local','audit-contract-compare'),String(Date.now()));
const packaged=process.env.QX_TEST_PACKAGED==='1',integration=packaged?path.join(app,'node_modules/@qunxing/desktop-session'):path.join(root,'desktop/integration');
const workspace=path.join(data,'deepseek-harness/default-workspace'),home=path.join(data,'home'),profile=path.join(home,'profiles/web');
fs.mkdirSync(workspace,{recursive:true});fs.mkdirSync(path.join(profile,'node_modules/@qunxing'),{recursive:true});
fs.symlinkSync(path.join(app,'node_modules/@deepseek-ai'),path.join(profile,'node_modules/@deepseek-ai'),'junction');
fs.symlinkSync(integration,path.join(profile,'node_modules/@qunxing/desktop-session'),'junction');
fs.writeFileSync(path.join(profile,'package.json'),JSON.stringify({name:'contract-compare-synthetic',private:true,dependencies:{'@qunxing/desktop-session':'0.1.0'},dsh:{profile:{bundles:['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}}));
fs.writeFileSync(path.join(profile,'cordis.yml'),'[]');
// Business entries create sessions with this existing preset; the UI fixture must supply it.
const skillRoot=path.join(packaged?app:root,'workspace-seed/.dsh/skills');
for(const skill of ['qx-client-reception','qx-contract-review','qx-case-work','qx-mock-hearing'])
  fs.cpSync(path.join(skillRoot,skill),path.join(workspace,'.dsh/skills',skill),{recursive:true});
const agentPlugins=[
  {id:'agent-instructions',name:'@deepseek-ai/dsh-agent-instructions',config:{maxBytes:65536}},
  {id:'tool-fs',name:'@deepseek-ai/dsh-tool-fs'},
  {id:'skill-filesystem',name:'@deepseek-ai/dsh-skill-filesystem'},
  {id:'tool-skill',name:'@deepseek-ai/dsh-tool-skill'}
];
fs.writeFileSync(path.join(profile,'cordis.patch.yml'),JSON.stringify([
  {id:'workspace-controller',config:{documentsDirectory:data}},
  {id:'agent-preset-registry',config:{default:'qunxing'}},
  {id:'attachment-local',config:{dshHome:path.join(workspace,'inbox/.harness')}},
  {id:'session-title-llm',disabled:true},{id:'session-telemetry-otel',disabled:true},
  {insert:[{id:'qx-desktop-session',name:'@qunxing/desktop-session'},
    {id:'qx-feishu',name:path.join(packaged?app:root,'plugins/feishu/index.js').replace(/\\/g,'/'),config:{workspace,stateDir:path.join(data,'feishu'),autoConnect:false}},
    {id:'qx-content-watch',name:path.join(packaged?app:root,'plugins/content-watch/index.mjs').replace(/\\/g,'/'),config:{workspace,stateDir:path.join(data,'content-watch')}},
    {id:'preset-qunxing',name:'@deepseek-ai/dsh-agent-preset',config:{id:'qunxing',order:0,plugins:agentPlugins}}]}
]));
fs.writeFileSync(path.join(workspace,'原合同.txt'),'第一条 保密。\n第二条 价款为人民币100元。\n第三条 保留。');
fs.writeFileSync(path.join(workspace,'新合同.txt'),'第一条 保密。\n第二条 价款为人民币200元。\n第三条 保留。');
const child=spawn(path.join(app,'runtime/node.exe'),[path.join(app,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'web','--no-open','--host','127.0.0.1','--port','0'],{cwd:workspace,windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,DSH_HOME:home,QX_INSTALL_DATA:data,DEEPSEEK_API_KEY:'sk-synthetic-contract-comparison-only',DEEPSEEK_BASE_URL:'http://127.0.0.1:1',DSH_TELEMETRY_MODE:'OFF'}});
const log=fs.createWriteStream(path.join(data,'host.log'));let pending='';
child.stdout.on('data',bytes=>{pending+=bytes;let end;while((end=pending.indexOf('\n'))>=0){const line=pending.slice(0,end);pending=pending.slice(end+1);const m=line.match(/^dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/);if(m)process.stdout.write(JSON.stringify({url:m[1],data,workspace,packaged,integration})+'\n');else log.write(line+'\n');}});
child.stderr.on('data',bytes=>log.write(bytes));child.on('exit',code=>process.exit(code||0));
process.on('SIGTERM',()=>child.kill());
