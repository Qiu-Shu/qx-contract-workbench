const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {createLocalBackup,restoreLocalBackup}=require('./local-backup.cjs');
const {assertRestoreReviewed}=require('./installed-stop.cjs');
const enabled=process.platform==='win32'&&process.env.QX_BACKUP_CAPACITY==='1';
const root=process.env.QX_BACKUP_CAPACITY_EVIDENCE,volume=process.env.QX_BACKUP_TEST_VOLUME;
const python=process.env.QX_TEST_PYTHON,restic=process.env.QX_TEST_RESTIC;
const password='synthetic-capacity-passphrase-only-2026';
function write(file,value){fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,typeof value==='string'||Buffer.isBuffer(value)?value:JSON.stringify(value));}
function digest(file){const hash=crypto.createHash('sha256'),block=Buffer.alloc(1024*1024),fd=fs.openSync(file,'r');try{let n;while((n=fs.readSync(fd,block)))hash.update(block.subarray(0,n));}finally{fs.closeSync(fd);}return hash.digest('hex');}
function tree(folder){const values={};function visit(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const target=path.join(dir,entry.name);assert.equal(entry.isSymbolicLink(),false);if(entry.isDirectory())visit(target);else values[path.relative(folder,target)]={sha256:digest(target),mtimeNs:fs.statSync(target,{bigint:true}).mtimeNs.toString()};}}visit(folder);return values;}
function seed(name){const data=path.join(root,name);fs.mkdirSync(path.join(data,'workspace'),{recursive:true});write(path.join(data,'.local/initialized-payload.json'),{schema:2,data});write(path.join(data,'.local/runtime.json'),{hostPid:null,launcherPid:123});write(path.join(data,'.local/host-state.json'),{phase:'stopped',hostPid:null,launcherPid:123});return data;}
function randomFile(file,megabytes){fs.mkdirSync(path.dirname(file),{recursive:true});const fd=fs.openSync(file,'wx');try{for(let i=0;i<megabytes;i++)fs.writeSync(fd,crypto.randomBytes(1024*1024));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
function validateVolume(){
 assert.match(root,/^D:[\\/]CodexChecks[\\/]AI-Shixiong-resilience-20261113[\\/]root[\\/]capacity-[a-f0-9-]+$/i);
 assert.match(volume,/^[R-Z]:\\$/);const marker=JSON.parse(fs.readFileSync(path.join(volume,'.qx-capacity-test.json'),'utf8'));
 assert.equal(marker.syntheticOnly,true);assert.equal(path.resolve(marker.evidence),path.resolve(root));assert.equal(marker.image,path.join(root,'bounded-test-volume.vhdx'));
 const stat=fs.statfsSync(volume);assert.ok(stat.bsize*stat.blocks<=512*1024*1024&&stat.bsize*stat.blocks>128*1024*1024);
 return marker;
}
function fillVolume(){
 validateVolume();const filler=path.join(volume,'qx-capacity-filler.bin'),fd=fs.openSync(filler,'wx'),block=crypto.randomBytes(65536);let full=false;
 try{for(let i=0;i<8193;i++){try{fs.writeSync(fd,block);}catch(error){assert.equal(error.code,'ENOSPC');full=true;break;}}assert.equal(full,true,'must observe a real OS disk-full error');const size=fs.fstatSync(fd).size;assert.ok(size>4*1024*1024);fs.ftruncateSync(fd,size-4*1024*1024);}
 finally{fs.closeSync(fd);}
 return filler;
}
function stageNames(){return fs.readdirSync(volume).filter(name=>/^\.qx-(backup|restore)-/.test(name));}
test('real bounded NTFS disk exhaustion preserves source and permits backup and restore retry',{skip:!enabled,timeout:600000},async()=>{
 const started=Date.now();validateVolume();const data=seed('disk-full-source');randomFile(path.join(data,'workspace/合成大附件.bin'),32);
 const before=tree(path.join(data,'workspace')),bundle=path.join(volume,'successful-backup');let filler=fillVolume(),backupError;
 try{await assert.rejects(createLocalBackup({data,bundle,python,restic,password}),error=>{backupError=error.code;return /^BACKUP_/.test(error.code);});assert.equal(fs.existsSync(bundle),false);assert.deepEqual(stageNames(),[]);assert.deepEqual(tree(path.join(data,'workspace')),before);}
 finally{fs.unlinkSync(filler);}
 const receipt=await createLocalBackup({data,bundle,python,restic,password});assert.equal(receipt.fileCount,1);const savedBefore=tree(bundle);
 const localBundle=path.join(root,'disk-full-backup-copy');fs.cpSync(bundle,localBundle,{recursive:true,preserveTimestamps:true});
 filler=fillVolume();const destination=path.join(volume,'successful-restore');let restoreError;
 try{await assert.rejects(restoreLocalBackup({bundle:localBundle,destination,python,restic,password}),error=>{restoreError=error.code;return /^BACKUP_/.test(error.code);});assert.equal(fs.existsSync(destination),false);assert.deepEqual(stageNames(),[]);assert.deepEqual(tree(bundle),savedBefore);assert.deepEqual(tree(path.join(data,'workspace')),before);}
 finally{fs.unlinkSync(filler);}
 await restoreLocalBackup({bundle:localBundle,destination,python,restic,password});assert.deepEqual(tree(path.join(destination,'workspace')),before);assert.throws(()=>assertRestoreReviewed(destination),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
 write(path.join(root,'disk-full-result.json'),{passed:true,nativeEnospcObserved:true,backupError,restoreError,sourceProtectedFiles:1,sourceBytes:32*1024*1024,oldBackupUnchanged:true,backupRetry:true,restoreRetry:true,restoredStillInactive:true,durationMs:Date.now()-started});
});
test('ten thousand files plus a 128 MiB attachment survive encrypted backup and restore',{skip:!enabled,timeout:900000},async()=>{
 const started=Date.now();validateVolume();const data=seed('many-files-source');
 for(let i=0;i<10000;i++){const content=Buffer.alloc(1024,46);content.write('独立虚构资料 '+i+'\n');write(path.join(data,'workspace','材料-'+Math.floor(i/500),'记录-'+i+'.txt'),content);}
 randomFile(path.join(data,'workspace/合成大附件.bin'),128);const before=tree(path.join(data,'workspace'));
 const bundle=path.join(root,'many-files-backup'),destination=path.join(root,'many-files-restored');
 const saved=await createLocalBackup({data,bundle,python,restic,password});assert.equal(saved.fileCount,10001);
 await restoreLocalBackup({bundle,destination,python,restic,password});assert.deepEqual(tree(path.join(destination,'workspace')),before);assert.deepEqual(tree(path.join(data,'workspace')),before);assert.throws(()=>assertRestoreReviewed(destination),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});
 write(path.join(root,'capacity-result.json'),{passed:true,files:10001,bytes:10000*1024+128*1024*1024,largestFileBytes:128*1024*1024,hashAndMtimeUnchanged:true,durationMs:Date.now()-started});
});
