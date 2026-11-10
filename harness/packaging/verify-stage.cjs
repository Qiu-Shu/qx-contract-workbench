const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {inventory,hash}=require('./incremental-package.cjs');
const {load}=require('./toolchain.cjs');
const lock=require('./bootstrap.lock.json');
async function verifyBase(stage){
  const files=[...await inventory(path.join(stage,'base'))].sort(([a],[b])=>a<b?-1:a>b?1:0);
  if(createHash('sha256').update(JSON.stringify(files)).digest('hex')!==lock.treeSha256)throw Error('Stage base differs from the pinned official installer');
}
async function verifyUpgradeBases(stage){
  for(const item of lock.upgradeBases||[]){
    if(!/^\d+\.\d+\.\d+$/.test(item.version))throw Error('Invalid upgrade baseline');
    const files=[...await inventory(path.join(stage,'upgrade-bases',item.version))].sort(([a],[b])=>a<b?-1:a>b?1:0);
    if(createHash('sha256').update(JSON.stringify(files)).digest('hex')!==item.treeSha256)throw Error('Upgrade base differs from the pinned official installer: '+item.version);
  }
}
function child(root,relative){
  const result=path.resolve(root,relative);
  if(!result.startsWith(path.resolve(root)+path.sep))throw Error('Invalid source manifest path');
  return result;
}
async function verifySources(stage){
  const manifest=JSON.parse(fs.readFileSync(path.join(stage,'source-manifest.json'),'utf8'));
  const candidate=path.join(stage,'win-unpacked'),root=path.resolve(__dirname,'..'),asar=load('@electron/asar');
  for(const item of manifest.files){
    if(await hash(child(root,item.source))!==item.sha256)throw Error('Source changed after staging: '+item.source);
    const actual=item.target.startsWith('app.asar/')?createHash('sha256').update(asar.extractFile(path.join(candidate,'resources/app.asar'),item.target.slice(9))).digest('hex'):await hash(child(candidate,item.target));
    if(actual!==item.sha256)throw Error('Candidate differs from source: '+item.target);
  }
  for(const item of manifest.generated)if(await hash(child(candidate,item.target))!==item.sha256)throw Error('Generated candidate changed: '+item.target);
  // A staging directory is a release input, never a writable test installation.
  // Detect extra bytecode, logs, credentials and any modified inherited dependency.
  const expected=new Map([...await inventory(path.join(stage,'base'))].map(([name,info])=>[name,info.sha256]));
  for(const item of [...manifest.files,...manifest.generated])if(!item.target.startsWith('app.asar/'))expected.set(item.target,item.sha256);
  const actual=await inventory(candidate);
  if(actual.size!==expected.size)throw Error('Candidate contains missing or unexpected files; create a clean stage before packaging');
  for(const [name,info] of actual)if(expected.get(name)!==info.sha256)throw Error('Candidate dependency or generated file changed: '+name);
}
module.exports={verifyBase,verifyUpgradeBases,verifySources};
