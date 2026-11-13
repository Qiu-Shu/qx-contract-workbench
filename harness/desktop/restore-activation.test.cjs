const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const python=spawnSync(process.env.QX_TEST_PYTHON||'python',['-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true}).stdout.trim();
function api(){const file=path.join(__dirname,'restore-activation.cjs');assert.ok(fs.existsSync(file),'restore activation backend is missing');return require(file);}
function put(root,name,value){const file=path.join(root,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,value);}
function fixture(t,setup=()=>{}){
  const temp=fs.realpathSync.native(fs.mkdtempSync(path.join(os.tmpdir(),'qx-activation-')));t.after(()=>fs.rmSync(temp,{recursive:true,force:true}));
  const source=path.join(temp,'source'),root=path.join(temp,'restored'),destination=path.join(temp,'active'),payload=path.join(temp,'payload');
  put(source,'workspace/original.txt','synthetic original');
  put(source,'.local/desktop-data/locale.json',JSON.stringify({locale:'zh-CN',secret:'synthetic-private'}));
  put(source,'.local/dsh-home/qx-wechat/prefs.json',JSON.stringify({format:'raw',delivery:'whole',desktopControl:true,secret:'synthetic-private'}));
  put(source,'.local/dsh-home/profiles/web/cordis.patch.yml',JSON.stringify([{id:'custom',name:'never-execute',config:{secret:'synthetic-private'}},{id:'agent-default-model',config:{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'high'}}]));
  put(payload,'config/portable.json',JSON.stringify([{id:'agent-default-model',config:{provider:'deepseek-official',model:'deepseek-flash'}},{insert:[{id:'qx-personal-wechat',name:'@APP@/plugins/wechat/qx-plugin.js',config:{workspace:'@DATA@/workspace',stateDir:'@DATA@/.local/dsh-home/qx-wechat',autoConnect:true}}]}]));
  setup(source);
  const {inspectScope}=require('./backup-preparation.cjs');
  const result=spawnSync(python,[path.join(__dirname,'../bridge/backup_snapshot.py')],{input:JSON.stringify({action:'create',source,destination:root,plan:inspectScope(source)}),encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,result.stdout+result.stderr);
  return {temp,source,root,destination,payload,python};
}
function tree(root){return Object.fromEntries(fs.readdirSync(root,{recursive:true}).sort().filter(n=>fs.statSync(path.join(root,n)).isFile()).map(n=>{const f=path.join(root,n);return[n,[crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),fs.statSync(f,{bigint:true}).mtimeNs.toString()]];}));}
test('activation exposes inspect, prepare and final verification interfaces',()=>{const module=api();for(const key of ['inspectRestoreActivation','prepareRestoreActivation','verifyPreparedRestore'])assert.equal(typeof module[key],'function');});
test('reviewed settings prepare a separate inactive copy without changing originals',{skip:process.platform!=='win32'},async t=>{
  const options=fixture(t),before=tree(options.root),module=api();
  const review=await module.inspectRestoreActivation(options);assert.match(review.reviewToken,/^[a-f0-9]{64}$/);
  assert.equal(review.counts.files,4);assert.equal(review.pending.length,0);assert.doesNotMatch(JSON.stringify(review),/synthetic-private|never-execute/);
  const prepared=await module.prepareRestoreActivation({...options,reviewToken:review.reviewToken,applySettings:true,decisions:{}});
  assert.equal(prepared.destination,options.destination);assert.deepEqual(tree(options.root),before);
  const receipt=JSON.parse(fs.readFileSync(path.join(options.destination,'.local/restore-activation.json')));
  assert.equal(receipt.phase,'prepared');assert.equal(receipt.data,options.destination);assert.equal(receipt.sourceRestoreRoot,options.root);assert.match(receipt.id,/^[a-f0-9-]{36}$/);
  assert.equal(fs.existsSync(path.join(options.destination,'backup-manifest.json')),false);
  assert.equal(fs.existsSync(path.join(options.destination,'.local/restore-original',receipt.id,'backup-manifest.json')),true);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(options.destination,'.local/desktop-data/locale.json'))),{locale:'zh-CN'});
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(options.destination,'.local/dsh-home/qx-wechat/prefs.json'))),{format:'raw',delivery:'whole'});
  const profile=fs.readFileSync(path.join(options.destination,'.local/dsh-home/profiles/web/cordis.patch.yml'),'utf8');
  assert.doesNotMatch(profile,/synthetic-private|never-execute|@APP@|@DATA@/);assert.match(profile,/deepseek-flash/);
  assert.equal((await module.verifyPreparedRestore({root:options.destination,python})).phase,'prepared');
  put(options.destination,'workspace/original.txt','changed');await assert.rejects(module.verifyPreparedRestore({root:options.destination,python}),{code:'BACKUP_PREPARED_CHANGED'});
});
test('stale review, destination collision and host lease never replace caller files',{skip:process.platform!=='win32'},async t=>{
  const options=fixture(t),module=api(),review=await module.inspectRestoreActivation(options);
  await assert.rejects(module.prepareRestoreActivation({...options,reviewToken:'0'.repeat(64)}),{code:'BACKUP_REVIEW_STALE'});
  assert.equal(fs.existsSync(options.destination),false);
  const lease=await require('./installed-stop.cjs').claimLauncher(options.destination);
  try{await assert.rejects(module.prepareRestoreActivation({...options,reviewToken:review.reviewToken}),{code:'BACKUP_HOST_BUSY'});}finally{await lease.close();}
  fs.mkdirSync(options.destination);put(options.destination,'keep.txt','keep');
  await assert.rejects(module.prepareRestoreActivation({...options,reviewToken:review.reviewToken}),{code:'BACKUP_TARGET_EXISTS'});
  assert.equal(fs.readFileSync(path.join(options.destination,'keep.txt'),'utf8'),'keep');
});
test('restored source corruption and changed trusted configuration invalidate preparation',{skip:process.platform!=='win32'},async t=>{
  const options=fixture(t),module=api(),review=await module.inspectRestoreActivation(options);
  put(options.payload,'config/portable.json','[]');
  await assert.rejects(module.prepareRestoreActivation({...options,reviewToken:review.reviewToken}),{code:'BACKUP_REVIEW_STALE'});
  put(options.root,'workspace/original.txt','changed');
  await assert.rejects(module.inspectRestoreActivation(options),{code:'BACKUP_FILE_HASH_MISMATCH'});
  assert.equal(fs.existsSync(options.destination),false);
});
test('failed choices release the lease and remove only the unpublished copy',{skip:process.platform!=='win32'},async t=>{
  const options=fixture(t),module=api(),before=tree(options.root),review=await module.inspectRestoreActivation(options);
  await assert.rejects(module.prepareRestoreActivation({...options,reviewToken:review.reviewToken,decisions:{unknown:'draft'}}),{code:'BACKUP_PENDING_CHOICE_INVALID'});
  await assert.rejects(module.prepareRestoreActivation({...options,reviewToken:review.reviewToken,applySettings:['unknown']}),{code:'BACKUP_SETTINGS_CHOICE_INVALID'});
  assert.equal(fs.existsSync(options.destination),false);assert.deepEqual(tree(options.root),before);
  assert.ok(!fs.readdirSync(options.temp).some(name=>name.startsWith('.qx-activation-')));
  const prepared=await module.prepareRestoreActivation({...options,reviewToken:review.reviewToken,applySettings:false});
  assert.equal(prepared.phase,'prepared');assert.equal(fs.existsSync(path.join(options.destination,'.local/desktop-data/locale.json')),false);
  const {inspectScope}=require('./backup-preparation.cjs'),plan=inspectScope(options.destination);
  assert.ok(!plan.scopes.some(item=>item.policy==='unclassified'));
  assert.equal(plan.scopes.find(item=>item.path==='.local/restore-original').policy,'protect');
  assert.equal(plan.scopes.find(item=>item.path==='.local/restore-activation.json').policy,'runtime');
  put(options.destination,'workspace/unreviewed.txt','unexpected');
  await assert.rejects(module.verifyPreparedRestore({root:options.destination,python}),{code:'BACKUP_PREPARED_CHANGED'});
});
test('preparation rejects overlapping source, restore, payload and target roots',{skip:process.platform!=='win32'},async t=>{
  const options=fixture(t),module=api(),review=await module.inspectRestoreActivation(options);
  for(const base of [options.root,options.source,options.payload])await assert.rejects(module.prepareRestoreActivation({...options,destination:path.join(base,'child'),reviewToken:review.reviewToken}),{code:'BACKUP_OVERLAPPING_PATHS'});
  assert.equal(fs.existsSync(options.destination),false);
});
test('the new copy always has an activation guard before its review markers move',{skip:process.platform!=='win32'},async t=>{
  const options=fixture(t),module=api(),review=await module.inspectRestoreActivation(options),rename=fs.renameSync;let observed=false;
  t.mock.method(fs,'renameSync',function(from,to){
    if(path.basename(from)==='backup-manifest.json'){
      const receipt=path.join(path.dirname(from),'.local/restore-activation.json');observed=true;
      assert.ok(fs.existsSync(receipt),'unpublished activation copy lost all startup guards');
      assert.equal(JSON.parse(fs.readFileSync(receipt)).phase,'prepared');
    }
    return rename.apply(this,arguments);
  });
  await module.prepareRestoreActivation({...options,reviewToken:review.reviewToken});assert.equal(observed,true);
});

test('backup classifies only known activation location records and temporary names',t=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-activation-policy-'));t.after(()=>fs.rmSync(temp,{recursive:true,force:true}));
  const id=crypto.randomUUID(),known=['data-location.json','data-location.json.previous','data-location.json.previous.'+id,'data-location.json.'+id+'.tmp'];
  for(const name of [...known,'data-location.json.previous.anything','data-location.json.anything.tmp'])put(temp,'.local/'+name,'{}');
  put(temp,'.local/backup-runtime/tool.exe','synthetic');
  fs.mkdirSync(path.join(temp,'.local/data-location.json.previous.'+crypto.randomUUID()));
  const scopes=require('./backup-preparation.cjs').inspectScope(temp).scopes;
  for(const name of known)assert.equal(scopes.find(s=>s.path==='.local/'+name).policy,'runtime',name);
  assert.equal(scopes.find(s=>s.path==='.local/backup-runtime').policy,'rebuild');
  assert.equal(scopes.filter(s=>s.policy==='unclassified').length,3);
});

test('an unavailable drive is rejected promptly instead of hanging path validation',{skip:process.platform!=='win32'},()=>{
  const drive=['Z','Y','X','W'].find(letter=>!fs.existsSync(letter+':\\'));if(!drive)return;
  const script="require("+JSON.stringify(path.join(__dirname,'restore-activation.cjs'))+").inspectRestoreActivation({root:"+JSON.stringify(drive+':\\missing')+"}).then(()=>process.exit(2),e=>{if(e.code!=='BACKUP_INVALID_PATH')process.exit(3);})";
  const result=spawnSync(process.execPath,['-e',script],{encoding:'utf8',windowsHide:true,timeout:2000});
  assert.equal(result.error,undefined);assert.equal(result.status,0,result.stderr);
});

test('verified snapshot activation applies pending decisions only in its new copy',{skip:process.platform!=='win32'},async t=>{
  const queue='.local/dsh-home/qx-wechat/qx-pending.json';
  const options=fixture(t,source=>put(source,queue,JSON.stringify({version:1,pending:[{id:'draft-me',items:[{text:'合成待办转为草稿'}]},{id:'cancel-me',items:[{text:'合成待办取消'}]}],active:{id:'hold-me',items:[{text:'合成已提交待核对'}]},history:[],failed:[]})));
  const before=tree(options.root),sourceBefore=tree(options.source),module=api(),review=await module.inspectRestoreActivation(options);
  assert.equal(review.pending.length,3);const decisions={};
  for(const item of review.pending){if(item.preview.includes('转为草稿'))decisions[item.id]='draft';else if(item.preview.includes('取消'))decisions[item.id]='cancel';}
  const prepared=await module.prepareRestoreActivation({...options,reviewToken:review.reviewToken,decisions});
  assert.deepEqual(tree(options.root),before);assert.deepEqual(tree(options.source),sourceBefore);
  const frozen=JSON.parse(fs.readFileSync(path.join(options.destination,queue)));
  assert.deepEqual(frozen.pending,[]);assert.equal(frozen.active,null);assert.equal(prepared.drafts.length,1);
  assert.match(fs.readFileSync(path.join(options.destination,prepared.drafts[0]),'utf8'),/合成待办转为草稿/);
  const ledger=JSON.parse(fs.readFileSync(path.join(options.destination,'.local/restore-pending.json')));
  assert.deepEqual(ledger.pending.map(row=>row.decision).sort(),['cancel','draft','hold']);
  assert.equal((await module.verifyPreparedRestore({root:options.destination,python})).id,prepared.id);
});

test('migration history is protected but old completion markers cannot skip fresh initialization',{skip:process.platform!=='win32'},async t=>{
  const marker='.local/migrations/upload-privacy-v1.json',history='.local/migrations/prior/cordis.patch.yml';
  const options=fixture(t,source=>{
    put(source,marker,JSON.stringify({version:'upload-privacy-v1',completedAt:'old'}));
    put(source,history,'synthetic-migration-secret: never-load');
    put(source,'.local/restore-original/earlier/migrations/keep.txt','older audit');
  });
  const plan=require('./backup-preparation.cjs').inspectScope(options.source);
  assert.equal(plan.scopes.find(item=>item.path==='.local/migrations').policy,'protect');
  const before=tree(options.root),module=api(),review=await module.inspectRestoreActivation(options);
  assert.doesNotMatch(JSON.stringify(review),/synthetic-migration-secret|never-load/);
  const prepared=await module.prepareRestoreActivation({...options,reviewToken:review.reviewToken});
  assert.deepEqual(tree(options.root),before);assert.equal(fs.existsSync(path.join(options.destination,'.local/migrations')),false);
  const archive=path.join(options.destination,'.local/restore-original',prepared.id,'migrations');
  assert.deepEqual(tree(archive),tree(path.join(options.root,'.local/migrations')));
  assert.equal(fs.readFileSync(path.join(options.destination,'.local/restore-original/earlier/migrations/keep.txt'),'utf8'),'older audit');
  assert.doesNotMatch(fs.readFileSync(path.join(options.destination,'.local/dsh-home/profiles/web/cordis.patch.yml'),'utf8'),/synthetic-migration-secret|never-load/);
  assert.equal((await module.verifyPreparedRestore({root:options.destination,python})).id,prepared.id);
  const migrated=require('./installed-migrations.cjs').migrateInstalledPrivacy({data:options.destination,payload:options.payload,portableConfig:[{id:'qx-upload-privacy',name:'trusted-synthetic-plugin'}]});
  assert.equal(migrated.status,'applied');
  assert.notEqual(JSON.parse(fs.readFileSync(path.join(options.destination,marker))).completedAt,'old');
  assert.deepEqual(tree(archive),tree(path.join(options.root,'.local/migrations')));
});

test('an archive identifier collision refuses publication without replacing earlier history',{skip:process.platform!=='win32'},async t=>{
  const collision=crypto.randomUUID(),options=fixture(t,source=>put(source,'.local/restore-original/'+collision+'/keep.txt','prior audit'));
  const module=api(),before=tree(options.root),review=await module.inspectRestoreActivation(options);
  t.mock.method(crypto,'randomUUID',()=>collision);
  await assert.rejects(module.prepareRestoreActivation({...options,reviewToken:review.reviewToken}),{code:'BACKUP_TARGET_EXISTS'});
  assert.equal(fs.existsSync(options.destination),false);assert.deepEqual(tree(options.root),before);
  assert.ok(!fs.readdirSync(options.temp).some(name=>name.startsWith('.qx-activation-')));
});
