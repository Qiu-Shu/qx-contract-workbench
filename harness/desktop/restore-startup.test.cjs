const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {assertRestoreReviewed}=require('./installed-stop.cjs');
test('prepared and damaged activation receipts block ordinary startup; ready is bound to its root',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-restore-start-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.mkdirSync(path.join(root,'.local'));const file=path.join(root,'.local/restore-activation.json');
 for(const value of ['broken',JSON.stringify({schema:1,phase:'prepared',data:root}),JSON.stringify({schema:1,phase:'ready',data:root+'-other'})]){fs.writeFileSync(file,value);assert.throws(()=>assertRestoreReviewed(root),error=>error.code==='BACKUP_RESTORE_REVIEW_REQUIRED');}
 fs.writeFileSync(file,JSON.stringify({schema:1,phase:'ready',data:root}));assert.doesNotThrow(()=>assertRestoreReviewed(root));
 fs.writeFileSync(path.join(root,'backup-manifest.json'),'{}');assert.throws(()=>assertRestoreReviewed(root));
});
test('public initialize cannot bypass the prepared guard with a caller supplied option',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-restore-init-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.mkdirSync(path.join(root,'.local'));fs.writeFileSync(path.join(root,'.local/restore-activation.json'),JSON.stringify({schema:1,phase:'prepared',data:root}));
 const {initialize}=require('./installed-runtime.cjs');assert.throws(()=>initialize('missing-payload',root,{allowPrepared:true}),error=>error.code==='BACKUP_RESTORE_REVIEW_REQUIRED');
});
test('a missing activation receipt does not remove the prepared-copy startup guard',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-restore-missing-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.mkdirSync(path.join(root,'.local'));fs.writeFileSync(path.join(root,'.local/restore-prepared-manifest.json'),'{}');
 assert.throws(()=>assertRestoreReviewed(root),error=>error.code==='BACKUP_RESTORE_REVIEW_REQUIRED');
});
