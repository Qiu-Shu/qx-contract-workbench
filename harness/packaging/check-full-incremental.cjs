// Exercise the real release plan in an isolated tree; never launch/register the app.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {hash}=require('./incremental-package.cjs');
const {applyUpdate,finalizeUpdate}=require('./incremental-install.cjs');
async function main(){
  const base=path.resolve(process.argv[2]),release=path.resolve(process.argv[3]);
  const parent=path.resolve(__dirname,'../.local/install-speed-check');
  assert.ok(base.startsWith(parent+path.sep));
  const out=path.join(parent,'full-apply-'+Date.now());fs.mkdirSync(out);
  const planFile=path.join(release,'incremental/plan.json');
  const plan=JSON.parse(fs.readFileSync(planFile,'utf8'));
  const changed=new Set(plan.changes.map(c=>c.path));
  const unchanged=[];let files=0;
  function copy(relative=''){
    for(const entry of fs.readdirSync(path.join(base,relative),{withFileTypes:true})){
      assert.ok(!entry.isSymbolicLink());
      const name=relative?relative+'/'+entry.name:entry.name;
      const target=path.join(out,name),source=path.join(base,name);
      if(entry.isDirectory()){fs.mkdirSync(target);copy(name);}
      else{
        assert.ok(entry.isFile());fs.linkSync(source,target);files++;
        if(!changed.has(name)){const stat=fs.statSync(target,{bigint:true});unchanged.push({name,ino:stat.ino,mtime:stat.mtimeNs,size:stat.size});}
      }
    }
  }
  copy();
  fs.writeFileSync(path.join(out,'用户保留文件.txt'),'preserve unmanaged data');
  console.log(JSON.stringify({stage:'prepared',files,unchangedFiles:unchanged.length}));
  const start=Date.now();
  const applied=await applyUpdate({installDir:out,planFile,patchFile:path.join(release,'incremental/changes.hdiff'),hpatchz:path.join(release,'incremental/hpatchz.exe')});
  const finalized=finalizeUpdate({installDir:out});
  const seconds=(Date.now()-start)/1000;
  for(const file of unchanged){const stat=fs.statSync(path.join(out,file.name),{bigint:true});assert.equal(stat.ino,file.ino);assert.equal(stat.mtimeNs,file.mtime);assert.equal(stat.size,file.size);}
  for(const change of plan.changes){
    if(change.newSha256)assert.equal(await hash(path.join(out,change.path)),change.newSha256);else assert.equal(fs.existsSync(path.join(out,change.path)),false);
    if(change.oldSha256)assert.equal(await hash(path.join(base,change.path)),change.oldSha256);
  }
  assert.equal(fs.readFileSync(path.join(out,'用户保留文件.txt'),'utf8'),'preserve unmanaged data');
  assert.equal(fs.existsSync(path.join(out,'.qx-update-transaction')),false);
  const report={passed:true,seconds,applied,finalized,stats:plan.stats,unchangedFileIdentitiesMtimesAndSizesVerified:unchanged.length,baselineChangedFileHashesPreserved:true,unmanagedFilePreserved:true,scope:'Real release patch on isolated full-size hardlinked baseline; no production installer execution',output:out};
  fs.writeFileSync(path.join(release,'full-incremental-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error);process.exit(1)});
