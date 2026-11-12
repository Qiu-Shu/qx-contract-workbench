const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {copyMediaRegistry}=require('./stage.cjs');
const {spawnSync}=require('node:child_process');

test('source overlay supplies the snapshot worker configurations without building an installer',{skip:process.platform!=='win32'||!process.env.QX_TEST_PYTHON},t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-backup-overlay-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const source=path.resolve(__dirname,'..'),payload=path.join(root,'payload'),manifest=[];
  require('./stage.cjs').copyBackupConfiguration(source,payload,manifest);
  for(const name of ['backup-settings.json','postgres-backup-runtime.json'])
    assert.deepEqual(fs.readFileSync(path.join(payload,'config',name)),fs.readFileSync(path.join(source,'config',name)));
  assert.equal(manifest.length,2);
  fs.mkdirSync(path.join(payload,'bridge'));fs.copyFileSync(path.join(source,'bridge/backup_snapshot.py'),path.join(payload,'bridge/backup_snapshot.py'));
  const target=path.join(root,'private');
  const result=spawnSync(process.env.QX_TEST_PYTHON,[path.join(payload,'bridge/backup_snapshot.py')],{encoding:'utf8',windowsHide:true,input:JSON.stringify({action:'private-directory',path:target})});
  assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).path,target);assert.ok(fs.statSync(target).isDirectory());
});

test('registry validation rejects invalid configuration before replacing the payload',t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-media-registry-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const source=path.join(root,'registry.json'),payload=path.join(root,'payload');
  fs.mkdirSync(path.join(payload,'sources'),{recursive:true});
  const target=path.join(payload,'sources/media-source-registry.json');
  fs.writeFileSync(target,'previous valid payload');
  const valid={version:1,sources:[{id:'synthetic',title:'Synthetic source',url:'https://example.org/',allowed_hosts:['example.org'],source_kind:'news',refresh_minutes:30}]};
  for(const alter of [v=>v.version=2,v=>v.sources=[],v=>v.sources.push({...v.sources[0]}),v=>v.sources[0].allowed_hosts=[],v=>v.sources[0].refresh_minutes=-1]){
    const value=structuredClone(valid);alter(value);fs.writeFileSync(source,JSON.stringify(value));
    assert.throws(()=>copyMediaRegistry(source,payload,[]),/Invalid media source registry/);
    assert.equal(fs.readFileSync(target,'utf8'),'previous valid payload');
  }
});
