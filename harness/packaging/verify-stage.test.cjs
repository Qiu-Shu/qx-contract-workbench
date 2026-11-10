const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {verifySources}=require('./verify-stage.cjs');
function fixture(t){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-release-input-'));
  for(const folder of ['base','win-unpacked']){fs.mkdirSync(path.join(root,folder));fs.writeFileSync(path.join(root,folder,'dependency.txt'),'immutable synthetic dependency');}
  fs.writeFileSync(path.join(root,'source-manifest.json'),JSON.stringify({files:[],generated:[]}));
  t.after(()=>{assert.equal(path.dirname(root),path.resolve(os.tmpdir()));assert.ok(path.basename(root).startsWith('qx-release-input-'));fs.rmSync(root,{recursive:true,force:true});});
  return root;
}
test('clean inherited release files pass the input gate',async t=>{await verifySources(fixture(t));});
test('test-generated files cannot silently enter an installer',async t=>{const root=fixture(t);fs.writeFileSync(path.join(root,'win-unpacked','generated.pyc'),'test artifact');await assert.rejects(verifySources(root),/unexpected files/);});
test('modified inherited dependencies cannot bypass the source manifest',async t=>{const root=fixture(t);fs.writeFileSync(path.join(root,'win-unpacked','dependency.txt'),'modified');await assert.rejects(verifySources(root),/dependency or generated file changed/);});
