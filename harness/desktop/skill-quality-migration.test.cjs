const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{createHash}=require('node:crypto');
const {migrateInstalledSkillQuality}=require('./installed-migrations.cjs');
const sha=s=>createHash('sha256').update(s).digest('hex');
test('candidate route repairs preserve recorded defaults and match current files',()=>{
 const project=path.resolve(__dirname,'..');
 const changes=JSON.parse(fs.readFileSync(path.join(project,'docs/checks/candidate-install/routes-changes.json'),'utf8')).changes;
 const spec=JSON.parse(fs.readFileSync(path.join(project,'config/skill-quality-upgrades.json'),'utf8'));
 for(const change of changes.filter(r=>r.path.startsWith('workspace/'))){
  const row=spec.files.find(r=>r.path===change.path.slice('workspace/'.length));assert.ok(row,change.path);
  assert.ok(row.previousSha256.includes(change.beforeSha256),change.path);
  if(row.sha256!==change.afterSha256)assert.ok(row.previousSha256.includes(change.afterSha256),change.path+' intermediate candidate');
  assert.equal(sha(fs.readFileSync(path.join(project,change.path))),row.sha256);
 }
});
function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-skill-quality-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const data=path.join(root,'data'),payload=path.join(root,'payload'),relative='.dsh/skills/example/SKILL.md';
 const file=path.join(data,'workspace',relative),seed=path.join(payload,'workspace-seed',relative),manifest=path.join(payload,'config/skill-quality-upgrades.json');
 for(const p of [file,seed,manifest,path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml')])fs.mkdirSync(path.dirname(p),{recursive:true});
 fs.writeFileSync(file,'old');fs.writeFileSync(seed,'new');fs.writeFileSync(path.join(data,'workspace/AGENTS.md'),'# User notes\nKeep this\n');fs.writeFileSync(path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),'[]');
 const resources=['practice-context.md','source-verification.md'].map(name=>({path:'legal-library/workbench/'+name,sha256:sha(name)}));
 for(const resource of resources)for(const dir of [path.join(payload,'workspace-seed'),path.join(data,'workspace')]){const file=path.join(dir,resource.path);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,path.basename(resource.path));}
 const spec={version:'skill-quality-v1',resources,files:[{path:relative,previousSha256:[sha('old'),sha('older')],sha256:sha('new')}]};
 fs.writeFileSync(manifest,JSON.stringify(spec));
 return {data,payload,file,seed,manifest,spec,run:()=>migrateInstalledSkillQuality({data,payload,portableConfig:[],seedInstructions:'# App\n\n## Skill 质量与法源核验\nNew rules\n\n## Skill 调用与停用\nLifecycle rules\n\n## 实务专项替代方法\nPractice rules\n'})};
}
test('known default updates with backup; custom instructions survive; restart is idempotent',t=>{
 const f=fixture(t),first=f.run();assert.equal(fs.readFileSync(f.file,'utf8'),'new');assert.equal(fs.readFileSync(path.join(first.backupDirectory,'.dsh__skills__example__SKILL.md'),'utf8'),'old');
 const notes=fs.readFileSync(path.join(f.data,'workspace/AGENTS.md'),'utf8');assert.match(notes,/Keep this/);assert.match(notes,/New rules/);assert.equal(f.run().status,'already-applied');
});
test('user edits are preserved, including an existing custom quality section',t=>{
 const f=fixture(t);fs.writeFileSync(f.file,'lawyer custom');const text='# User\n\n## Skill 质量与法源核验\nMy rules\n';fs.writeFileSync(path.join(f.data,'workspace/AGENTS.md'),text);
 assert.deepEqual(f.run().preservedCustom,[f.spec.files[0].path]);assert.equal(fs.readFileSync(f.file,'utf8'),'lawyer custom');assert.equal(fs.readFileSync(path.join(f.data,'workspace/AGENTS.md'),'utf8'),text);
});
test('partial and mismatched packages defer without recording completion, then retry',t=>{
 const f=fixture(t);fs.unlinkSync(f.seed);assert.equal(f.run().status,'deferred');fs.writeFileSync(f.seed,'wrong');assert.equal(f.run().status,'deferred');assert.equal(fs.readFileSync(f.file,'utf8'),'old');fs.writeFileSync(f.seed,'new');assert.equal(f.run().status,'applied');
});
test('manifest cannot name outside or ambiguous paths; deleted user skill is not recreated',t=>{
 const f=fixture(t);f.spec.files[0].path='.dsh/skills/example/../../outside';fs.writeFileSync(f.manifest,JSON.stringify(f.spec));assert.throws(()=>f.run(),/Invalid/);f.spec.files[0].path='.dsh/skills/example/SKILL.md';fs.writeFileSync(f.manifest,JSON.stringify(f.spec));fs.unlinkSync(f.file);assert.deepEqual(f.run().changedFiles,[]);assert.equal(fs.existsSync(f.file),false);
});
test('missing shared reference defers before any Skill or instructions are updated',t=>{
 const f=fixture(t),file=path.join(f.payload,'workspace-seed',f.spec.resources[0].path);fs.unlinkSync(file);assert.equal(f.run().status,'deferred');assert.equal(fs.readFileSync(f.file,'utf8'),'old');assert.doesNotMatch(fs.readFileSync(path.join(f.data,'workspace/AGENTS.md'),'utf8'),/New rules/);
 fs.writeFileSync(file,'practice-context.md');assert.equal(f.run().status,'applied');
});
test('v2 upgrades a known v1 default without being skipped by old completion markers',t=>{
 const f=fixture(t);assert.equal(f.run().status,'applied');
 const resource={path:'legal-library/workbench/skill-status.md',sha256:sha('lifecycle')};
 for(const dir of [path.join(f.payload,'workspace-seed'),path.join(f.data,'workspace')])fs.writeFileSync(path.join(dir,resource.path),'lifecycle');
 f.spec.version='skill-quality-v2';f.spec.resources.push(resource);f.spec.files[0].previousSha256.push(sha('new'));f.spec.files[0].sha256=sha('newer');
 fs.writeFileSync(f.seed,'newer');fs.writeFileSync(f.manifest,JSON.stringify(f.spec));
 const result=f.run();assert.equal(result.status,'applied');assert.equal(fs.readFileSync(f.file,'utf8'),'newer');
 assert.equal(fs.readFileSync(path.join(result.backupDirectory,'.dsh__skills__example__SKILL.md'),'utf8'),'new');
 const notes=fs.readFileSync(path.join(f.data,'workspace/AGENTS.md'),'utf8');assert.match(notes,/Keep this/);assert.match(notes,/Lifecycle rules/);
 assert.equal(f.run().status,'already-applied');
});
test('real manifest upgrades recorded defaults and preserves one lawyer edit',t=>{
 const project=path.resolve(__dirname,'..'),baseline=path.join(project,'docs/checks/skills-quality');
 if(!fs.existsSync(path.join(baseline,'backups/legal-before'))){t.skip('Local recorded baseline evidence unavailable');return;}
 const f=fixture(t),spec=JSON.parse(fs.readFileSync(path.join(project,'config/skill-quality-upgrades.json'),'utf8'));
 assert.ok(spec.files.length>=189);fs.writeFileSync(f.manifest,JSON.stringify(spec));
 for(const row of spec.resources){
  const body=fs.readFileSync(path.join(project,'workspace',row.path));assert.equal(sha(body),row.sha256);
  for(const dir of [path.join(f.payload,'workspace-seed'),path.join(f.data,'workspace')]){const file=path.join(dir,row.path);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,body);}
 }
 for(const row of spec.files){
  const before=[...['before-core','backups/legal-before'].map(dir=>path.join(baseline,dir,'workspace',row.path)),
    path.join(project,'docs/checks/candidate-install/routes-before/workspace',row.path)].find(p=>fs.existsSync(p));assert.ok(before,row.path);
  const old=fs.readFileSync(before),next=fs.readFileSync(path.join(project,'workspace',row.path));assert.ok(row.previousSha256.includes(sha(old)));assert.equal(sha(next),row.sha256);
  for(const [dir,body] of [[path.join(f.data,'workspace'),old],[path.join(f.payload,'workspace-seed'),next]]){const file=path.join(dir,row.path);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,body);}
 }
 const custom=spec.files[0].path;fs.writeFileSync(path.join(f.data,'workspace',custom),'Lawyer customization');const result=f.run();
 assert.equal(result.changedFiles.length,spec.files.length-1);assert.deepEqual(result.preservedCustom,[custom]);assert.equal(fs.readFileSync(path.join(f.data,'workspace',custom),'utf8'),'Lawyer customization');
 for(const relative of result.changedFiles)assert.equal(sha(fs.readFileSync(path.join(f.data,'workspace',relative))),spec.files.find(r=>r.path===relative).sha256);
});

test('v3 updates a v2 default once and adds practice guidance while preserving user sections',t=>{
 const f=fixture(t),resource={path:'legal-library/workbench/skill-status.md',sha256:sha('lifecycle')};
 for(const dir of [path.join(f.payload,'workspace-seed'),path.join(f.data,'workspace')])fs.writeFileSync(path.join(dir,resource.path),'lifecycle');
 f.spec.resources.push(resource);f.spec.version='skill-quality-v2';fs.writeFileSync(f.manifest,JSON.stringify(f.spec));f.run();
 f.spec.version='skill-quality-v3';f.spec.files[0].previousSha256.push(sha('new'));f.spec.files[0].sha256=sha('practice');
 fs.writeFileSync(f.seed,'practice');fs.writeFileSync(f.manifest,JSON.stringify(f.spec));
 const result=f.run();assert.equal(result.status,'applied');assert.equal(fs.readFileSync(f.file,'utf8'),'practice');
 const notes=fs.readFileSync(path.join(f.data,'workspace/AGENTS.md'),'utf8');assert.match(notes,/Keep this/);assert.match(notes,/Lifecycle rules/);assert.match(notes,/Practice rules/);
 assert.equal(fs.readFileSync(path.join(result.backupDirectory,'.dsh__skills__example__SKILL.md'),'utf8'),'new');assert.equal(f.run().status,'already-applied');
});
