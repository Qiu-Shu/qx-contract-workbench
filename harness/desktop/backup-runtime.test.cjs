const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const runtime=require('./backup-runtime.cjs');
test('unverified engine is never reported ready or executed',async t=>{
 const anchor=fs.mkdtempSync(path.join(os.tmpdir(),'qx-engine-'));t.after(()=>fs.rmSync(anchor,{recursive:true,force:true}));
 fs.mkdirSync(path.join(anchor,'.local/backup-runtime'),{recursive:true});fs.writeFileSync(path.join(anchor,'.local/backup-runtime/restic.exe'),'untrusted');
 assert.equal(runtime.engineReady(anchor),false);
 await assert.rejects(runtime.prepareEngine({anchor,payload:'unused',fetcher:async()=>new Response('untrusted')}),/BACKUP_ENGINE_UNVERIFIED/);
 assert.equal(fs.readFileSync(path.join(anchor,'.local/backup-runtime/restic.exe'),'utf8'),'untrusted');
});
test('fixed cached archive can prepare the exact verified executable without network',{skip:!process.env.QX_TEST_RESTIC_ZIP||!process.env.QX_TEST_APP},async t=>{
 const anchor=fs.mkdtempSync(path.join(os.tmpdir(),'qx-engine-real-'));t.after(()=>fs.rmSync(anchor,{recursive:true,force:true}));
 await runtime.prepareEngine({anchor,payload:process.env.QX_TEST_APP,worker:path.join(__dirname,'../bridge/backup_engine.py'),fetcher:async()=>new Response(fs.readFileSync(process.env.QX_TEST_RESTIC_ZIP))});
 assert.equal(runtime.engineReady(anchor),true);
 await runtime.prepareEngine({anchor,payload:'unused',fetcher:()=>{throw Error('must reuse verified engine');}});
});
