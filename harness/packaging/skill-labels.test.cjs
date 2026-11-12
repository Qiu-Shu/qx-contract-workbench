const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const {createHash}=require('node:crypto');
const {copySkillLabels}=require('./stage.cjs');
const root=path.resolve(__dirname,'..');
const target='node_modules/@deepseek-ai/dsh-client-ui-skill/lib/client.js';
const source=path.join(root,'config/skill-labels.zh-CN.json');
function fixture(t){
  const base=fs.realpathSync(os.tmpdir()),payload=fs.mkdtempSync(path.join(base,'qx-research-labels-'));
  t.after(()=>{assert.equal(path.dirname(path.resolve(payload)),base);fs.rmSync(payload,{recursive:true,force:true});});
  fs.mkdirSync(path.dirname(path.join(payload,target)),{recursive:true});return payload;
}
function assertLabels(text){
  const mapping=text.match(/const qxSkillLabels = (\{[\s\S]*?\});/);assert.ok(mapping);
  const lookup=text.match(/const qxSkillLabel =[^;]+;/);assert.ok(lookup);
  const context={};vm.runInNewContext(mapping[0]+'\n'+lookup[0]+'\nthis.label=qxSkillLabel;',context);
  for(const [name,label] of Object.entries(JSON.parse(fs.readFileSync(source,'utf8')).labels))assert.equal(context.label(name),label);
  assert.equal(context.label('custom-unlisted'),'custom-unlisted');
}
test('packaging applies research Chinese names and records both catalog source and generated UI hash',t=>{
  const payload=fixture(t),file=path.join(payload,target),manifest=[];
  fs.writeFileSync(file,'/* keep UI */\nconst qxSkillLabels = {"existing":"已有名称"};\nconst qxSkillLabel = name => Object.hasOwn(qxSkillLabels, name) ? qxSkillLabels[name] : name;\n/* keep calls */');
  const result=copySkillLabels(source,payload,manifest),updated=fs.readFileSync(file,'utf8');
  assertLabels(updated);assert.match(updated,/"existing": "已有名称"/);assert.match(updated,/\/\* keep UI \*\/[\s\S]*\/\* keep calls \*\//);
  assert.equal(result.target,'resources/workbench/'+target);assert.equal(result.sha256,createHash('sha256').update(updated).digest('hex'));
  assert.equal(manifest[0].source,'config/skill-labels.zh-CN.json');
  assert.deepEqual(fs.readFileSync(path.join(payload,'config/skill-labels.zh-CN.json')),fs.readFileSync(source));
  assert.deepEqual(copySkillLabels(source,payload,[]),result,'repeating refresh is deterministic');
});
test('an unexpected upstream UI mapping fails before any payload modification',t=>{
  const payload=fixture(t),file=path.join(payload,target),before='upstream no longer has the expected label map';fs.writeFileSync(file,before);
  assert.throws(()=>copySkillLabels(source,payload,[]),/Skill label/);
  assert.equal(fs.readFileSync(file,'utf8'),before);assert.equal(fs.existsSync(path.join(payload,'config/skill-labels.zh-CN.json')),false);
});
test('source-install pnpm patch contains the same research labels as the package overlay',()=>{
  const patch=fs.readFileSync(path.join(root,'patches/@deepseek-ai__dsh-client-ui-skill@0.2.2-alpha.2.patch'),'utf8');
  const additions=patch.split('\n').filter(line=>line.startsWith('+')&&!line.startsWith('+++')).map(line=>line.slice(1)).join('\n');
  assertLabels(additions);
});
test('the real installed Harness Skill UI accepts the label overlay without changing surrounding code',t=>{
  const payload=fixture(t),file=path.join(payload,target);
  const shipped=fs.readFileSync(path.join(path.dirname(require.resolve('@deepseek-ai/dsh-client-ui-skill')),'client.js'),'utf8');
  fs.writeFileSync(file,shipped);copySkillLabels(source,payload,[]);const updated=fs.readFileSync(file,'utf8');assertLabels(updated);
  const withoutMap=text=>text.replace(/const qxSkillLabels = \{[\s\S]*?\};/,'const qxSkillLabels = {};');
  assert.equal(withoutMap(updated),withoutMap(shipped));
});
test('malformed label entries do not overwrite the UI or source catalog',t=>{
  const payload=fixture(t),file=path.join(payload,target),bad=path.join(payload,'bad-labels.json');
  fs.writeFileSync(file,'const qxSkillLabels = {};');
  for(const labels of [[],{'qx-method':false},{'../bad':'非法路径'}]){
    fs.writeFileSync(bad,JSON.stringify({version:1,labels}));
    assert.throws(()=>copySkillLabels(bad,payload,[]),/Invalid Skill label catalog/);
    assert.equal(fs.readFileSync(file,'utf8'),'const qxSkillLabels = {};');
  }
});
