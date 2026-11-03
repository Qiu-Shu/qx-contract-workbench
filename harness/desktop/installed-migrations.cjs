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
function knowledgeSection(text){
  const lines=text.split(/\r?\n/);let start=-1,end=lines.length,fence=null;
  for(let index=0;index<lines.length;index++){
    const code=lines[index].match(/^\s{0,3}(`{3,}|~{3,})/);
    if(code){if(!fence)fence=code[1];else if(code[1][0]===fence[0]&&code[1].length>=fence.length)fence=null;continue;}
    if(fence)continue;
    const heading=lines[index].match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if(!heading)continue;
    if(start>=0&&heading[1].length<=2){end=index;break;}
    if(heading[1]==='##'&&heading[2]===HEADING)start=index;
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
function migrateInstalled({data,portableConfig,seedInstructions,payload,yaml},{version,ids,withInstructions=false,providerOverride=false}){
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
  const section=withInstructions?knowledgeSection(seedInstructions||''):null;
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
  if(withInstructions&&!knowledgeSection(originalInstructions))changes.push({file:instructions,name:'AGENTS.md',original:originalInstructions,
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

module.exports={migrateInstalledKnowledge,migrateInstalledPrivacy,migrateInstalledContract,migrateInstalledModelRecovery};
