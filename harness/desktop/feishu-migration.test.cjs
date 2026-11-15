const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {migrateInstalledFeishu}=require('./installed-migrations.cjs');

function fixture(t,config='[]'){
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx-feishu-upgrade-'));
  t.after(()=>fs.rmSync(data,{recursive:true,force:true}));
  const patch=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');
  fs.mkdirSync(path.dirname(patch),{recursive:true});fs.writeFileSync(patch,config);
  const workspace=path.join(data,'workspace');fs.mkdirSync(workspace);
  fs.writeFileSync(path.join(workspace,'lawyer.txt'),'synthetic private profile');
  return {data,patch,workspace};
}
function portable(data){return [{insert:[{id:'qx-feishu',name:'app/plugins/feishu/index.js',
  config:{workspace:path.join(data,'workspace'),stateDir:path.join(data,'.local/feishu')}}]}];}

test('older payload without the Feishu adapter leaves user configuration and state unchanged',t=>{
  const f=fixture(t,'[{"id":"custom","disabled":true}]');
  assert.equal(migrateInstalledFeishu({data:f.data,portableConfig:[]}).status,'deferred');
  assert.equal(fs.readFileSync(f.patch,'utf8'),'[{"id":"custom","disabled":true}]');
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/feishu-v1.json')),false);
});
test('upgrade adds the adapter once, preserves custom plugins and backs up the exact old patch',t=>{
  const original='[{"id":"custom","config":{"model":"lawyer-choice"}}]';
  const f=fixture(t,original),config=portable(f.data);
  const result=migrateInstalledFeishu({data:f.data,portableConfig:config});
  assert.equal(result.status,'applied');
  assert.equal(fs.readFileSync(path.join(result.backupDirectory,'cordis.patch.yml'),'utf8'),original);
  assert.deepEqual(JSON.parse(fs.readFileSync(f.patch,'utf8')),[...JSON.parse(original),...config]);
  assert.equal(fs.readFileSync(path.join(f.workspace,'lawyer.txt'),'utf8'),'synthetic private profile');
  const after=fs.readFileSync(f.patch);assert.equal(migrateInstalledFeishu({data:f.data,portableConfig:config}).status,'already-applied');
  assert.deepEqual(fs.readFileSync(f.patch),after);
});
test('upgrade preserves a user-disabled adapter and never creates a scheduled task or account',t=>{
  const original='[{"id":"qx-feishu","disabled":true,"config":{"workspace":"custom"}}]';
  const f=fixture(t,original);
  migrateInstalledFeishu({data:f.data,portableConfig:portable(f.data)});
  assert.equal(fs.readFileSync(f.patch,'utf8'),original);
  assert.equal(fs.existsSync(path.join(f.data,'.local/feishu')),false);
});
test('bad installed patch does not receive a completion marker or overwrite user files',t=>{
  const f=fixture(t,'{"broken":true}');
  assert.throws(()=>migrateInstalledFeishu({data:f.data,portableConfig:portable(f.data)}),/patch array/);
  assert.equal(fs.readFileSync(f.patch,'utf8'),'{"broken":true}');
  assert.equal(fs.existsSync(path.join(f.data,'.local/migrations/feishu-v1.json')),false);
});
