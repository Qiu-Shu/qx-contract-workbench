const fs=require('node:fs');
const path=require('node:path');
const {randomUUID,createHash}=require('node:crypto');
const {createRequire}=require('node:module');
const {isDeepStrictEqual}=require('node:util');

const HEADING='本机律所知识库';

function bundledYaml(payload){
  if(!payload)throw new Error('Existing YAML configuration requires the bundled YAML parser.');
  return createRequire(fs.realpathSync(path.join(payload,'node_modules/@deepseek-ai/dsh/package.json')))('js-yaml');
}
function findIds(value,found=new Map(),seen=new Set()){
  if(!value||typeof value!=='object'||seen.has(value))return found;
  seen.add(value);
  if(typeof value.id==='string')found.set(value.id,value);
  for(const item of Object.values(value))findIds(item,found,seen);
  return found;
}
function providerConfig(value,id){
  let merged={};const seen=new Set();
  const visit=node=>{
    if(!node||typeof node!=='object'||seen.has(node))return;
    seen.add(node);
    if(node.id===id&&node.config&&typeof node.config==='object'){
      const policy=node.config.retryPolicy;
      const combinedPolicy=policy&&typeof policy==='object'?{...merged.retryPolicy,...policy}:policy;
      merged={...merged,...node.config};
      if(policy!==undefined)merged.retryPolicy=combinedPolicy;
      return;
    }
    for(const child of Object.values(node))visit(child);
  };
  visit(value);return merged;
}
function knowledgeSection(text,sectionHeading=HEADING){
  const lines=text.split(/\r?\n/);let start=-1,end=lines.length,fence=null;
  for(let index=0;index<lines.length;index++){
    const code=lines[index].match(/^\s{0,3}(`{3,}|~{3,})/);
    if(code){if(!fence)fence=code[1];else if(code[1][0]===fence[0]&&code[1].length>=fence.length)fence=null;continue;}
    if(fence)continue;
    const heading=lines[index].match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if(!heading)continue;
    if(start>=0&&heading[1].length<=2){end=index;break;}
    if(heading[1]==='##'&&heading[2]===sectionHeading)start=index;
  }
  return start<0?null:lines.slice(start,end).join('\n').trimEnd()+'\n';
}
function assertNoLinks(root,target){
  const relative=path.relative(root,target);
  if(relative.startsWith('..')||path.isAbsolute(relative))throw new Error('Migration path is outside the application data directory.');
  let current=root;
  for(const part of relative.split(path.sep)){
    current=path.join(current,part);
    try{if(fs.lstatSync(current).isSymbolicLink())throw new Error('Migration refuses a linked configuration or backup path.');}
    catch(error){if(error.code!=='ENOENT')throw error;}
  }
}
function atomicWrite(file,contents){
  const temporary=path.join(path.dirname(file),`.${path.basename(file)}.${randomUUID()}.tmp`);
  let descriptor;
  try{
    descriptor=fs.openSync(temporary,'wx',0o600);
    fs.writeFileSync(descriptor,contents);fs.fsyncSync(descriptor);fs.closeSync(descriptor);descriptor=undefined;
    fs.renameSync(temporary,file);
  }finally{
    if(descriptor!==undefined)fs.closeSync(descriptor);
    try{fs.unlinkSync(temporary);}catch(error){if(error.code!=='ENOENT')throw error;}
  }
}

// Call after initial seeding, before launching dsh. Never inspect case files or history.
function migrateInstalled({data,portableConfig,seedInstructions,payload,yaml},{version,ids,withInstructions=false,providerOverride=false,sectionHeading=HEADING}){
  data=path.resolve(data);
  const migrationRoot=path.join(data,'.local/migrations');
  const marker=path.join(migrationRoot,`${version}.json`);
  const patch=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');
  const instructions=path.join(data,'workspace/AGENTS.md');
  for(const target of [marker,patch,...(withInstructions?[instructions]:[])])assertNoLinks(data,target);
  if(fs.existsSync(marker)){
    if(JSON.parse(fs.readFileSync(marker,'utf8')).version!==version)throw new Error('Invalid installed migration marker.');
    return {status:'already-applied',changedFiles:[]};
  }
  const desired=findIds(portableConfig);
  for(const id of ids)if(!desired.has(id)||(providerOverride?!Array.isArray(desired.get(id).config?.retryPolicy?.retryableCodes):typeof desired.get(id).name!=='string'))throw new Error(`Portable configuration is missing ${id}.`);
  const section=withInstructions?knowledgeSection(seedInstructions||'',sectionHeading):null;
  if(withInstructions&&!section)throw new Error('Portable instructions are missing the knowledge section.');
  const originalConfig=fs.readFileSync(patch,'utf8');
  const originalInstructions=withInstructions?fs.readFileSync(instructions,'utf8'):null;
  let current,json=true;
  try{current=JSON.parse(originalConfig.replace(/^\uFEFF/,''));}
  catch{
    json=false;yaml=yaml||bundledYaml(payload);
    try{current=yaml.load(originalConfig);}
    catch{throw new Error('Cannot migrate invalid installed configuration; user files were left unchanged.');}
  }
  if(!Array.isArray(current))throw new Error('Installed configuration must be a patch array; user files were left unchanged.');
  const present=findIds(current),missing=ids.filter(id=>!present.has(id)).map(id=>desired.get(id));
  let additions=missing.length?[{insert:missing}]:[];
  if(providerOverride){
    additions=[];
    for(const id of ids){
      const prior=providerConfig(current,id),policy=prior.retryPolicy||{},wanted=desired.get(id).config.retryPolicy;
      const retryPolicy={...wanted,...policy,retryableCodes:[...new Set([...wanted.retryableCodes,...(Array.isArray(policy.retryableCodes)?policy.retryableCodes:[])])]};
      if(!isDeepStrictEqual(policy,retryPolicy))additions.push({id,config:{...prior,retryPolicy}});
    }
  }
  const changes=[];
  if(additions.length){
    const next=[...current,...additions];let contents;
    if(json)contents=JSON.stringify(next,null,2)+'\n';
    else{
      // Keep ordinary YAML comments verbatim; unusual flow-style YAML is reserialized, with the exact original backed up.
      const block='\n'+yaml.dump(additions,{noRefs:true,lineWidth:-1});
      const terminator=originalConfig.match(/^\.\.\.[ \t]*(?:#[^\r\n]*)?(?:\r?\n)?\s*$/m);
      const offset=terminator?terminator.index:originalConfig.length;
      contents=originalConfig.slice(0,offset).replace(/\s*$/,'')+'\n'+block+originalConfig.slice(offset);
      try{if(!isDeepStrictEqual(yaml.load(contents),next))contents=null;}catch{contents=null;}
      if(contents===null)contents=yaml.dump(next,{noRefs:true,lineWidth:-1});
    }
    changes.push({file:patch,name:'cordis.patch.yml',original:originalConfig,contents,relative:'.local/dsh-home/profiles/web/cordis.patch.yml'});
  }
  if(withInstructions&&!knowledgeSection(originalInstructions,sectionHeading))changes.push({file:instructions,name:'AGENTS.md',original:originalInstructions,
    contents:originalInstructions+(originalInstructions.endsWith('\n')?'\n':'\n\n')+section,relative:'workspace/AGENTS.md'});

  let backupDirectory=null;
  fs.mkdirSync(migrationRoot,{recursive:true});
  if(changes.length){
    backupDirectory=path.join(migrationRoot,`${version}-${randomUUID()}`);
    fs.mkdirSync(backupDirectory);
    // Every original is durable before replacing anything. A partial run is safe to resume because additions are idempotent.
    for(const change of changes)atomicWrite(path.join(backupDirectory,change.name),change.original);
    for(const change of changes){
      assertNoLinks(data,change.file);
      if(fs.readFileSync(change.file,'utf8')!==change.original)throw new Error('Configuration changed during upgrade; retry after closing other editors. Original files are backed up.');
      atomicWrite(change.file,change.contents);
    }
  }
  const changedFiles=changes.map(change=>change.relative);
  atomicWrite(marker,JSON.stringify({version,completedAt:new Date().toISOString(),backupDirectory,changedFiles},null,2)+'\n');
  return {status:'applied',backupDirectory,changedFiles};
}

function migrateInstalledKnowledge(options){
  return migrateInstalled(options,{version:'knowledge-v1',ids:['qx-knowledge-ui','qx-knowledge'],withInstructions:true});
}
function migrateInstalledPrivacy(options){
  return migrateInstalled(options,{version:'upload-privacy-v1',ids:['qx-upload-privacy']});
}
function migrateInstalledCaseMemory(options){
  const desired=findIds(options.portableConfig);
  if(!desired.has('qx-case-memory-ui')||!desired.has('qx-case-memory'))return {status:'deferred',changedFiles:[]};
  return migrateInstalled(options,{version:'case-memory-v1',ids:['qx-case-memory-ui','qx-case-memory'],withInstructions:true,sectionHeading:'案件记忆'});
}
function migrateInstalledLegalSearch(options){
  // Optional capability: an older/partial payload must not block the workbench.
  if(!findIds(options.portableConfig).has('qx-legal-search'))return {status:'deferred',changedFiles:[]};
  // A self-contained extension survives installation of a concurrently prepared
  // older package. New packages refresh only these application-owned code files.
  const {payload,data}=options;
  if(payload&&fs.existsSync(path.join(payload,'plugins/legal-search/index.mjs'))){
    const root=path.join(data,'.local/legal-search-runtime');
    for(const relative of ['plugins/legal-search/index.mjs','plugins/legal-search/core.mjs','bridge/legal_search_fallback.py','bridge/vendor/union_search']){
      const target=path.join(root,relative);assertNoLinks(path.resolve(data),path.resolve(target));
      fs.mkdirSync(path.dirname(target),{recursive:true});
      fs.cpSync(path.join(payload,relative),target,{recursive:true,force:true,filter:source=>!source.includes('__pycache__')});
    }
  }
  return migrateInstalled(options,{version:'legal-search-v1',ids:['qx-legal-search']});
}
function migrateInstalledModelRecovery(options){
  return migrateInstalled(options,{version:'model-recovery-v1',ids:['llm-deepseek'],providerOverride:true});
}

function migrateInstalledContract({data,payload}){
  data=path.resolve(data);
  const version='contract-delivery-v1',migrationRoot=path.join(data,'.local/migrations');
  const marker=path.join(migrationRoot,version+'.json');
  assertNoLinks(data,marker);
  if(fs.existsSync(marker)){
    if(JSON.parse(fs.readFileSync(marker,'utf8')).version!==version)throw Error('Invalid contract migration marker.');
    return {status:'already-applied',changedFiles:[]};
  }
  const defaults=JSON.parse(fs.readFileSync(path.join(payload,'config/contract-0.2.0-defaults.json'),'utf8'));
  const seed=path.join(payload,'workspace-seed'),workspace=path.join(data,'workspace');
  const changes=[],preservedCustom=[];
  for(const relative of ['.dsh/skills/qx-contract-review/SKILL.md','.dsh/skills/qx-contract-review/references/method.md']){
    if(!/^[a-f0-9]{64}$/.test(defaults.files[relative]))throw Error('Invalid released contract defaults.');
    const file=path.join(workspace,relative);assertNoLinks(data,file);
    const original=fs.readFileSync(file),contents=fs.readFileSync(path.join(seed,relative));
    if(original.equals(contents))continue;
    if(createHash('sha256').update(original).digest('hex')===defaults.files[relative])changes.push({file,relative,original,contents});
    else preservedCustom.push(relative);
  }
  const file=path.join(workspace,'AGENTS.md');assertNoLinks(data,file);
  const original=fs.readFileSync(file,'utf8');
  const nextLine=fs.readFileSync(path.join(seed,'AGENTS.md'),'utf8').split(/\r?\n/).find(line=>line.startsWith(defaults.instructionPrefix));
  if(!nextLine||!defaults.oldInstruction)throw Error('Contract instructions missing from package.');
  const contents=original.split('\n').map(line=>line.replace(/\r$/,'')===defaults.oldInstruction?nextLine+(line.endsWith('\r')?'\r':''):line).join('\n');
  if(contents!==original)changes.push({file,relative:'AGENTS.md',original,contents});
  fs.mkdirSync(migrationRoot,{recursive:true});
  let backupDirectory=null;
  if(changes.length){
    backupDirectory=path.join(migrationRoot,version+'-'+randomUUID());fs.mkdirSync(backupDirectory);
    for(const change of changes)atomicWrite(path.join(backupDirectory,change.relative.replaceAll('/','__')),change.original);
    for(const change of changes){
      assertNoLinks(data,change.file);
      if(!fs.readFileSync(change.file).equals(Buffer.from(change.original)))throw Error('Contract settings changed during upgrade. Originals are backed up.');
      atomicWrite(change.file,change.contents);
    }
  }
  const changedFiles=changes.map(change=>change.relative);
  atomicWrite(marker,JSON.stringify({version,completedAt:new Date().toISOString(),backupDirectory,changedFiles,preservedCustom},null,2)+'\n');
  return {status:'applied',backupDirectory,changedFiles,preservedCustom};
}

function migrateInstalledSkillFixes({data,payload}){
  const defaults={
    '.dsh/skills/impeccable/SKILL.md':'fab04b31f946573b00a8559db1fc070f8ea5825254d491c2b13156e5661a86d7',
    '.dsh/skills/windows-desktop/SKILL.md':'8869f57ed29b3368bcdbbb9ef71d9a87eae929e882f01c5bc346cc36cf8e64a8',
  };
  return migrateSkillFiles({data,payload},{version:'skill-tool-fixes-v1',defaults});
}

function migrateInstalledSkillQuality(options){
  const manifest=path.join(options.payload,'config/skill-quality-upgrades.json');
  if(!fs.existsSync(manifest))return {status:'deferred',changedFiles:[]};
  const spec=JSON.parse(fs.readFileSync(manifest,'utf8'));
  if(!['skill-quality-v1','skill-quality-v2','skill-quality-v3'].includes(spec.version)||!Array.isArray(spec.files))throw new Error('Invalid Skill quality upgrade manifest.');
  const required=['legal-library/workbench/practice-context.md','legal-library/workbench/source-verification.md'];
  if(spec.version!=='skill-quality-v1')required.push('legal-library/workbench/skill-status.md');
  if(!Array.isArray(spec.resources)||spec.resources.length!==required.length||new Set(spec.resources.map(r=>r.path)).size!==required.length)throw new Error('Invalid Skill quality resources.');
  for(const row of spec.resources){
    if(!required.includes(row.path)||!/^[a-f0-9]{64}$/.test(row.sha256))throw new Error('Invalid Skill quality resource.');
    const seed=path.join(options.payload,'workspace-seed',row.path),installed=path.join(options.data,'workspace',row.path);
    assertNoLinks(path.resolve(options.payload),path.resolve(seed));assertNoLinks(path.resolve(options.data),path.resolve(installed));
    if(!fs.existsSync(seed)||!fs.existsSync(installed)||!fs.statSync(installed).isFile()||createHash('sha256').update(fs.readFileSync(seed)).digest('hex')!==row.sha256)return {status:'deferred',changedFiles:[]};
  }
  const defaults={},targets={};
  for(const row of spec.files){
    if(!/^\.dsh\/skills\/[a-z0-9-]+\/(?:[a-zA-Z0-9_.-]+\/)*[a-zA-Z0-9_.-]+$/.test(row.path)||row.path.split('/').some(p=>p==='..'||p==='.')||defaults[row.path]||
      !Array.isArray(row.previousSha256)||!row.previousSha256.length||!row.previousSha256.every(h=>/^[a-f0-9]{64}$/.test(h))||!/^[a-f0-9]{64}$/.test(row.sha256))throw new Error('Invalid Skill quality upgrade entry.');
    defaults[row.path]=row.previousSha256;targets[row.path]=row.sha256;
  }
  const files=migrateSkillFiles(options,{version:spec.version,defaults,targets});
  if(files.status==='deferred')return files;
  const sectionHeading=spec.version==='skill-quality-v3'?'实务专项替代方法':spec.version==='skill-quality-v2'?'Skill 调用与停用':'Skill 质量与法源核验';
  if(!knowledgeSection(options.seedInstructions||'',sectionHeading))return {...files,status:'deferred'};
  // v2 also seeds v1 guidance for people upgrading directly from a released build.
  if(spec.version!=='skill-quality-v1'&&knowledgeSection(options.seedInstructions||'','Skill 质量与法源核验'))migrateInstalled(options,{version:'skill-quality-instructions-v1',ids:[],withInstructions:true,sectionHeading:'Skill 质量与法源核验'});
  if(spec.version==='skill-quality-v3'&&knowledgeSection(options.seedInstructions||'','Skill 调用与停用'))migrateInstalled(options,{version:'skill-quality-instructions-v2',ids:[],withInstructions:true,sectionHeading:'Skill 调用与停用'});
  const instructions=migrateInstalled(options,{version:spec.version.replace('quality-','quality-instructions-'),ids:[],withInstructions:true,sectionHeading});
  return {...files,instructions};
}

function migrateSkillFiles({data,payload},{version,defaults,targets={}}){
  data=path.resolve(data);
  const migrationRoot=path.join(data,'.local/migrations'),marker=path.join(migrationRoot,version+'.json');
  assertNoLinks(data,marker);
  if(fs.existsSync(marker))return {status:'already-applied',changedFiles:[]};
  const changes=[],preservedCustom=[],pending=[];
  for(const [relative,hash] of Object.entries(defaults)){
    const file=path.join(data,'workspace',relative),seed=path.join(payload,'workspace-seed',relative);
    assertNoLinks(data,file);
    if(!fs.existsSync(file))continue;
    if(!fs.existsSync(seed)){pending.push(relative);continue;}
    const original=fs.readFileSync(file),contents=fs.readFileSync(seed);
    if(targets[relative]&&createHash('sha256').update(contents).digest('hex')!==targets[relative]){pending.push(relative);continue;}
    if(original.equals(contents))continue;
    if([hash].flat().includes(createHash('sha256').update(original).digest('hex')))changes.push({file,relative,original,contents});
    else preservedCustom.push(relative);
  }
  fs.mkdirSync(migrationRoot,{recursive:true});
  let backupDirectory=null;
  const changedFiles=[];
  if(changes.length){
    backupDirectory=path.join(migrationRoot,version+'-'+randomUUID());
    assertNoLinks(data,backupDirectory);fs.mkdirSync(backupDirectory);
    for(const change of changes)atomicWrite(path.join(backupDirectory,change.relative.replaceAll('/','__')),change.original);
    for(const change of changes){
      assertNoLinks(data,change.file);
      // An editor may have changed a default since it was read. Preserve it too.
      if(!fs.existsSync(change.file)||!fs.readFileSync(change.file).equals(change.original)){
        preservedCustom.push(change.relative);continue;
      }
      atomicWrite(change.file,change.contents);changedFiles.push(change.relative);
    }
  }
  // A partial package must not block startup or prevent a later complete package from retrying.
  if(!pending.length)atomicWrite(marker,JSON.stringify({version,completedAt:new Date().toISOString(),backupDirectory,changedFiles,preservedCustom},null,2)+'\n');
  return {status:pending.length?'deferred':'applied',backupDirectory,changedFiles,preservedCustom};
}

module.exports={migrateInstalledKnowledge,migrateInstalledPrivacy,migrateInstalledContract,migrateInstalledModelRecovery,migrateInstalledSkillFixes,migrateInstalledSkillQuality,migrateInstalledLegalSearch,migrateInstalledCaseMemory};
