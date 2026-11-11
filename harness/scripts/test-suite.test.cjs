const test=require('node:test'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs'),os=require('node:os');
const runner=path.join(__dirname,'test-suite.cjs');

test('default test plan contains restore regressions but no native or paid evaluations',()=>{
  const result=spawnSync(process.execPath,[runner,'offline','--list'],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  const plan=JSON.parse(result.stdout);
  assert.ok(plan.node.includes('desktop/integration/knowledge-restore.test.mjs'));
  assert.ok(plan.node.includes('plugins/wechat/test/credentials.test.mjs'));
  assert.ok(plan.python.includes('packaging/test_media_payload.py'));
  assert.ok(!plan.node.some(file=>/credentials-windows|incremental-install|evaluate_skills/.test(file)));
});

test('real quality mode refuses execution without explicit opt in and inputs',()=>{
  const result=spawnSync(process.execPath,[runner,'quality'],{encoding:'utf8',env:{...process.env,QX_REAL_MODEL_TEST:''}});
  assert.notEqual(result.status,0);
  assert.match(result.stderr,/QX_REAL_MODEL_TEST=1/);
});

test('test runner preserves child failures',()=>{
  const {run}=require('./test-suite.cjs');
  assert.equal(run(process.execPath,['-e','process.exit(7)'],process.env),7);
});

test('a successful evaluator process cannot hide missing or incomplete model responses',t=>{
  const {checkQualityResults}=require('./test-suite.cjs');
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'qx-quality-results-'));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const cases=[{id:'synthetic'}],file=path.join(directory,'synthetic.json');
  assert.throws(()=>checkQualityResults(directory,cases),/ENOENT/);
  for(const status of ['request-failed','incomplete']){
    fs.writeFileSync(file,JSON.stringify({status}));
    assert.throws(()=>checkQualityResults(directory,cases),/failed or incomplete/);
  }
  fs.writeFileSync(file,JSON.stringify({status:'response-received'}));
  checkQualityResults(directory,cases);
});
