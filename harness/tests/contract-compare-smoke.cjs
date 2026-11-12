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
fs.writeFileSync(path.join(profile,'cordis.patch.yml'),JSON.stringify([{id:'workspace-controller',config:{documentsDirectory:data}},{id:'session-title-llm',disabled:true},{id:'session-telemetry-otel',disabled:true},{insert:[{id:'qx-desktop-session',name:'@qunxing/desktop-session'}]}]));
fs.writeFileSync(path.join(workspace,'原合同.txt'),'第一条 保密。\n第二条 价款为人民币100元。\n第三条 保留。');
fs.writeFileSync(path.join(workspace,'新合同.txt'),'第一条 保密。\n第二条 价款为人民币200元。\n第三条 保留。');
const child=spawn(path.join(app,'runtime/node.exe'),[path.join(app,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'web','--no-open','--host','127.0.0.1','--port','0'],{cwd:workspace,windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,DSH_HOME:home,QX_INSTALL_DATA:data,DEEPSEEK_API_KEY:'sk-synthetic-contract-comparison-only',DEEPSEEK_BASE_URL:'http://127.0.0.1:1',DSH_TELEMETRY_MODE:'OFF'}});
const log=fs.createWriteStream(path.join(data,'host.log'));let pending='';
child.stdout.on('data',bytes=>{pending+=bytes;let end;while((end=pending.indexOf('\n'))>=0){const line=pending.slice(0,end);pending=pending.slice(end+1);const m=line.match(/^dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/);if(m)process.stdout.write(JSON.stringify({url:m[1],data,workspace,packaged,integration})+'\n');else log.write(line+'\n');}});
child.stderr.on('data',bytes=>log.write(bytes));child.on('exit',code=>process.exit(code||0));
process.on('SIGTERM',()=>child.kill());
