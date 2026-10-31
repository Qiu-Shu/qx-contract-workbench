const {test} = require('node:test');
const assert = require('node:assert/strict');
const {ModelControl} = require('../model-control.cjs');

const protocol = 'qx-model-control-v1';
const nonce = 'a'.repeat(32);
const version = '11111111-2222-4333-8444-555555555555';
const citation = 'aaaaaaaa-2222-4333-8444-555555555555';
const citation2 = 'bbbbbbbb-2222-4333-8444-555555555555';
const scope = {workspace_id:version,conversation_id:version,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:0};
const basis = () => ({input_format:'library-context-v1',template_version:'saved-library-context-system-v1',
  request_id:version,expected_scope:{...scope},expected_composer_revision:1,
  system_sha256:'a'.repeat(64),manifest_sha256:'b'.repeat(64),
  source_bindings:[{saved_citation_id:citation,citation_sha256:'c'.repeat(64)}],
  config_sha256:'d'.repeat(64),wire_sha256:'e'.repeat(64)});
const payload = () => ({session_token:'SYNTHETIC_SESSION_TOKEN',expected_config_version:version,
  basis:basis(),max_total_usd:'0.10',valid_for_seconds:60,max_rounds:1});

function channel(t) {
  const writes=[],fatal=[];
  const control=new ModelControl({nonce,write:line=>writes.push(line),
    onReady:()=>{},onFatal:code=>fatal.push(code)});
  t.after(()=>control.close());
  control.feed(Buffer.from(JSON.stringify({event:'ready',port:19022,nonce,control_protocol:protocol})+'\n'));
  return {control,writes,fatal};
}

test('a valid authorize_context command is framed and answered with the fixed statuses', async t => {
  const {control,writes,fatal}=channel(t);
  const pending=control.request('authorize_context',{...payload(),max_total_usd:null});
  assert.equal(writes.length,1);
  const frame=JSON.parse(writes[0]);
  assert.equal(frame.operation,'authorize_context');
  assert.equal(frame.payload.max_rounds,1);
  assert.equal(frame.payload.max_total_usd,null);
  control.feed(Buffer.from(JSON.stringify({event:'model-control-result',protocol,nonce,sequence:1,
    ok:true,status:'authorized'})+'\n'));
  assert.deepEqual(await pending,{ok:true,status:'authorized'});
  assert.deepEqual(fatal,[]);
});

const invalid = {
  'missing-max-rounds': value => { delete value.max_rounds; },
  'multi-round-not-this-slice': value => { value.max_rounds = 2; },
  'v2-format-not-this-slice': value => { value.basis.input_format = 'library-context-v2'; },
  'template-mismatch': value => { value.basis.template_version = 'saved-library-context-system-v2'; },
  'extra-payload-key': value => { value.note = 'x'; },
  'extra-basis-key': value => { value.basis.note = 'x'; },
  'bad-digest': value => { value.basis.wire_sha256 = 'zzzz'; },
  'empty-bindings': value => { value.basis.source_bindings = []; },
  'ninth-binding': value => { value.basis.source_bindings = Array.from({length:9},
    (_,index)=>({saved_citation_id:citation.slice(0,-1)+index,citation_sha256:'c'.repeat(64)})); },
  'duplicate-binding': value => { value.basis.source_bindings.push({...value.basis.source_bindings[0]}); },
  'binding-extra-key': value => { value.basis.source_bindings[0].title = 'x'; },
  'bad-citation-id': value => { value.basis.source_bindings[0].saved_citation_id = 'not-a-uuid'; },
  'bad-config-version': value => { value.expected_config_version = 'not-a-uuid'; },
  'overlong-validity': value => { value.valid_for_seconds = 901; },
};
for (const [name,mutate] of Object.entries(invalid)) {
  test(`authorize_context ${name} is rejected before writing or consuming a sequence`, async t => {
    const {control,writes}=channel(t);
    const value=payload();mutate(value);
    assert.deepEqual(await control.request('authorize_context',value),{ok:false,code:'BLOCKED_LIVE'});
    assert.equal(writes.length,0);
    assert.equal(control.sequence,0);
  });
}

test('two distinct citations in order are accepted', async t => {
  const {control,writes}=channel(t);
  const value=payload();
  value.basis.source_bindings.push({saved_citation_id:citation2,citation_sha256:'f'.repeat(64)});
  const pending=control.request('authorize_context',value);
  assert.equal(writes.length,1);
  control.feed(Buffer.from(JSON.stringify({event:'model-control-result',protocol,nonce,sequence:1,
    ok:true,status:'existing'})+'\n'));
  assert.deepEqual(await pending,{ok:true,status:'existing'});
});
