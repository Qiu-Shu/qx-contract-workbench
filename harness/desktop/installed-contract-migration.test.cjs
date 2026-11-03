const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createHash}=require('node:crypto');
const {migrateInstalledContract}=require('./installed-migrations.cjs');
const files=['.dsh/skills/qx-contract-review/SKILL.md','.dsh/skills/qx-contract-review/references/method.md'];
function fixture(t){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-contract-upgrade-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const data=path.join(root,'data'),payload=path.join(root,'app');
  const write=(file,text)=>{fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,text)};
  const hashes={};
  for(const file of files){write(path.join(data,'workspace',file),'old default');write(path.join(payload,'workspace-seed',file),'new default');hashes[file]=createHash('sha256').update('old default').digest('hex')}
  write(path.join(data,'workspace/AGENTS.md'),'My personal rule.\r\nContract: old default\r\nKeep this too.\r\n');
  write(path.join(payload,'workspace-seed/AGENTS.md'),'Contract: comments and opinion\n');
  write(path.join(payload,'config/contract-0.2.0-defaults.json'),JSON.stringify({files:hashes,instructionPrefix:'Contract:',oldInstruction:'Contract: old default'}));
  write(path.join(data,'workspace/matter.txt'),'client material');
  return {data,payload,run:()=>migrateInstalledContract({data,payload})};
}
test('upgrade replaces released defaults, updates only the known instruction and keeps exact backups',t=>{
  const f=fixture(t),result=f.run();
  for(const file of files){assert.equal(fs.readFileSync(path.join(f.data,'workspace',file),'utf8'),'new default');assert.equal(fs.readFileSync(path.join(result.backupDirectory,file.replaceAll('/','__')),'utf8'),'old default')}
  assert.equal(fs.readFileSync(path.join(f.data,'workspace/AGENTS.md'),'utf8'),'My personal rule.\r\nContract: comments and opinion\r\nKeep this too.\r\n');
  assert.equal(fs.readFileSync(path.join(f.data,'workspace/matter.txt'),'utf8'),'client material');
  assert.equal(f.run().status,'already-applied');
});
test('custom contract skill and edited instruction survive while untouched reference updates',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.data,'workspace',files[0]),'My custom skill');fs.writeFileSync(path.join(f.data,'workspace/AGENTS.md'),'Contract: my custom choice\n');
  const result=f.run();assert.equal(fs.readFileSync(path.join(f.data,'workspace',files[0]),'utf8'),'My custom skill');
  assert.equal(fs.readFileSync(path.join(f.data,'workspace/AGENTS.md'),'utf8'),'Contract: my custom choice\n');
  assert.equal(fs.readFileSync(path.join(f.data,'workspace',files[1]),'utf8'),'new default');assert.ok(result.preservedCustom.includes(files[0]));
});
test('interrupted replacement has no success marker and safely resumes from backed-up defaults',t=>{
  const f=fixture(t),rename=fs.renameSync;let calls=0;
  fs.renameSync=(a,b)=>{if(b===path.join(f.data,'workspace',files[1])&&++calls===1)throw Error('simulated replace failure');return rename(a,b)};
  try{assert.throws(f.run,/simulated/)}finally{fs.renameSync=rename}
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/contract-delivery-v1.json')),false);
  assert.equal(f.run().status,'applied');assert.equal(fs.readFileSync(path.join(f.data,'workspace',files[1]),'utf8'),'new default');
});
