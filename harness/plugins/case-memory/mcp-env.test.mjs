import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,readdir,writeFile,rm,access} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {createHash,randomBytes} from 'node:crypto';

const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
async function installed(name){
  for(const dir of await readdir(join(root,'node_modules/.pnpm'))){
    if(!dir.startsWith(name.replace('/','+').slice(0,25)))continue;
    const file=join(root,'node_modules/.pnpm',dir,'node_modules',name,'package.json');
    try{await access(file);return createRequire(file);}catch{}
  }
  throw Error('Installed package not found: '+name);
}
const mcpRequire=await installed('@deepseek-ai/dsh-mcp-client');
const loaderRequire=await installed('@deepseek-ai/cordis-plugin-loader');
const editorRequire=await installed('@deepseek-ai/dsh-config-editor');
const settingsRequire=await installed('@deepseek-ai/dsh-settings');
const {Config,apply}=await import(pathToFileURL(mcpRequire.resolve('@deepseek-ai/dsh-mcp-client')));
const {interpolate}=await import(pathToFileURL(loaderRequire.resolve('@deepseek-ai/cordis-plugin-loader')));
const {ConfigEditor}=await import(pathToFileURL(editorRequire.resolve('@deepseek-ai/dsh-config-editor')));
const {SettingsForms}=await import(pathToFileURL(settingsRequire.resolve('@deepseek-ai/dsh-settings')));
const yaml=editorRequire('js-yaml');
const expression={__jsExpr:"process.env.QX_HINDSIGHT_TOKEN || ''"};

test('configured MCP receives only its explicitly referenced token; raw config and browser describe remain secret-free',async t=>{
  const directory=await mkdtemp(join(tmpdir(),'qx-mcp-env-'));
  t.after(()=>rm(directory,{recursive:true,force:true,maxRetries:5,retryDelay:100}));
  const token=randomBytes(24).toString('hex'),saved={};
  for(const key of ['QX_HINDSIGHT_TOKEN','QX_UNRELATED_API_KEY','QX_CASE_MEMORY_CONTROL_TOKEN']){
    saved[key]=process.env[key];process.env[key]=key==='QX_HINDSIGHT_TOKEN'?token:'synthetic-unrelated';
  }
  t.after(()=>{for(const [key,value] of Object.entries(saved)){if(value===undefined)delete process.env[key];else process.env[key]=value;}});
  const configText=await readFile(join(root,'config/cordis.patch.yml'),'utf8');
  const entry=yaml.load(configText).flatMap(row=>row.insert||[]).find(row=>row.id==='qx-case-memory');
  assert.ok(entry);
  assert.deepEqual(entry.config.env.QX_HINDSIGHT_TOKEN,expression);
  const raw=structuredClone(entry.config);
  const resolved=Config(interpolate({},raw));
  assert.equal(resolved.env.QX_HINDSIGHT_TOKEN,token);
  assert.deepEqual(raw.env.QX_HINDSIGHT_TOKEN,expression,'official interpolation must not mutate the persisted raw config');
  assert.ok(!JSON.stringify(raw).includes(token));

  // Exercise the installed profile editor against a temporary profile, not a live one.
  await writeFile(join(directory,'package.json'),JSON.stringify({name:'synthetic-profile',private:true,dsh:{profile:{bundles:[]}}}));
  await writeFile(join(directory,'cordis.patch.yml'),yaml.dump([{insert:[{...entry,config:raw}]}]));
  const profileEntry={id:'synthetic-memory-entry',options:{...entry,config:raw},fiber:{uid:1,state:2,runtime:{Config},effectiveConfig:resolved,ctx:{}}};
  const editor={ownerContext:{profileContext:{dir:directory,installAnchor:join(directory,'package.json')}},entries:()=>[profileEntry]};
  const layers=ConfigEditor.prototype.configuration.call(editor);
  assert.deepEqual(layers[0].inherited.env.QX_HINDSIGHT_TOKEN,expression);
  assert.ok(!JSON.stringify(layers.map(({inherited,override})=>({inherited,override}))).includes(token));
  const forms={ownerContext:{configEditor:{configuration:()=>layers},emit(){}},schema:()=>Config,revisions:new Map(),presentations:new WeakMap()};
  const browserView=SettingsForms.prototype.describe.call(forms,{redactSecrets:true});
  assert.deepEqual(browserView,[],'non-volatile MCP configuration is excluded from the actual settings describe projection');
  assert.ok(!(await readFile(join(directory,'cordis.patch.yml'),'utf8')).includes(token));

  const fixture=join(directory,'server.mjs');
  await writeFile(fixture,`import {createInterface} from 'node:readline';
import {writeFileSync} from 'node:fs';import {createHash} from 'node:crypto';
writeFileSync(process.argv[2],JSON.stringify({digest:createHash('sha256').update(process.env.QX_HINDSIGHT_TOKEN||'').digest('hex'),unrelated:process.env.QX_UNRELATED_API_KEY!==undefined,control:process.env.QX_CASE_MEMORY_CONTROL_TOKEN!==undefined,encoding:process.env.PYTHONIOENCODING}));
createInterface({input:process.stdin}).on('line',line=>{const request=JSON.parse(line);if(request.id===undefined)return;const result=request.method==='initialize'?{protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'synthetic-env-fixture',version:'1.0.0'}}:request.method==='tools/list'?{tools:[]}:{};process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\\n');});`);
  async function spawnMcp(serverName,env){
    const output=join(directory,serverName+'.json'),disposers=[],logs=[];
    const ctx={root:{},fiber:{uid:1},get(){},inject(){},on(){},tools:{register(){throw Error('fixture exposes no tools');}},
      logger:{info(){},warn(message){logs.push(message);},error(message){logs.push(message);}},effect(callback){const disposer=callback();if(disposer)disposers.push(disposer);}};
    try{
      await apply(ctx,Config({transport:'stdio',serverName,command:process.execPath,args:[fixture,output],cwd:directory,env,reconnect:{enabled:false},failOnStartupError:true}));
      const result=JSON.parse(await readFile(output,'utf8'));
      assert.equal(result.unrelated,false);assert.equal(result.control,false);assert.ok(!JSON.stringify(logs).includes(token));
      return result;
    }finally{for(const dispose of disposers.reverse())await dispose();}
  }
  const nominated=await spawnMcp('qx_case_memory',resolved.env);
  assert.equal(nominated.digest,createHash('sha256').update(token).digest('hex'));assert.equal(nominated.encoding,'utf-8');
  const unrelated=await spawnMcp('unrelated_mcp',{PYTHONIOENCODING:'utf-8'});
  assert.equal(unrelated.digest,createHash('sha256').update('').digest('hex'),'ambient memory token remains scrubbed for other MCP servers');
  delete process.env.QX_HINDSIGHT_TOKEN;
  const offline=Config(interpolate({},raw));assert.equal(offline.env.QX_HINDSIGHT_TOKEN,'','runtime absence preserves local fallback startup');
});
