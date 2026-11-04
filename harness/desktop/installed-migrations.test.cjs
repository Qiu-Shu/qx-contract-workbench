const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {createRequire}=require('node:module');
const yaml=createRequire(fs.realpathSync(path.join(__dirname,'../node_modules/@deepseek-ai/dsh/package.json')))('js-yaml');
const {migrateInstalledKnowledge,migrateInstalledPrivacy,migrateInstalledModelRecovery,migrateInstalledCaseMemory}=require('./installed-migrations.cjs');
const portableConfig=[{insert:[{id:'qx-knowledge-ui',name:'app/knowledge',config:{workspace:'data/workspace'}},{id:'qx-knowledge',name:'mcp',config:{command:'app/python.exe'}}]}];
const privacyConfig=[{insert:[{id:'qx-upload-privacy',name:'app/privacy',config:{workspace:'data/workspace',enabled:true}}]}];
const recoveryConfig=[{id:'llm-deepseek',config:{retryPolicy:{mode:'normal',maxRetries:5,retryableCodes:['TIMEOUT','MALFORMED_RESPONSE','STREAM_CLOSED']}}}];
const seedInstructions='# Workbench\n\n## 本机律所知识库\n\nOnly explicitly uploaded documents.\n\n## Other\nNot copied.\n';
test('case memory migration is independent and preserves disabled plugins and customized rules',t=>{
  const memoryConfig=[{insert:[{id:'qx-case-memory-ui',name:'app/memory-ui'},{id:'qx-case-memory',name:'mcp'}]}];
  const f=fixture(t,'[{"id":"qx-case-memory","disabled":true}]');f.run();
  const before=fs.readFileSync(f.agents,'utf8');
  const options={data:f.data,portableConfig:memoryConfig,seedInstructions:'## 案件记忆\nOnly selected sources.\n## Next\nDo not copy.\n'};
  assert.equal(migrateInstalledCaseMemory(options).status,'applied');
  assert.equal(fs.readFileSync(f.agents,'utf8'),before+'\n## 案件记忆\nOnly selected sources.\n');
  const value=JSON.parse(fs.readFileSync(f.patch));assert.deepEqual(value[0],{id:'qx-case-memory',disabled:true});
  assert.deepEqual(value.at(-1),{insert:[memoryConfig[0].insert[0]]});
  assert.equal(migrateInstalledCaseMemory(options).status,'already-applied');
  const other=fixture(t,'[]','User rules\n## 案件记忆\nMy restrictions.\n');
  migrateInstalledCaseMemory({...options,data:other.data});assert.equal(fs.readFileSync(other.agents,'utf8'),'User rules\n## 案件记忆\nMy restrictions.\n');
});
function fixture(t,config,instructions='Custom lawyer instructions.\n'){
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx 迁移 '));
  t.after(()=>fs.rmSync(data,{recursive:true,force:true}));
  const patch=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');
  const agents=path.join(data,'workspace/AGENTS.md');
  fs.mkdirSync(path.dirname(patch),{recursive:true});fs.mkdirSync(path.dirname(agents),{recursive:true});
  fs.writeFileSync(patch,config);fs.writeFileSync(agents,instructions);
  return {data,patch,agents,run:()=>migrateInstalledKnowledge({data,portableConfig,seedInstructions,yaml})};
}

test('model recovery adds the actual provider override without changing existing unrelated settings',t=>{
  const f=fixture(t,'[{"id":"custom","disabled":true}]');
  const result=migrateInstalledModelRecovery({data:f.data,portableConfig:recoveryConfig});
  assert.deepEqual(JSON.parse(fs.readFileSync(f.patch,'utf8')),[{id:'custom',disabled:true},...recoveryConfig]);
  assert.equal(fs.readFileSync(path.join(result.backupDirectory,'cordis.patch.yml'),'utf8'),'[{"id":"custom","disabled":true}]');
  assert.equal(migrateInstalledModelRecovery({data:f.data,portableConfig:recoveryConfig}).status,'already-applied');
});

test('recovery merge preserves provider credentials, endpoint, custom limits, disabled flag and YAML comments',t=>{
  const source='# Personal provider\n- id: llm-deepseek\n  disabled: true\n  config:\n    apiKey: synthetic-only\n    baseURL: https://example.invalid\n    retryPolicy:\n      mode: normal\n      maxRetries: 2\n      retryableCodes: [TIMEOUT, CUSTOM]\n';
  const f=fixture(t,source);migrateInstalledModelRecovery({data:f.data,portableConfig:recoveryConfig,yaml});
  const text=fs.readFileSync(f.patch,'utf8');assert.ok(text.startsWith(source));
  const next=yaml.load(text);assert.deepEqual(next[0],yaml.load(source)[0]);
  assert.equal(next[1].config.apiKey,'synthetic-only');assert.equal(next[1].config.baseURL,'https://example.invalid');
  assert.equal(next[1].config.retryPolicy.maxRetries,2);assert.deepEqual(next[1].config.retryPolicy.retryableCodes,['TIMEOUT','MALFORMED_RESPONSE','STREAM_CLOSED','CUSTOM']);
});

test('recovery preserves user policy spread across multiple provider overrides',t=>{
  const current=[{id:'llm-deepseek',config:{apiKey:'synthetic',retryPolicy:{maxRetries:2,retryableCodes:['CUSTOM']}}},{id:'llm-deepseek',config:{baseURL:'https://example.invalid',retryPolicy:{mode:'normal'}}}];
  const f=fixture(t,JSON.stringify(current));migrateInstalledModelRecovery({data:f.data,portableConfig:recoveryConfig});
  const next=JSON.parse(fs.readFileSync(f.patch,'utf8'));assert.deepEqual(next.slice(0,2),current);
  assert.equal(next[2].config.retryPolicy.maxRetries,2);assert.ok(next[2].config.retryPolicy.retryableCodes.includes('CUSTOM'));
  assert.equal(next[2].config.apiKey,'synthetic');assert.equal(next[2].config.baseURL,'https://example.invalid');
});
test('old JSON upgrade preserves settings, disabled plugins, custom rules and exact backups',t=>{
  const original=JSON.stringify([{insert:[{id:'custom',config:{apiKey:'synthetic-key'}}]},{id:'qx-knowledge-ui',disabled:true}],null,2);
  const f=fixture(t,original);fs.writeFileSync(path.join(f.data,'workspace/client-history.txt'),'unchanged');
  const result=f.run();const current=JSON.parse(fs.readFileSync(f.patch,'utf8'));
  assert.deepEqual(current.slice(0,2),JSON.parse(original));
  assert.deepEqual(current[2],{insert:[portableConfig[0].insert[1]]});
  assert.equal(fs.readFileSync(path.join(result.backupDirectory,'cordis.patch.yml'),'utf8'),original);
  assert.equal(fs.readFileSync(path.join(result.backupDirectory,'AGENTS.md'),'utf8'),'Custom lawyer instructions.\n');
  assert.equal(fs.readFileSync(f.agents,'utf8'),'Custom lawyer instructions.\n\n## 本机律所知识库\n\nOnly explicitly uploaded documents.\n');
  assert.equal(fs.readFileSync(path.join(f.data,'workspace/client-history.txt'),'utf8'),'unchanged');
  const before=fs.readFileSync(f.patch);assert.equal(f.run().status,'already-applied');assert.deepEqual(fs.readFileSync(f.patch),before);
});
test('ordinary YAML comments, user overrides and document terminator survive upgrade',t=>{
  const source='# Personal configuration\n---\n- insert:\n    - id: custom\n      name: custom-plugin\n      config: {enabled: false}\n- id: qx-knowledge\n  disabled: true\n... # end\n';
  const f=fixture(t,source,'## 本机律所知识库\nCustom restrictions.\n');f.run();
  const next=fs.readFileSync(f.patch,'utf8');assert.ok(next.startsWith(source.slice(0,source.indexOf('...'))));
  assert.match(next,/\.\.\. # end/);assert.deepEqual(yaml.load(next).slice(0,2),yaml.load(source));
  assert.equal(yaml.load(next)[2].insert[0].id,'qx-knowledge-ui');
  assert.equal(fs.readFileSync(f.agents,'utf8'),'## 本机律所知识库\nCustom restrictions.\n');
});
test('malformed config aborts without changing rules or creating success marker',t=>{
  const f=fixture(t,'- insert: [broken');assert.throws(f.run,/configuration|配置/);
  assert.equal(fs.readFileSync(f.patch,'utf8'),'- insert: [broken');
  assert.equal(fs.readFileSync(f.agents,'utf8'),'Custom lawyer instructions.\n');
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/knowledge-v1.json')),false);
});
test('an interrupted migration can finish without duplicating existing additions',t=>{
  const f=fixture(t,JSON.stringify(portableConfig));const result=f.run();
  assert.deepEqual(result.changedFiles,['workspace/AGENTS.md']);
  assert.deepEqual(JSON.parse(fs.readFileSync(f.patch,'utf8')),portableConfig);
});
test('bad portable inputs fail before touching user files',t=>{
  const f=fixture(t,'[]');assert.throws(()=>migrateInstalledKnowledge({data:f.data,portableConfig:[],seedInstructions,yaml}),/qx-knowledge/);
  assert.equal(fs.readFileSync(f.patch,'utf8'),'[]');
});
test('completed migration does not re-enable plugins deliberately removed afterward',t=>{
  const f=fixture(t,'[]');f.run();fs.writeFileSync(f.patch,'[]');assert.equal(f.run().status,'already-applied');
  assert.equal(fs.readFileSync(f.patch,'utf8'),'[]');
});
test('flow-style YAML retains native setting types when it must be reserialized',t=>{
  const source='[{id: custom, config: {date: 2026-11-03, enabled: false}}]';
  const f=fixture(t,source);f.run();
  assert.deepEqual(yaml.load(fs.readFileSync(f.patch,'utf8'))[0],yaml.load(source)[0]);
});
test('privacy migration runs independently after knowledge-v1 and leaves instructions and old settings untouched',t=>{
  const f=fixture(t,'[{"id":"custom","config":{"chosenModel":"user-model"}}]');f.run();
  const before=fs.readFileSync(f.patch,'utf8'),instructions=fs.readFileSync(f.agents);
  const knowledgeMarker=fs.readFileSync(path.join(f.data,'.local/migrations/knowledge-v1.json'));
  const result=migrateInstalledPrivacy({data:f.data,portableConfig:privacyConfig});
  assert.equal(result.status,'applied');assert.deepEqual(result.changedFiles,['.local/dsh-home/profiles/web/cordis.patch.yml']);
  assert.deepEqual(JSON.parse(fs.readFileSync(f.patch,'utf8')),[...JSON.parse(before),privacyConfig[0]]);
  assert.equal(fs.readFileSync(path.join(result.backupDirectory,'cordis.patch.yml'),'utf8'),before);
  assert.deepEqual(fs.readFileSync(f.agents),instructions);
  assert.deepEqual(fs.readFileSync(path.join(f.data,'.local/migrations/knowledge-v1.json')),knowledgeMarker);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.data,'.local/migrations/upload-privacy-v1.json'))).version,'upload-privacy-v1');
  const migrated=fs.readFileSync(f.patch);assert.equal(migrateInstalledPrivacy({data:f.data,portableConfig:privacyConfig}).status,'already-applied');
  assert.deepEqual(fs.readFileSync(f.patch),migrated);
});
test('privacy migration preserves disabled YAML entries and customized settings without requiring instructions',t=>{
  const original='# Keep my privacy choice\n- id: qx-upload-privacy\n  disabled: true\n  config:\n    mode: my-custom-mode\n';
  const f=fixture(t,original);fs.unlinkSync(f.agents);
  const result=migrateInstalledPrivacy({data:f.data,portableConfig:privacyConfig,yaml});
  assert.deepEqual(result.changedFiles,[]);assert.equal(result.backupDirectory,null);
  assert.equal(fs.readFileSync(f.patch,'utf8'),original);assert.equal(fs.existsSync(f.agents),false);
});
test('privacy migration rejects malformed config and incomplete portable input without success marker',t=>{
  const f=fixture(t,'- broken: [');
  assert.throws(()=>migrateInstalledPrivacy({data:f.data,portableConfig:privacyConfig,yaml}),/configuration/);
  assert.equal(fs.readFileSync(f.patch,'utf8'),'- broken: [');
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/upload-privacy-v1.json')),false);
  assert.throws(()=>migrateInstalledPrivacy({data:f.data,portableConfig:[],yaml}),/qx-upload-privacy/);
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/upload-privacy-v1.json')),false);
});
test('privacy replacement failure leaves exact backup and no success marker, then resumes safely',t=>{
  const f=fixture(t,'[]');const rename=fs.renameSync;
  const failure=t.mock.method(fs,'renameSync',(from,to)=>{if(to===f.patch)throw Object.assign(new Error('simulated locked settings'),{code:'EACCES'});return rename(from,to);});
  assert.throws(()=>migrateInstalledPrivacy({data:f.data,portableConfig:privacyConfig}),/simulated locked settings/);
  assert.equal(fs.readFileSync(f.patch,'utf8'),'[]');
  const migrations=path.join(f.data,'.local/migrations');
  assert.equal(fs.existsSync(path.join(migrations,'upload-privacy-v1.json')),false);
  const backup=fs.readdirSync(migrations).find(name=>name.startsWith('upload-privacy-v1-'));
  assert.equal(fs.readFileSync(path.join(migrations,backup,'cordis.patch.yml'),'utf8'),'[]');
  failure.mock.restore();
  assert.equal(migrateInstalledPrivacy({data:f.data,portableConfig:privacyConfig}).status,'applied');
  assert.deepEqual(JSON.parse(fs.readFileSync(f.patch,'utf8')),privacyConfig);
});
