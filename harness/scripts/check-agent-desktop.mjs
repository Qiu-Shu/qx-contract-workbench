// Read-only integration smoke: no windows, clipboard, screenshots or model calls.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readdirSync,readFileSync,mkdirSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=resolve(fileURLToPath(new URL('../',import.meta.url)));
const directory=readdirSync(join(root,'node_modules/.pnpm')).find(x=>x.startsWith('@deepseek-ai+dsh-mcp-client_'));
const req=createRequire(join(root,'node_modules/.pnpm',directory,'node_modules/@deepseek-ai/dsh-mcp-client/package.json'));
const {Client}=req('@modelcontextprotocol/client');
const {StdioClientTransport}=req('@modelcontextprotocol/client/stdio');
const {Config,apply}=await import(pathToFileURL(req.resolve('@deepseek-ai/dsh-mcp-client')));
const yaml=createRequire(createRequire(import.meta.url).resolve('electron-updater'))('js-yaml');
const {migrateInstalledAgentDesktop}=createRequire(import.meta.url)('../desktop/installed-migrations.cjs');
const entry=yaml.load(readFileSync(join(root,'config/cordis.patch.yml'),'utf8')).flatMap(x=>x.insert||[]).find(x=>x.id==='qx-agent-desktop');
assert.ok(entry);assert.equal(entry.disabled,false);
if(process.argv.includes('--configure-development')){
  const result=migrateInstalledAgentDesktop({data:root,portableConfig:[{insert:[entry]}],yaml});
  console.log(JSON.stringify({developmentConfiguration:result.status,changedFiles:result.changedFiles}));
}
if(process.argv.includes('--enable-development')){
  const file=join(root,'.local/dsh-home/profiles/web/cordis.patch.yml'),before=readFileSync(file,'utf8');
  const rows=yaml.load(before);assert.ok(Array.isArray(rows));
  const entries=rows.flatMap(x=>x.insert||[x]).filter(x=>x.id==='qx-agent-desktop');
  assert.ok(entries.length,'Configure the development entry first');
  if(entries.reduce((disabled,x)=>x.disabled??disabled,true)){
    const next=[...rows,{id:'qx-agent-desktop',disabled:false}];
    const backup=join(root,'.local/agent-desktop-enable-backup-'+Date.now()+'.yml');
    writeFileSync(backup,before,{flag:'wx'});
    const terminator=before.match(/^\.\.\.[ \t]*(?:#[^\r\n]*)?(?:\r?\n)?\s*$/m);
    const offset=terminator?terminator.index:before.length;
    const after=before.slice(0,offset).trimEnd()+'\n\n- id: qx-agent-desktop\n  disabled: false\n'+before.slice(offset);
    assert.deepEqual(yaml.load(after),next);
    assert.equal(readFileSync(file,'utf8'),before,'Configuration changed concurrently');
    writeFileSync(file,after);
  }
  console.log(JSON.stringify({developmentDesktopEnabled:true}));
}
const scratch=mkdtempSync(join(tmpdir(),'qx-desktop-check-'));
const report={status:'running',checks:[],toolCount:0,privateDesktopContentRead:false};
try{
  const client=new Client({name:'qx-agent-desktop-check',version:'1.0.0'});
  const transport=new StdioClientTransport({command:entry.config.command,args:entry.config.args,env:{AGENT_DESKTOP_HOME:join(scratch,'direct')},stderr:'pipe'});
  try{
    await client.connect(transport);
    const listed=await client.listTools();report.toolCount=listed.tools.length;
    for(const name of ['desktop_status','desktop_snapshot','desktop_click','desktop_skills_get'])assert.ok(listed.tools.some(t=>t.name===name),name);
    report.checks.push('native MCP handshake and tool discovery');
    const result=await client.callTool({name:'desktop_status',arguments:{}});
    assert.notEqual(result.isError,true);
    const status=JSON.parse(result.content.find(x=>x.type==='text').text);
    assert.equal(status.ok,true);assert.equal(status.data.version,'1.2.0');
    report.checks.push('read-only desktop_status reports Windows 1.2.0');
    report.skillSchema=listed.tools.find(t=>t.name==='desktop_skills_get').inputSchema;
  }finally{await client.close();}
  const tools=new Map(),disposers=[],logs=[];
  const ctx={root:{},fiber:{uid:1},get(){},inject(){},on(){},tools:{register(definition){assert.ok(!tools.has(definition.name));tools.set(definition.name,definition);return()=>tools.delete(definition.name);}},
    logger:{info(){},warn(message){logs.push(message);},error(message){logs.push(message);}},effect(callback){const dispose=callback();if(dispose)disposers.push(dispose);}};
  try{
    await apply(ctx,Config({...entry.config,env:{AGENT_DESKTOP_HOME:join(scratch,'harness')},failOnStartupError:true}));
    assert.equal(tools.size,report.toolCount);
    assert.ok(tools.has('mcp__agent_desktop__desktop_status'));
    report.checks.push('real Harness MCP client accepts and registers every tool schema');
  }finally{for(const dispose of disposers.reverse())await dispose();}
  assert.equal(tools.size,0);report.checks.push('Harness disposal unregisters desktop tools');
  if(process.argv.includes('--codex')){
    const configured=JSON.parse(execFileSync('codex.exe',['mcp','get','agent-desktop','--json'],{encoding:'utf8',windowsHide:true}));
    assert.equal(configured.enabled,true);assert.equal(configured.transport.type,'stdio');
    assert.deepEqual(configured.transport.args,['mcp']);
    assert.notEqual(configured.transport.env.AGENT_DESKTOP_HOME,entry.config.env.AGENT_DESKTOP_HOME);
    const provenance=JSON.parse(readFileSync(join(root,'tools/agent-desktop/1.2.0/provenance.json'),'utf8'));
    assert.equal(createHash('sha256').update(readFileSync(configured.transport.command)).digest('hex'),provenance.binarySha256);
    const codexClient=new Client({name:'qx-codex-desktop-check',version:'1.0.0'});
    try{
      await codexClient.connect(new StdioClientTransport({command:configured.transport.command,args:configured.transport.args,env:configured.transport.env,stderr:'pipe'}));
      const listed=await codexClient.listTools();assert.equal(listed.tools.length,report.toolCount);
      const result=await codexClient.callTool({name:'desktop_status',arguments:{}});
      assert.notEqual(result.isError,true);
      const status=JSON.parse(result.content.find(x=>x.type==='text').text);
      assert.equal(status.ok,true);assert.equal(status.data.version,'1.2.0');
      report.checks.push('Codex configured executable checksum and enabled stdio configuration');
      report.checks.push('Codex exact configured transport discovers tools and calls desktop_status');
    }finally{await codexClient.close();}
  }
  report.status='passed';
}finally{rmSync(scratch,{recursive:true,force:true,maxRetries:5,retryDelay:100});}
const evidence=join(root,'docs/checks/agent-desktop');mkdirSync(evidence,{recursive:true});
writeFileSync(join(evidence,'connection.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
