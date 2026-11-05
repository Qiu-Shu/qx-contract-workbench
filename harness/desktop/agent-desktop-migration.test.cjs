const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {migrateInstalledAgentDesktop}=require('./installed-migrations.cjs');

function fixture(t,entry){
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx-agent-desktop-'));
  t.after(()=>fs.rmSync(data,{recursive:true,force:true}));
  const patch=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');
  fs.mkdirSync(path.dirname(patch),{recursive:true});
  fs.writeFileSync(patch,JSON.stringify([{insert:[{id:'keep-me',name:'synthetic'},...(entry?[entry]:[])]}]));
  const desired={id:'qx-agent-desktop',name:'@deepseek-ai/dsh-mcp-client',disabled:false,config:{command:'portable/agent-desktop.exe',args:['mcp']}};
  return {data,patch,portableConfig:[{insert:[desired]}],desired};
}
test('adds optional desktop entry with backup and is idempotent',t=>{
  const f=fixture(t);const before=fs.readFileSync(f.patch,'utf8');
  const result=migrateInstalledAgentDesktop(f);
  assert.equal(result.status,'applied');
  assert.equal(fs.readFileSync(path.join(result.backupDirectory,'cordis.patch.yml'),'utf8'),before);
  assert.deepEqual(JSON.parse(fs.readFileSync(f.patch)).flatMap(x=>x.insert||[]).at(-1),f.desired);
  assert.equal(migrateInstalledAgentDesktop(f).status,'already-applied');
});
test('preserves a deliberate desktop opt-out and customized command',t=>{
  const f=fixture(t,{id:'qx-agent-desktop',name:'custom',disabled:true,config:{command:'mine.exe'}});
  const before=fs.readFileSync(f.patch,'utf8');migrateInstalledAgentDesktop(f);
  assert.equal(fs.readFileSync(f.patch,'utf8'),before);
});
test('older payload lacking optional desktop remains usable',t=>{
  const f=fixture(t);const before=fs.readFileSync(f.patch,'utf8');
  assert.equal(migrateInstalledAgentDesktop({...f,portableConfig:[]}).status,'deferred');
  assert.equal(fs.readFileSync(f.patch,'utf8'),before);
});
