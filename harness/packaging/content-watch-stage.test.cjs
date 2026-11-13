const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {createHash}=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {overlay,copyContentWatchAssets}=require('./stage.cjs');
const root=path.resolve(__dirname,'..');

function fixture(t){
  const stage=fs.mkdtempSync(path.join(os.tmpdir(),'qx-content-stage-'));
  t.after(()=>fs.rmSync(stage,{recursive:true,force:true}));
  const payload=path.join(stage,'win-unpacked/resources/workbench'),manifest=[];
  fs.mkdirSync(path.join(payload,'plugins/content-watch'),{recursive:true});fs.mkdirSync(path.join(stage,'base'));
  overlay(path.join(root,'plugins/content-watch'),path.join(payload,'plugins/content-watch'),manifest,'resources/workbench/plugins/content-watch');
  copyContentWatchAssets(payload,manifest);
  return {stage,payload,manifest};
}

test('portable content watcher uses installed paths without seeding an account or schedule',()=>{
  const patches=JSON.parse(fs.readFileSync(path.join(__dirname,'payload-config/portable.json'),'utf8'));
  const entries=patches.flatMap(patch=>patch.insert||[]).filter(plugin=>plugin.id==='qx-content-watch');
  assert.equal(entries.length,1);
  assert.deepEqual(entries[0],{id:'qx-content-watch',name:'@APP@/plugins/content-watch/index.mjs',
    config:{workspace:'@DATA@/workspace',stateDir:'@DATA@/.local/content-watch'}});
});

test('content watch package includes its preparer and license in the source manifest',t=>{
  const {payload,manifest}=fixture(t);
  for(const relative of ['scripts/prepare-content-watch.mjs','sources/xiaohongshu-mcp-Apache-2.0.txt']){
    const source=fs.readFileSync(path.join(root,relative)),packed=fs.readFileSync(path.join(payload,relative));
    assert.deepEqual(packed,source);
    assert.deepEqual(manifest.filter(item=>item.target==='resources/workbench/'+relative),[
      {source:relative,target:'resources/workbench/'+relative,sha256:createHash('sha256').update(source).digest('hex')},
    ]);
  }
  assert.equal(manifest.some(item=>/\.test\.(mjs|cjs|js)$/.test(item.target)),false);
});

test('packaged plugin imports with its real dependencies and cannot make network requests',t=>{
  const {payload,manifest}=fixture(t);
  const wechat=path.join(payload,'plugins/wechat');fs.mkdirSync(wechat,{recursive:true});
  // These existing plugin dependencies are normally supplied by the full plugins overlay.
  for(const name of ['package.json','secrets.js','session.js'])fs.copyFileSync(path.join(root,'plugins/wechat',name),path.join(wechat,name));
  const entry=pathToFileURL(path.join(payload,'plugins/content-watch/index.mjs')).href;
  const preparer=pathToFileURL(path.join(payload,'scripts/prepare-content-watch.mjs')).href;
  const before=fs.readdirSync(payload,{recursive:true}).sort();
  execFileSync(process.execPath,['--input-type=module','-e',`
    import assert from 'node:assert/strict';
    import {readFile} from 'node:fs/promises';
    let calls=0;
    globalThis.fetch=async()=>{calls++;throw Error('Network disabled for package import check');};
    const plugin=await import(${JSON.stringify(entry)});
    const prepare=await import(${JSON.stringify(preparer)});
    assert.equal(plugin.name,'qx-content-watch');
    assert.equal(typeof plugin.installContentWatch,'function');
    assert.equal(typeof prepare.prepareContentWatch,'function');
    const license=await readFile(new URL('../sources/xiaohongshu-mcp-Apache-2.0.txt',${JSON.stringify(preparer)}),'utf8');
    assert.match(license,/Apache License/);
    assert.equal(calls,0);
  `],{stdio:'pipe'});
  assert.deepEqual(fs.readdirSync(payload,{recursive:true}).sort(),before);
  assert.ok(manifest.some(item=>item.target==='resources/workbench/scripts/prepare-content-watch.mjs'));
});

test('existing source verifier accepts content assets and rejects altered or extra package files',async t=>{
  const {stage,payload,manifest}=fixture(t),manifestPath=path.join(stage,'source-manifest.json');
  const save=()=>fs.writeFileSync(manifestPath,JSON.stringify({files:manifest,generated:[]}));save();
  // This fixture has no ASAR entries. Keep the real source/tree verifier while rejecting any archive use.
  const toolchain=require('./toolchain.cjs');
  t.mock.method(toolchain,'load',name=>{assert.equal(name,'@electron/asar');return {extractFile(){throw Error('No archive entries in content asset fixture');}};});
  delete require.cache[require.resolve('./verify-stage.cjs')];
  const {verifySources}=require('./verify-stage.cjs');
  t.after(()=>{delete require.cache[require.resolve('./verify-stage.cjs')];});
  await verifySources(stage);
  const script=path.join(payload,'scripts/prepare-content-watch.mjs'),original=fs.readFileSync(script);
  fs.appendFileSync(script,'\n// altered candidate\n');
  await assert.rejects(verifySources(stage),/Candidate differs from source/);
  fs.writeFileSync(script,original);
  const extra=path.join(payload,'unexpected-state.json');fs.writeFileSync(extra,'{}');
  await assert.rejects(verifySources(stage),/missing or unexpected files/);fs.unlinkSync(extra);
  const item=manifest.find(item=>item.source==='scripts/prepare-content-watch.mjs'),digest=item.sha256;
  item.sha256='0'.repeat(64);save();
  await assert.rejects(verifySources(stage),/Source changed after staging/);
  item.sha256=digest;save();await verifySources(stage);
});
