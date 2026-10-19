const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
test('declared desktop bundle includes standalone credential modules without new dependencies',()=>{
  const root=path.resolve(__dirname,'..');
  const metadata=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
  assert.deepEqual(metadata.dependencies||{},{});
  for(const name of ['model-credentials.cjs','model-settings.cjs']){
    assert.ok(metadata.build.files.includes(name),'native model module missing from explicit bundle');
    assert.ok(fs.statSync(path.join(root,name)).isFile());
  }
  // Load the modules from the declared file set, so an undeclared local require fails.
  const stage=fs.mkdtempSync(path.join(os.tmpdir(),'qx-model-packaging-'));
  try{
    for(const name of metadata.build.files){
      assert.equal(path.basename(name),name,'bundle test expects explicit flat file list');
      fs.copyFileSync(path.join(root,name),path.join(stage,name));
    }
    assert.equal(typeof require(path.join(stage,'model-credentials.cjs')).createModelCredentialStore,'function');
    assert.equal(typeof require(path.join(stage,'model-settings.cjs')),'object');
    assert.ok(!fs.readdirSync(stage).some(name=>name.endsWith('.bin')||name.startsWith('test')));
  }finally{fs.rmSync(stage,{recursive:true});}
});
