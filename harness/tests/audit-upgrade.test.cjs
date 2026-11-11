const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const payload=process.env.QX_TEST_APP||path.resolve(path.dirname(process.execPath),'..');
const {initialize}=require(process.env.QX_TEST_RUNTIME||path.join(__dirname,'../desktop/installed-runtime.cjs'));
function skills(value,found=[]){if(!value||typeof value!=='object')return found;if(value.id==='skill-filesystem')found.push(value);for(const child of Object.values(value))skills(child,found);return found;}
function skillConfig(value){return Object.assign({},...skills(value).map(node=>node.config));}
function temporary(t,prefix){const root=fs.realpathSync.native(os.tmpdir()),data=fs.mkdtempSync(path.join(root,prefix));t.after(()=>{assert.equal(path.dirname(data),root);fs.rmSync(data,{recursive:true,force:true,maxRetries:3});});return data;}
function sourcePayload(t){
  const target=temporary(t,'qx-upgrade-payload-'),source=path.resolve(__dirname,'..');
  for(const [from,to] of [['packaging/payload-config','config'],['workspace-seed','workspace-seed'],['plugins/lazy-mcp','plugins/lazy-mcp']])fs.cpSync(path.join(source,from),path.join(target,to),{recursive:true});
  fs.symlinkSync(path.join(payload,'node_modules'),path.join(target,'node_modules'),'junction');
  fs.writeFileSync(path.join(target,'config/initialization.json'),JSON.stringify({schema:1,id:'a'.repeat(64)}));
  return target;
}
test('an existing profile receives the built-in skill root while retaining custom roots and disabled preferences',t=>{
  const data=temporary(t,'律所 升级路径-'),payload=sourcePayload(t);
  initialize(payload,data);
  const file=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),config=JSON.parse(fs.readFileSync(file,'utf8')),node=skills(config).at(-1);
  assert.ok(node);node.config={...node.config,customSkillDirs:[path.join(data,'自定义技能')],disabledSkills:['synthetic-disabled']};
  fs.writeFileSync(file,JSON.stringify(config));
  const marker=path.join(data,'.local/initialized-payload.json'),previous=JSON.parse(fs.readFileSync(marker,'utf8'));previous.schema=1;fs.writeFileSync(marker,JSON.stringify(previous));
  initialize(payload,data);
  const after=skillConfig(JSON.parse(fs.readFileSync(file,'utf8')));
  assert.ok(after.customSkillDirs.some(root=>path.resolve(root)===path.join(data,'workspace/.dsh/skills')),'upgrade must register the bundled skills root even with an existing profile and unchanged payload marker');
  assert.ok(after.customSkillDirs.includes(path.join(data,'自定义技能')));assert.deepEqual(after.disabledSkills,['synthetic-disabled']);
  const stable=fs.readFileSync(file,'utf8');assert.equal(initialize(payload,data).status,'unchanged');assert.equal(fs.readFileSync(file,'utf8'),stable);
});
test('YAML migration preserves disabled provider and expression data without evaluating it',t=>{
  const {migrateInstalledSkillRoots}=require('../desktop/installed-migrations.cjs'),data=temporary(t,'yaml upgrade-');
  const file=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');fs.mkdirSync(path.dirname(file),{recursive:true});
  fs.writeFileSync(file,'- id: skill-filesystem\n  disabled: true\n  name: "@deepseek-ai/dsh-skill-filesystem"\n  config:\n    customSkillDirs:\n      - custom-skills\n    synthetic: !!js forbidden()\n');
  const options={data,payload,portableConfig:[{id:'skill-filesystem',config:{customSkillDirs:[path.join(data,'workspace/.dsh/skills')]}}]};
  assert.equal(migrateInstalledSkillRoots(options).status,'applied');const content=fs.readFileSync(file,'utf8');assert.match(content,/disabled: true/);assert.match(content,/custom-skills/);assert.match(content,/forbidden\(\)/);assert.equal(migrateInstalledSkillRoots(options).status,'unchanged');
});
test('forcing initialization still upgrades a preexisting profile instead of relying only on the fresh template',t=>{
  const data=temporary(t,'existing office-'),payload=sourcePayload(t);initialize(payload,data);
  const file=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),config=JSON.parse(fs.readFileSync(file,'utf8'));
  for(const node of skills(config))if(node.config)delete node.config.customSkillDirs;
  assert.equal(skillConfig(config).customSkillDirs,undefined);fs.writeFileSync(file,JSON.stringify(config));
  const marker=path.join(data,'.local/initialized-payload.json');fs.unlinkSync(marker);
  initialize(payload,data);const roots=skillConfig(JSON.parse(fs.readFileSync(file,'utf8'))).customSkillDirs;
  assert.ok(roots?.some(root=>path.resolve(root)===path.join(data,'workspace/.dsh/skills')),'existing configuration needs an explicit migration');
});
