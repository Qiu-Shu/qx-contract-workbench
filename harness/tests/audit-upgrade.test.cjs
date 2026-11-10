const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const payload=process.env.QX_TEST_APP||(process.env.QX_TEST_APP||path.resolve(path.dirname(process.execPath),'..'));
const {initialize}=require(process.env.QX_TEST_RUNTIME||path.join(__dirname,'../desktop/installed-runtime.cjs'));
function skill(value){if(value?.id==='skill-filesystem')return value;for(const child of Object.values(value||{})){if(child&&typeof child==='object'){const found=skill(child);if(found)return found;}}}
test('an existing profile receives the built-in skill root while retaining custom roots and disabled preferences',()=>{
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'律所 升级路径-'));
  initialize(payload,data);
  const file=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),config=JSON.parse(fs.readFileSync(file,'utf8')),node=skill(config);
  assert.ok(node);node.config.customSkillDirs=[path.join(data,'自定义技能')];node.config.disabledSkills=['synthetic-disabled'];
  fs.writeFileSync(file,JSON.stringify(config));
  const marker=path.join(data,'.local/initialized-payload.json'),previous=JSON.parse(fs.readFileSync(marker,'utf8'));previous.schema=1;fs.writeFileSync(marker,JSON.stringify(previous));
  initialize(payload,data);
  const after=skill(JSON.parse(fs.readFileSync(file,'utf8'))).config;
  assert.ok(after.customSkillDirs.some(root=>path.resolve(root)===path.join(data,'workspace/.dsh/skills')),'upgrade must register the bundled skills root even with an existing profile and unchanged payload marker');
  assert.ok(after.customSkillDirs.includes(path.join(data,'自定义技能')));assert.deepEqual(after.disabledSkills,['synthetic-disabled']);
  const stable=fs.readFileSync(file,'utf8');assert.equal(initialize(payload,data).status,'unchanged');assert.equal(fs.readFileSync(file,'utf8'),stable);
});
test('YAML migration preserves disabled provider and expression data without evaluating it',()=>{
  const {migrateInstalledSkillRoots}=require('../desktop/installed-migrations.cjs'),data=fs.mkdtempSync(path.join(os.tmpdir(),'yaml upgrade-'));
  const file=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');fs.mkdirSync(path.dirname(file),{recursive:true});
  fs.writeFileSync(file,'- id: skill-filesystem\n  disabled: true\n  name: "@deepseek-ai/dsh-skill-filesystem"\n  config:\n    customSkillDirs:\n      - custom-skills\n    synthetic: !!js forbidden()\n');
  const options={data,payload,portableConfig:[{id:'skill-filesystem',config:{customSkillDirs:[path.join(data,'workspace/.dsh/skills')]}}]};
  assert.equal(migrateInstalledSkillRoots(options).status,'applied');const content=fs.readFileSync(file,'utf8');assert.match(content,/disabled: true/);assert.match(content,/custom-skills/);assert.match(content,/forbidden\(\)/);assert.equal(migrateInstalledSkillRoots(options).status,'unchanged');
});
test('forcing initialization still upgrades a preexisting profile instead of relying only on the fresh template',()=>{
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'existing office-'));initialize(payload,data);
  const file=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),config=JSON.parse(fs.readFileSync(file,'utf8'));delete skill(config).config.customSkillDirs;fs.writeFileSync(file,JSON.stringify(config));
  const marker=path.join(data,'.local/initialized-payload.json');fs.unlinkSync(marker);
  initialize(payload,data);const roots=skill(JSON.parse(fs.readFileSync(file,'utf8'))).config.customSkillDirs;
  assert.ok(roots?.some(root=>path.resolve(root)===path.join(data,'workspace/.dsh/skills')),'existing configuration needs an explicit migration');
});
