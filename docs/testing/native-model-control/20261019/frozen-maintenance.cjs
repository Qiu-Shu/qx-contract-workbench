// Existing Maintenance adapter and final production executable, synthetic only.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {Maintenance}=require('../../desktop/maintenance.cjs');
const base=__dirname,exe=path.join(base,'frozen-backend/qx-backend/qx-backend.exe');
async function main(){
  const parent=JSON.parse(fs.readFileSync(path.join(base,'frozen-backend-smoke.json'),'utf8')).workspace_parent;
  const archive=path.join(base,'synthetic-maintenance-'+require('node:crypto').randomUUID()+'.qxbak');
  const config={data_parent:parent,archive,passphrase:'synthetic-maintenance-password-12345'};
  const backup=new Maintenance(exe,[]),restore=new Maintenance(exe,[]);
  try{
    const saved=await backup.run({...config,operation:'backup'});
    const restored=await restore.run({...config,operation:'restore'});
    assert.equal(saved.archive_sha256,restored.archive_sha256);
    assert.equal(saved.workspace_id,restored.workspace_id);assert.equal(restored.quarantined,true);
    assert.equal(backup.child.exitCode,0);assert.equal(restore.child.exitCode,0);
    fs.writeFileSync(path.join(base,'frozen-maintenance.json'),JSON.stringify({status:'passed',
      checks:['existing_maintenance_adapter_backup','existing_maintenance_adapter_restore_quarantined'],
      archive_sha256:saved.archive_sha256,file_count:saved.file_count,exit_codes:[0,0]},null,2));
  }finally{await backup.stop();await restore.stop();}
}
main().catch(error=>{process.exitCode=1;console.log(JSON.stringify({error_type:error.name,
  code:/^[A-Z_]+$/.test(error.message)?error.message:'PROBE_FAILED',
  location:String(error.stack).match(/frozen-maintenance\.cjs:\d+:\d+/)?.[0]}));});
