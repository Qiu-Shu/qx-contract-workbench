// Production Node owner and Python framing, synthetic no-op handler only.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {Backend} = require('../../desktop/backend.cjs');
const root = path.resolve(__dirname,'../..');
const secret = 'SYNTHETIC_REVIEW_NO_REAL_PROVIDER_KEY_12345';
const config = {enabled:true,model:'deepseek-flash',price_reference:'合成价格上限',
  input_usd_per_million:'0.3',output_usd_per_million:'1.2'};
function child(t, invalid=false) {
  const backend = new Backend(path.join(root,'.venv/Scripts/python.exe'),
    ['-X','utf8',path.join(__dirname,'review-control-child.py'),...(invalid?['invalid']:[])]);
  t.after(()=>backend.stop());
  return backend;
}

test('actual Node to Python control uses LF, one command in flight, fixed projections and clean EOF', async t=>{
  const backend = child(t);
  const ready = await backend.start({data_parent:__dirname});
  assert.equal(ready.control_protocol,'qx-model-control-v1');
  const bytes=[];
  backend.child.stdout.on('data',part=>bytes.push(part));
  const first = backend.configureModel({config,secret});
  assert.deepEqual(await backend.disableModel(),{ok:false,code:'STATE_CONFLICT'});
  assert.deepEqual(await first,{ok:true,status:'configured',config_sha256:'e'.repeat(64),
    config_version:'00000000-0000-0000-0000-000000000001'});
  assert.deepEqual(await backend.revokeModel({session_token:'SYNTHETIC_SESSION_TOKEN'}),{ok:true,status:'revoked'});
  await backend.stop();
  assert.equal(backend.child.exitCode,0);
  const raw=Buffer.concat(bytes).toString('utf8');
  assert(!raw.includes('\r'));
  assert(!raw.includes(secret));
  assert(!raw.includes('SYNTHETIC_SESSION_TOKEN'));
});

test('actual malformed handler projection exits the child without returning synthetic secret', async t=>{
  const backend=child(t,true);
  await backend.start({data_parent:__dirname});
  const bytes=[];
  let failures=0;
  backend.child.stdout.on('data',part=>bytes.push(part));
  backend.child.stderr.on('data',part=>bytes.push(part));
  backend.on('failed',()=>failures++);
  await assert.rejects(backend.configureModel({config,secret}),/BACKEND_EXITED/);
  await backend.exited;
  assert.equal(failures,1);
  assert(!Buffer.concat(bytes).includes(Buffer.from(secret)));
  assert.deepEqual(await backend.disableModel(),{ok:false,code:'BLOCKED_LIVE'});
});
