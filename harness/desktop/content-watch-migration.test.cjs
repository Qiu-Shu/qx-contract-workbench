const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {migrateInstalledContentWatch}=require('./installed-migrations.cjs');

function fixture(t,config='[]'){
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx-content-upgrade-'));
  t.after(()=>fs.rmSync(data,{recursive:true,force:true}));
  const patch=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');
  fs.mkdirSync(path.dirname(patch),{recursive:true});fs.writeFileSync(patch,config);
  const workspace=path.join(data,'workspace');fs.mkdirSync(workspace);
  fs.writeFileSync(path.join(workspace,'lawyer.txt'),'synthetic private profile');
  return {data,patch,workspace};
}
function portable(data){return [{insert:[{id:'qx-content-watch',name:'app/plugins/content-watch/index.mjs',
  config:{workspace:path.join(data,'workspace'),stateDir:path.join(data,'.local/content-watch')}}]}];}

test('older payload without the content watcher leaves user configuration and state unchanged',t=>{
  const f=fixture(t,'[{"id":"custom","disabled":true}]');
  assert.equal(migrateInstalledContentWatch({data:f.data,portableConfig:[]}).status,'deferred');
  assert.equal(fs.readFileSync(f.patch,'utf8'),'[{"id":"custom","disabled":true}]');
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/content-watch-v1.json')),false);
});
test('upgrade adds the watcher once, preserves custom plugins and backs up the exact old patch',t=>{
  const original='[{"id":"custom","config":{"model":"lawyer-choice"}}]';
  const f=fixture(t,original),config=portable(f.data);
  const result=migrateInstalledContentWatch({data:f.data,portableConfig:config});
  assert.equal(result.status,'applied');
  assert.equal(fs.readFileSync(path.join(result.backupDirectory,'cordis.patch.yml'),'utf8'),original);
  assert.deepEqual(JSON.parse(fs.readFileSync(f.patch,'utf8')),[...JSON.parse(original),...config]);
  assert.equal(fs.readFileSync(path.join(f.workspace,'lawyer.txt'),'utf8'),'synthetic private profile');
  const after=fs.readFileSync(f.patch);assert.equal(migrateInstalledContentWatch({data:f.data,portableConfig:config}).status,'already-applied');
  assert.deepEqual(fs.readFileSync(f.patch),after);
});
test('upgrade preserves a user-disabled watcher and never creates a scheduled task or account',t=>{
  const original='[{"id":"qx-content-watch","disabled":true,"config":{"workspace":"custom"}}]';
  const f=fixture(t,original);
  migrateInstalledContentWatch({data:f.data,portableConfig:portable(f.data)});
  assert.equal(fs.readFileSync(f.patch,'utf8'),original);
  assert.equal(fs.existsSync(path.join(f.data,'.local/content-watch')),false);
});
test('bad installed patch does not receive a completion marker or overwrite user files',t=>{
  const f=fixture(t,'{"broken":true}');
  assert.throws(()=>migrateInstalledContentWatch({data:f.data,portableConfig:portable(f.data)}),/patch array/);
  assert.equal(fs.readFileSync(f.patch,'utf8'),'{"broken":true}');
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/content-watch-v1.json')),false);
});
