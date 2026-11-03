const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {initialize,readRuntime,redactedLines}=require('./installed-runtime.cjs');
test('logs redact secrets split between chunks and on final flush',()=>{
  let output='';const key='sk-synthetic-sensitive';const sink=redactedLines(key,value=>output+=value);
  sink.push('prefix sk-synthetic-');sink.push('sensitive\nfinal sk-');sink.push('synthetic-sensitive');sink.end();
  assert.equal(output,'prefix [REDACTED]\nfinal [REDACTED]');assert.ok(!output.includes(key));
});
test('initialize Chinese/spaced path without overwriting user configuration or materials',()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'qx 安装 '));
  const payload=path.join(temp,'程序'),data=path.join(temp,'资料');
  fs.mkdirSync(path.join(payload,'config'),{recursive:true});fs.mkdirSync(path.join(payload,'node_modules'));
  fs.mkdirSync(path.join(payload,'workspace-seed/.dsh/skills'),{recursive:true});
  fs.writeFileSync(path.join(payload,'workspace-seed/AGENTS.md'),'seed\n\n## 本机律所知识库\n合成迁移规则。\nContract: new\n');
  const contractFiles=['.dsh/skills/qx-contract-review/SKILL.md','.dsh/skills/qx-contract-review/references/method.md'];
  for(const file of contractFiles){const target=path.join(payload,'workspace-seed',file);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,'new default')}
  fs.writeFileSync(path.join(payload,'config/contract-0.2.0-defaults.json'),JSON.stringify({files:Object.fromEntries(contractFiles.map(file=>[file,'0'.repeat(64)])),instructionPrefix:'Contract:',oldInstruction:'Contract: old'}));
  fs.writeFileSync(path.join(payload,'config/portable.json'),JSON.stringify([{path:'@APP@/bridge',workspace:'@DATA@/workspace',insert:[
    {id:'qx-knowledge-ui',name:'@APP@/plugins/knowledge/index.mjs'},
    {id:'qx-knowledge',name:'@deepseek-ai/dsh-mcp-client'},
    {id:'qx-upload-privacy',name:'@APP@/plugins/privacy/index.mjs'},
  ]},{id:'llm-deepseek',config:{retryPolicy:{mode:'normal',maxRetries:5,retryableCodes:['MALFORMED_RESPONSE','STREAM_CLOSED']}}}]));
  fs.writeFileSync(path.join(payload,'config/profile-package.json'),'{}');fs.writeFileSync(path.join(payload,'config/profile-cordis.yml'),'[]');
  try{
    initialize(payload,data);
    const patch=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');
    assert.match(fs.readFileSync(patch,'utf8'),/资料\/workspace/);assert.doesNotMatch(fs.readFileSync(patch,'utf8'),/@APP@|@DATA@/);
    fs.writeFileSync(patch,'user settings');fs.writeFileSync(path.join(data,'workspace/AGENTS.md'),'user @APP@ instructions');
    fs.writeFileSync(path.join(data,'workspace/客户.txt'),'synthetic');
    initialize(payload,data);
    assert.equal(fs.readFileSync(patch,'utf8'),'user settings');
    assert.equal(fs.readFileSync(path.join(data,'workspace/AGENTS.md'),'utf8'),'user @APP@ instructions');
    assert.equal(fs.readFileSync(path.join(data,'workspace/客户.txt'),'utf8'),'synthetic');
  }finally{fs.rmSync(temp,{recursive:true,force:true})}
});
test('missing runtime does not count as running',async()=>assert.equal(await readRuntime(path.join(os.tmpdir(),'qx-missing-runtime')),null));
