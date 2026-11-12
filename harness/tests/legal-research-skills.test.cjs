const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createHash}=require('node:crypto');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
const methods=['authority-check','case-comparison','issue-memo','lecture-source-pack'];
const names=methods.map(name=>'qx-'+name);
const sha=value=>createHash('sha256').update(value).digest('hex');
const json=file=>JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));
function temporary(t){
  const base=fs.realpathSync(os.tmpdir()),folder=fs.mkdtempSync(path.join(base,'qx-research-skills-'));
  t.after(()=>{assert.equal(path.dirname(path.resolve(folder)),base);fs.rmSync(folder,{recursive:true,force:true});});
  return folder;
}
async function discover(workspace,t){
  const {FileSystemSkillProvider}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-skill-filesystem')).href);
  const empty=path.join(temporary(t),'empty'),control=new AbortController(),warnings=[];
  const provider=new FileSystemSkillProvider({get:()=>undefined,logger:{warn:value=>warnings.push(value)}},
    {signal:control.signal,invalidate(){}},{watch:false,dshHome:empty,agentsHome:empty,bundledSkillDir:empty,customSkillDirs:[path.join(workspace,'.dsh/skills')]});
  t.after(async()=>{control.abort();await provider.dispose();});
  const found=await provider.list({cwd:workspace}),candidates=Array.isArray(found)?found:found.candidates;
  const definitions=[];for(const candidate of candidates)definitions.push(await provider.get(candidate,{cwd:workspace}));
  assert.deepEqual(warnings,[]);return definitions;
}

test('four research methods are discoverable and invocable by the real Harness provider',async t=>{
  const definitions=await discover(path.join(root,'workspace-seed'),t),byName=new Map(definitions.map(x=>[x.name,x]));
  const totals=json('config/practice-skill-additions.json');assert.equal(definitions.length,totals.discoveredCount);
  assert.equal(definitions.filter(x=>x.invocation.modelInvocable).length,totals.automaticallyAvailableCount);
  const {apply}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-tool-skill')).href);let tool;
  apply({tools:{register:value=>{tool=value;},get:()=>tool},skills:{list:async()=>definitions,get:async name=>byName.get(name),snapshot:async()=>({skills:definitions,complete:true})},workingDirectory:{ensure:async()=>path.join(root,'workspace-seed')},on(){}});
  for(const name of names){assert.ok(byName.has(name),'missing '+name);assert.equal(byName.get(name).invocation.modelInvocable,true);
    assert.equal((await tool.execute({name},{signal:new AbortController().signal})).name,name);}
  assert.equal(definitions.filter(x=>!x.invocation.modelInvocable).length,36,'legacy disabled methods remain disabled');
});

test('research adapters retain pinned originals, Apache license, local links and real tool names',()=>{
  const manifest=json('sources/legal-research-cn.json'),labels=json('config/skill-labels.zh-CN.json').labels;
  assert.equal(manifest.commit,'59f37f1c8851b8277e24f7a45f4e773bee97bab9');assert.equal(manifest.license,'Apache-2.0');
  const tools=new Set(json('plugins/lazy-mcp/catalogs/qx_legal.json').tools.map(x=>'mcp__qx_legal__'+x.name));
  for(const row of manifest.files){const bytes=fs.readFileSync(path.join(root,'workspace-seed',row.path));assert.equal(sha(bytes),row.sha256);
    assert.equal(createHash('sha1').update(Buffer.concat([Buffer.from('blob '+bytes.length+'\0'),bytes])).digest('hex'),row.gitBlobSha);}
  assert.match(fs.readFileSync(path.join(root,'workspace-seed',manifest.licensePath),'utf8'),/Apache License[\s\S]*Version 2\.0/);
  const common=fs.readFileSync(path.join(root,'workspace-seed/legal-library/workbench/legal-research.md'),'utf8');
  for(const name of names){
    const relative='.dsh/skills/'+name+'/SKILL.md',body=fs.readFileSync(path.join(root,'workspace-seed',relative),'utf8');
    assert.equal(body,fs.readFileSync(path.join(root,'config/skills',name,'SKILL.md'),'utf8'));assert.ok(labels[name]);
    for(const match of (body+'\n'+common).matchAll(/mcp__qx_legal__[a-z_]+/g))assert.ok(tools.has(match[0]),match[0]);
    for(const match of body.matchAll(/\]\(((?:legal-library|\.dsh)\/[^)]+)\)/g))assert.ok(fs.existsSync(path.join(root,'workspace-seed',match[1])),match[1]);
    assert.match(body,/已修改|适配/);assert.match(body,/CSlawyer/);
  }
  for(const field of ['original','title','issuer','article','caseNo','factDate','researchDate','region','version','effect','applicability','evidence','unresolved'])assert.match(common,new RegExp('`'+field+'`'));
  for(const state of ['已核验','部分核验','未核验','不适用'])assert.ok(common.includes(state));
  assert.match(common,/matched[\s\S]*法律/);assert.match(common,/未知[\s\S]*否定/);
  assert.match(common,/legal_search_read/);assert.match(common,/web_fetch/);
  const additions=json('config/practice-skill-additions.json');for(const name of names)assert.ok(additions.skills.includes(name));
  const catalog=json('workspace-seed/legal-library/skill-catalog.json');assert.deepEqual(catalog.research_adapters.map(x=>x.name),names);
});

test('normal installed initialization adds research methods without replacing custom or disabled methods',async t=>{
  const folder=temporary(t),payload=path.join(folder,'payload'),data=path.join(folder,'data');
  const write=(base,file,text)=>{const target=path.join(base,file);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,text);};
  for(const name of names){const relative='.dsh/skills/'+name+'/SKILL.md';write(path.join(payload,'workspace-seed'),relative,fs.readFileSync(path.join(root,'workspace-seed',relative)));}
  for(const name of ['legal-research.md'])write(path.join(payload,'workspace-seed'),'legal-library/workbench/'+name,fs.readFileSync(path.join(root,'workspace-seed/legal-library/workbench',name)));
  const custom='---\nname: qx-authority-check\ndescription: 律师自定义\ndisable-model-invocation: true\nuser-invocable: false\n---\n保留人工规则。\n';
  write(path.join(data,'workspace'),'.dsh/skills/qx-authority-check/SKILL.md',custom);
  write(path.join(data,'workspace'),'.dsh/skills/my-method/SKILL.md','---\nname: my-method\ndescription: 自有方法\n---\n人工内容\n');
  write(path.join(payload,'workspace-seed'),'AGENTS.md','## 本机律所知识库\n合成规则\nContract: new\n');
  const contractFiles=['.dsh/skills/qx-contract-review/SKILL.md','.dsh/skills/qx-contract-review/references/method.md'];
  for(const file of contractFiles)write(path.join(payload,'workspace-seed'),file,file.endsWith('SKILL.md')?'---\nname: qx-contract-review\ndescription: 合成合同方法\n---\n合成内容\n':'合成参考');
  write(payload,'config/contract-0.2.0-defaults.json',JSON.stringify({files:Object.fromEntries(contractFiles.map(file=>[file,'0'.repeat(64)])),instructionPrefix:'Contract:',oldInstruction:'Contract: old'}));
  write(payload,'config/portable.json',JSON.stringify([{insert:[{id:'qx-knowledge-ui',name:'@APP@/plugins/knowledge/index.mjs'},{id:'qx-knowledge',name:'@deepseek-ai/dsh-mcp-client'},{id:'qx-upload-privacy',name:'@APP@/plugins/privacy/index.mjs'}]},{id:'llm-deepseek',config:{retryPolicy:{mode:'normal',maxRetries:5,retryableCodes:['MALFORMED_RESPONSE','STREAM_CLOSED']}}}]));
  write(payload,'config/profile-package.json','{}');write(payload,'config/profile-cordis.yml','[]');fs.mkdirSync(path.join(payload,'node_modules'));
  const {initialize}=require('../desktop/installed-runtime.cjs');initialize(payload,data);initialize(payload,data);
  const definitions=await discover(path.join(data,'workspace'),t),byName=new Map(definitions.map(x=>[x.name,x]));
  assert.equal(fs.readFileSync(path.join(data,'workspace/.dsh/skills/qx-authority-check/SKILL.md'),'utf8'),custom);
  assert.equal(byName.get('qx-authority-check').invocation.modelInvocable,false);assert.equal(byName.get('qx-authority-check').invocation.userInvocable,false);
  assert.match(byName.get('my-method').content,/人工内容/);
  for(const name of names.slice(1))assert.equal(byName.get(name).invocation.modelInvocable,true);
});
