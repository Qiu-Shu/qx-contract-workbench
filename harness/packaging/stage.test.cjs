const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {copyMediaRegistry}=require('./stage.cjs');
const {spawnSync}=require('node:child_process');

test('runner overlay includes new backup entry points without shipping development tests',t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-runner-overlay-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const source=path.resolve(__dirname,'..'),payload=path.join(root,'payload'),manifest=[];
  require('./stage.cjs').copyDesktopRunners(source,payload,manifest);
  require('./stage.cjs').copyBackupConfiguration(source,payload,manifest);
  const runner=path.join(payload,'desktop-runner');
  for(const name of ['backup-preparation.cjs','local-backup.cjs','installed-stop.cjs','installed-runtime.cjs',
    'restore-activation.cjs','restore-pending.cjs','data-location.cjs']){
    assert.deepEqual(fs.readFileSync(path.join(runner,name)),fs.readFileSync(path.join(source,'desktop',name)));
    assert.equal(manifest.filter(item=>item.target==='resources/workbench/desktop-runner/'+name).length,1);
  }
  assert.equal(typeof require(path.join(runner,'backup-preparation.cjs')).inspectScope,'function');
  assert.equal(typeof require(path.join(runner,'local-backup.cjs')).createLocalBackup,'function');
  assert.equal(fs.readdirSync(runner).some(name=>name.includes('.test.')||name.startsWith('check-')),false);
});

test('desktop overlay adds maintenance files absent from the old app and records each source once',t=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-maintenance-app-overlay-'));
  t.after(()=>fs.rmSync(temp,{recursive:true,force:true}));
  const source=path.join(temp,'source'),desktop=path.join(source,'desktop'),app=path.join(temp,'app'),manifest=[];
  fs.mkdirSync(desktop,{recursive:true});fs.mkdirSync(app);
  const added=['backup.html','backup.css','backup.js','backup-preload.cjs','backup-controller.cjs','backup-window.cjs','backup-runtime.cjs','data-location.cjs'];
  for(const name of ['main.cjs',...added])fs.writeFileSync(path.join(desktop,name),'synthetic current '+name);
  fs.writeFileSync(path.join(desktop,'backup-ui.test.cjs'),'must not ship');
  fs.writeFileSync(path.join(desktop,'check-synthetic.cjs'),'must not ship');
  fs.writeFileSync(path.join(app,'main.cjs'),'old bootstrap');
  fs.writeFileSync(path.join(app,'backup.js'),'old maintenance version');
  fs.writeFileSync(path.join(app,'third-party.txt'),'preserved dependency');
  require('./stage.cjs').copyDesktopApp(source,app,manifest);
  for(const name of ['main.cjs',...added]){
    assert.deepEqual(fs.readFileSync(path.join(app,name)),fs.readFileSync(path.join(desktop,name)));
    assert.equal(manifest.filter(item=>item.target==='app.asar/'+name).length,1);
  }
  assert.equal(manifest.length,added.length+1);
  assert.equal(fs.readFileSync(path.join(app,'third-party.txt'),'utf8'),'preserved dependency');
  assert.equal(fs.existsSync(path.join(app,'backup-ui.test.cjs')),false);
  assert.equal(fs.existsSync(path.join(app,'check-synthetic.cjs')),false);
  fs.unlinkSync(path.join(desktop,'backup-controller.cjs'));
  assert.throws(()=>require('./stage.cjs').copyDesktopApp(source,app,[]),/ENOENT/);
});

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
  assert.equal(result.status,0,result.stderr);
  assert.equal(fs.realpathSync.native(JSON.parse(result.stdout).path),fs.realpathSync.native(target));
  assert.ok(fs.statSync(target).isDirectory());
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
