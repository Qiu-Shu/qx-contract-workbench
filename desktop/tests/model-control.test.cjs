const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {Backend} = require('../backend.cjs');
const {ModelControl} = require('../model-control.cjs');
const protocol = 'qx-model-control-v1';
const version = '11111111-2222-4333-8444-555555555555';
const fixture = path.join(__dirname,'fixture-model-control.cjs');
const config = {enabled:true,model:'deepseek-flash',input_usd_per_million:'0.3',
  output_usd_per_million:'1.2',price_reference:'synthetic-only'};
const secret = 'SYNTHETIC_MODEL_CONTROL_NOT_A_REAL_KEY_12345';
const nonce = 'a'.repeat(32);
const authorization = {session_token:'SYNTHETIC_SESSION_TOKEN',expected_config_version:version,
  basis:{request_id:version,expected_scope:{workspace_id:version,conversation_id:version,
    binding_version:1,input_revision:0,materials_revision:0},expected_composer_revision:0,
    content_sha256:'b'.repeat(64)},max_total_usd:'0.10',valid_for_seconds:60};
const frame = value => Buffer.from(JSON.stringify(value)+'\n');
const ready = {event:'ready',port:19022,nonce,control_protocol:protocol};
const answer = (values={}) => ({event:'model-control-result',protocol,nonce,sequence:1,
  ok:true,status:'disabled',...values});
function channel(t, options={}) {
  const writes=[],fatal=[],announcements=[];
  const control=new ModelControl({nonce,write:line => writes.push(line),
    onReady:value => announcements.push(value),onFatal:code => fatal.push(code),...options});
  t.after(() => control.close());
  return {control,writes,fatal,announcements};
}

test('main null budget passes the native bridge while missing budget remains rejected',async t=>{
  const f=channel(t);f.control.feed(frame(ready));
  const payload={...authorization,max_total_usd:null};
  const pending=f.control.request('authorize',payload);
  assert.equal(f.writes.length,1);
  assert.equal(JSON.parse(f.writes[0]).payload.max_total_usd,null);
  f.control.feed(frame(answer({status:'authorized'})));
  assert.equal((await pending).ok,true);
  delete payload.max_total_usd;
  assert.equal((await f.control.request('authorize',payload)).ok,false);
  assert.equal(f.writes.length,1);
});

test('trusted backend configures and disables through one owned child without exposing protocol credentials', async t => {
  const backend = new Backend(process.execPath,[fixture]);
  t.after(() => backend.stop());
  assert.equal((await backend.start({data_parent:'synthetic'})).control_protocol,protocol);
  assert.deepEqual(await backend.configureModel({config,secret}),
    {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:version});
  assert.deepEqual(await backend.disableModel(),{ok:true,status:'disabled'});
  assert.deepEqual(await backend.authorizeModel(authorization),{ok:true,status:'authorized'});
  assert.deepEqual(await backend.revokeModel({session_token:authorization.session_token}),{ok:true,status:'revoked'});
});

test('legacy readiness still starts but model control remains unavailable', async t => {
  const backend=new Backend(process.execPath,[fixture,'legacy']);
  t.after(() => backend.stop());
  assert.equal((await backend.start({data_parent:'synthetic'})).port,19022);
  assert.deepEqual(await backend.configureModel({config,secret}),{ok:false,code:'BLOCKED_LIVE'});
});

test('an owner stopped before startup cannot create a child or leave startup pending', async t => {
  const backend=new Backend(process.execPath,[fixture]);
  t.after(() => backend.stop());
  assert.deepEqual(await backend.disableModel(),{ok:false,code:'BLOCKED_LIVE'});
  await backend.stop();
  const result=backend.start({data_parent:'synthetic'}).then(() => 'started',error => error.message);
  assert.equal(await Promise.race([result,new Promise(resolve => setTimeout(() => resolve('still_pending'),100))]),
    'BACKEND_STOPPED');
  assert.equal(backend.child,undefined);
});

test('synchronous process setup errors never expose their input or leave a startup timer', async t => {
  const backend=new Backend({secret});
  t.after(() => backend.stop());
  await assert.rejects(backend.start({data_parent:'synthetic'}),{message:'BACKEND_START_FAILED'});
  assert.deepEqual(await backend.disableModel(),{ok:false,code:'BLOCKED_LIVE'});
});

test('fragmented child pipe frames are reconstructed through their final newline', async t => {
  const backend=new Backend(process.execPath,[fixture,'fragmented']);
  t.after(() => backend.stop());
  await backend.start({data_parent:'synthetic'});
  assert.deepEqual(await backend.disableModel(),{ok:true,status:'disabled'});
});

test('a malformed second frame in the readiness chunk rejects startup', async t => {
  const backend=new Backend(process.execPath,[fixture,'extra-ready-frame']);
  t.after(() => backend.stop());
  await assert.rejects(backend.start({data_parent:'synthetic'}),/BACKEND_PROTOCOL/);
  await backend.exited;
});

for (const mode of ['bad-nonce','partial-result']) test(`${mode} irreversibly closes the owned child and reports only one fixed failure`, async t => {
  const backend=new Backend(process.execPath,[fixture,mode]);
  t.after(() => backend.stop());
  let failures=0;
  backend.on('failed',(...args) => { failures++; assert.deepEqual(args,[]); });
  await backend.start({data_parent:'synthetic'});
  const pid=backend.child.pid;
  await assert.rejects(backend.disableModel(),/BACKEND_PROTOCOL/);
  await backend.exited;
  assert.equal(failures,1);
  assert.throws(() => process.kill(pid,0));
  assert.deepEqual(await backend.disableModel(),{ok:false,code:'BLOCKED_LIVE'});
});

test('normal stop cancels pending control, permits EOF exit and does not announce failure', async t => {
  const backend=new Backend(process.execPath,[fixture,'hang']);
  t.after(() => backend.stop());
  let failed=false;
  backend.on('failed',() => { failed=true; });
  await backend.start({data_parent:'synthetic'});
  const pending=assert.rejects(backend.disableModel(),/BACKEND_STOPPED/);
  await Promise.all([backend.stop(),backend.stop(),pending]);
  assert.equal(failed,false);
  assert.deepEqual(await backend.disableModel(),{ok:false,code:'BLOCKED_LIVE'});
});

for (const pipe of ['stdout','stderr']) test(`${pipe} system errors stay inside the fixed failure boundary`, async t => {
  const backend=new Backend(process.execPath,[fixture]);
  t.after(() => backend.stop());
  let failures=0;
  backend.on('failed',() => { failures++; });
  await backend.start({data_parent:'synthetic'});
  assert.doesNotThrow(() => backend.child[pipe].emit('error',new Error('synthetic pipe failure detail')));
  await backend.exited;
  assert.equal(failures,1);
  assert.deepEqual(await backend.disableModel(),{ok:false,code:'BLOCKED_LIVE'});
});

test('commands are serialized once, busy calls are rejected without allocating a sequence', async t => {
  const f=channel(t);
  f.control.feed(frame(ready));
  const first=f.control.request('disable',{});
  assert.deepEqual(await f.control.request('revoke',{session_token:'synthetic-token'}),
    {ok:false,code:'STATE_CONFLICT'});
  assert.equal(f.writes.length,1);
  assert.deepEqual(JSON.parse(f.writes[0]),{event:'model-control',protocol,nonce,
    sequence:1,operation:'disable',payload:{}});
  f.control.feed(frame(answer()));
  assert.deepEqual(await first,{ok:true,status:'disabled'});
  const second=f.control.request('revoke',{session_token:'synthetic-token'});
  assert.equal(JSON.parse(f.writes[1]).sequence,2);
  f.control.feed(frame(answer({sequence:2,status:'revoked'})));
  assert.deepEqual(await second,{ok:true,status:'revoked'});
});

test('business denials expose only fixed codes and do not poison the control pipe', async t => {
  const f=channel(t);
  f.control.feed(frame(ready));
  for (const [index,code] of ['VERSION_CONFLICT','STATE_CONFLICT','BUDGET_EXCEEDED',
    'CROSS_MATTER_DENIED',secret].entries()) {
    const result=f.control.request('disable',{});
    f.control.feed(frame({event:'model-control-result',protocol,nonce,sequence:index+1,ok:false,code}));
    assert.deepEqual(await result,{ok:false,code:code === secret ? 'BLOCKED_LIVE' : code});
  }
  assert.deepEqual(f.fatal,[]);
});

test('existing is an authorization-only success status', async t => {
  const f=channel(t);
  f.control.feed(frame(ready));
  const result=f.control.request('authorize',authorization);
  f.control.feed(frame(answer({status:'existing'})));
  assert.deepEqual(await result,{ok:true,status:'existing'});
});

for (const [name,bytes] of [
  ['wrong nonce',frame(answer({nonce:'wrong'}))],
  ['future sequence',frame(answer({sequence:2}))],
  ['unsafe sequence',frame(answer({sequence:9007199254740992}))],
  ['wrong operation status',frame(answer({status:'authorized'}))],
  ['unknown field',frame({...answer(),secret})],
  ['wrong protocol',frame(answer({protocol:'other'}))],
  ['duplicate key',Buffer.from(JSON.stringify(answer()).replace('"sequence":1','"sequence":1,"sequence":1')+'\n')],
  ['noncanonical number',Buffer.from(JSON.stringify(answer()).replace('"sequence":1','"sequence":1.0')+'\n')],
  ['extra whitespace',Buffer.from(' '+JSON.stringify(answer())+'\n')],
  ['invalid UTF8',Buffer.concat([Buffer.from([0xff]),frame(answer())])],
  ['UTF8 BOM',Buffer.concat([Buffer.from([0xef,0xbb,0xbf]),frame(answer())])],
  ['CRLF',Buffer.from(JSON.stringify(answer())+'\r\n')],
  ['extra empty frame',Buffer.from('\n')],
  ['oversized incomplete frame',Buffer.from('界'.repeat(2731))]
]) test(`${name} rejects the pending command with a fixed fatal error`, async t => {
  const f=channel(t);
  f.control.feed(frame(ready));
  const rejected=assert.rejects(f.control.request('disable',{}),{message:'BACKEND_PROTOCOL'});
  f.control.feed(bytes);
  await rejected;
  assert.deepEqual(f.fatal,['BACKEND_PROTOCOL']);
  f.control.feed(frame(answer()));
  assert.deepEqual(await f.control.request('disable',{}),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(f.writes.length,1);
});

test('every complete frame is handled, including a duplicate ack in the same buffer', async t => {
  const f=channel(t);
  f.control.feed(frame(ready));
  const first=f.control.request('disable',{});
  f.control.feed(Buffer.concat([frame(answer()),frame(answer())]));
  assert.deepEqual(await first,{ok:true,status:'disabled'});
  assert.deepEqual(f.fatal,['BACKEND_PROTOCOL']);
  assert.deepEqual(await f.control.request('disable',{}),{ok:false,code:'BLOCKED_LIVE'});
});

test('timeout and pipe-write failure are terminal and never retry a secret-bearing command', async t => {
  const timed=channel(t,{timeoutMs:10});
  timed.control.feed(frame(ready));
  await assert.rejects(timed.control.request('configure',{config,secret}),{message:'BACKEND_CONTROL_TIMEOUT'});
  assert.deepEqual(timed.fatal,['BACKEND_CONTROL_TIMEOUT']);
  assert.equal(timed.writes.length,1);
  assert.deepEqual(await timed.control.request('configure',{config,secret}),{ok:false,code:'BLOCKED_LIVE'});
  const broken=channel(t,{write:() => { throw new Error(secret); }});
  broken.control.feed(frame(ready));
  await assert.rejects(broken.control.request('configure',{config,secret}),{message:'BACKEND_PIPE_CLOSED'});
  assert.deepEqual(broken.fatal,['BACKEND_PIPE_CLOSED']);
});

test('invalid command inputs and UTF8 byte overflow are rejected before writing or consuming a sequence', async t => {
  const f=channel(t);
  f.control.feed(frame(ready));
  for (const [operation,payload] of [
    ['unknown',{}],['configure',{config,secret:'bad\n'+secret}],
    ['configure',{config:{...config,price_reference:'界'.repeat(11000)},secret}],
    ['configure',{config,secret,endpoint:'https://example.invalid'}],
    ['authorize',{...authorization,expected_config_version:'old'}],
    ['authorize',{...authorization,valid_for_seconds:901}],
    ['authorize',{...authorization,session_token:'token\nvalue'}],
    ['revoke',{session_token:'token',extra:true}]
  ]) assert.deepEqual(await f.control.request(operation,payload),{ok:false,code:'BLOCKED_LIVE'});
  assert.equal(f.writes.length,0);
  const pending=f.control.request('disable',{});
  assert.equal(JSON.parse(f.writes[0]).sequence,1);
  f.control.feed(frame(answer()));
  await pending;
});
