const fs=require('node:fs/promises');
const {createReadStream}=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {spawn}=require('node:child_process');
const TOOL_HASHES={
  'hdiffz.exe':'f5ed7ac622a2daf4a31cc21ffa8ea1717f92323e79ef5ae695c5c9238a282f52',
  'hpatchz.exe':'9703c694b5955c576d9f0e26e98b60941f0bbb53b382b1f1988d75d461e580cb',
};
async function hash(file){const sum=createHash('sha256');for await(const chunk of createReadStream(file))sum.update(chunk);return sum.digest('hex');}
async function inventory(directory){
  const result=new Map(),queue=[''];
  for(let index=0;index<queue.length;index++){
    const relative=queue[index];
    for(const entry of await fs.readdir(path.join(directory,relative),{withFileTypes:true})){
      if(entry.isSymbolicLink())throw Error('Release tree contains a symbolic link');
      const name=relative?relative+'/'+entry.name:entry.name;
      if(entry.isDirectory())queue.push(name);
      else if(entry.isFile())result.set(name,{sha256:await hash(path.join(directory,name)),size:(await fs.stat(path.join(directory,name))).size});
      else throw Error('Unsupported release file type');
    }
  }
  return result;
}
async function run(file,args){
  await new Promise((resolve,reject)=>{
    const child=spawn(file,args,{windowsHide:true,stdio:['ignore','pipe','pipe']});let log='';
    child.stdout.on('data',b=>{log=(log+b).slice(-6000)});child.stderr.on('data',b=>{log=(log+b).slice(-6000)});
    child.once('error',reject);child.once('close',code=>code===0?resolve():reject(Error('HDiffPatch packaging failed ('+code+'): '+log)));
  });
}
async function prepareIncrementalPackage({oldDir,newDir,fromVersion,toVersion,output,toolsDir}){
  for(const version of [fromVersion,toVersion])if(!/^\d+\.\d+\.\d+$/.test(version))throw Error('Invalid release version');
  for(const [name,digest] of Object.entries(TOOL_HASHES))if(await hash(path.join(toolsDir,name))!==digest)throw Error('HDiffPatch tool checksum mismatch');
  await fs.mkdir(output,{recursive:true});
  const patchFile=path.join(output,'changes.hdiff'),planFile=path.join(output,'plan.json');
  for(const file of [patchFile,planFile]){try{await fs.access(file);throw Error('Use a new incremental output directory')}catch(error){if(error.code!=='ENOENT')throw error}}
  const [oldFiles,newFiles]=await Promise.all([inventory(oldDir),inventory(newDir)]);
  const marker='resources/app.asar';
  if(!oldFiles.has(marker)||!newFiles.has(marker))throw Error('Application marker missing');
  const changes=[];let unchangedFiles=0,unchangedBytes=0;
  for(const name of [...new Set([...oldFiles.keys(),...newFiles.keys()])].sort()){
    const previous=oldFiles.get(name),next=newFiles.get(name);
    if(previous?.sha256===next?.sha256){unchangedFiles++;unchangedBytes+=next.size;continue}
    changes.push({path:name,oldSha256:previous?.sha256||null,newSha256:next?.sha256||null});
  }
  if(!changes.length)throw Error('No changed files');
  const oldChanges=path.join(output,'old-changes'),newChanges=path.join(output,'new-changes');
  await fs.mkdir(oldChanges);await fs.mkdir(newChanges);
  for(const change of changes){
    for(const [source,target,exists] of [[oldDir,oldChanges,change.oldSha256],[newDir,newChanges,change.newSha256]]){
      if(!exists)continue;
      const destination=path.join(target,change.path);await fs.mkdir(path.dirname(destination),{recursive:true});
      await fs.copyFile(path.join(source,change.path),destination);
    }
  }
  await run(path.join(toolsDir,'hdiffz.exe'),['-s-64','-c-zstd-3','-C-xxh128',oldChanges,newChanges,patchFile]);
  const plan={schema:1,product:'cn.qunxing.harness.workbench',fromVersion,toVersion,patchSha256:await hash(patchFile),
    baseMarker:{path:marker,sha256:oldFiles.get(marker).sha256},targetMarker:{path:marker,sha256:newFiles.get(marker).sha256},changes,
    bootstrapNode:{oldSha256:oldFiles.get('resources/workbench/runtime/node.exe')?.sha256,newSha256:newFiles.get('resources/workbench/runtime/node.exe')?.sha256},
    stats:{oldFiles:oldFiles.size,newFiles:newFiles.size,unchangedFiles,unchangedBytes,changedFiles:changes.length,
      oldChangedBytes:changes.reduce((n,c)=>n+(oldFiles.get(c.path)?.size||0),0),newChangedBytes:changes.reduce((n,c)=>n+(newFiles.get(c.path)?.size||0),0),patchBytes:(await fs.stat(patchFile)).size}};
  await fs.writeFile(planFile,JSON.stringify(plan,null,2)+'\n');
  await fs.copyFile(path.join(toolsDir,'hpatchz.exe'),path.join(output,'hpatchz.exe'));
  return {planFile,patchFile,hpatchz:path.join(output,'hpatchz.exe'),stats:plan.stats};
}
module.exports={prepareIncrementalPackage,inventory,hash,TOOL_HASHES};
