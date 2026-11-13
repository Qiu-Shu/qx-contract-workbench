const fs=require('node:fs'),path=require('node:path'),{createHash,randomUUID}=require('node:crypto');
const {execFile}=require('node:child_process');
const {normalized}=require('./data-location.cjs');
const ENGINE_SHA='b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830';
const ARCHIVE_SHA='da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d';
const URL='https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_windows_amd64.zip';
const fail=()=>Object.assign(Error('BACKUP_ENGINE_UNVERIFIED'),{code:'BACKUP_ENGINE_UNVERIFIED'});
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
function enginePath(anchor){return path.join(normalized(anchor),'.local/backup-runtime/restic.exe');}
function engineReady(anchor){try{const file=normalized(enginePath(anchor)),stat=fs.lstatSync(file);return stat.isFile()&&stat.nlink===1&&stat.size<64*1024*1024&&hash(fs.readFileSync(file))===ENGINE_SHA;}catch{return false;}}
async function prepareEngine({anchor,payload,fetcher=fetch,worker=path.join(payload,'bridge/backup_engine.py')}){
 if(engineReady(anchor))return;
 const file=enginePath(anchor),directory=normalized(path.dirname(file));fs.mkdirSync(directory,{recursive:true});normalized(directory);
 const archive=path.join(directory,randomUUID()+'.zip'),executable=path.join(directory,randomUUID()+'.exe');
 try{
  const response=await fetcher(URL,{signal:AbortSignal.timeout(120000),redirect:'follow'});if(!response.ok)throw fail();
  const chunks=[];let size=0;for await(const chunk of response.body){size+=chunk.length;if(size>12*1024*1024)throw fail();chunks.push(chunk);}
  const bytes=Buffer.concat(chunks);if(hash(bytes)!==ARCHIVE_SHA)throw fail();fs.writeFileSync(archive,bytes,{flag:'wx',mode:0o600});
  await new Promise((resolve,reject)=>execFile(path.join(payload,'runtime/python/python.exe'),['-I',worker,archive,executable],{windowsHide:true,timeout:30000,maxBuffer:65536},error=>error?reject(fail()):resolve()));
  if(hash(fs.readFileSync(executable))!==ENGINE_SHA)throw fail();normalized(file);
  if(fs.existsSync(file)){const stat=fs.lstatSync(file);if(!stat.isFile()||stat.nlink!==1)throw fail();}
  fs.renameSync(executable,file);
 }finally{for(const owned of [archive,executable]){try{fs.unlinkSync(owned);}catch(error){if(error.code!=='ENOENT')throw error;}}}
}
function findPgTools(data,payload){
 let expected;try{expected=JSON.parse(fs.readFileSync(path.join(payload,'config/postgres-backup-runtime.json'),'utf8')).files['bin/pg_controldata.exe'];}catch{return undefined;}
 const bases=[path.join(data,'.local/case-memory-runtime/pg0/installation'),path.join(process.env.USERPROFILE||'', '.pg0/installation')];
 for(const base of bases){try{normalized(base);for(const name of fs.readdirSync(base).sort().reverse()){
  try{const root=normalized(path.join(base,name)),file=normalized(path.join(root,'bin/pg_controldata.exe')),stat=fs.lstatSync(file);if(stat.isFile()&&stat.nlink===1&&stat.size<64*1024*1024&&hash(fs.readFileSync(file))===expected)return root;}catch{}
 }}catch{}}
 return undefined; // The snapshot worker checks the full pinned tool inventory before execution.
}
module.exports={enginePath,engineReady,prepareEngine,findPgTools};
