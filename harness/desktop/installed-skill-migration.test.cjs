const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createHash}=require('node:crypto');
const {gunzipSync}=require('node:zlib');
const {migrateInstalledSkillFixes}=require('./installed-migrations.cjs');

// Exact released defaults, compressed so the tests do not depend on an installed app.
const released={
  "impeccable": "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",
  "windows-desktop": "H4sIAAAAAAAAClVUS0/rRhjd51dY6q5Syp4t60pIVLpLLo+oRAVMEyO6dB5OHLATc8kDEockkBA3JTa9QF6Ow4+Jv2/Gq/yFajIuanezODPnfOecb6LRaOR07yS2KVzETw/Fi2T0MJb8TRLPIoex5EEifibFxdNNAW903zPRfEZzJnzhSAGKLVJuwaxMytZSTn3Z3lnKKfqexZlB7A4xcnBnoVolry5xW1jN++4InCl1mtjJreYNf3JDyhZW89h5hHEPlDGUHLA1VA2sjfz5LSgqKVscxgFLOR2JRqORyA8CWXRBefvUgh0taD5wmZGI732wO/Z9cKfgqwU5jdSzwteTg7Pd3XDO3d0fvwqfr4KiClviqZQQj3ekPek8KeCjjK0e6G1StlZzbed07yx5JEoC7afBaYF3AwWdNGxs51dzDXL6/yiLfd8dYTtPnRyqVVQH0Fj4nk48mytczTV+AKOI7QnY98S9wXtzKaf9iU6fUpDKU3tBKmwoaBprlgZzSx3j8BFMKwykNgpS72CrfBBSz5JhARaKPylisQ/qCJsZKOnBk8qci2DhBuYyD4z7G6oefw9V1LPEbYIzJdYVzEp07MAiu5o3wNBJ/wW0aaDo0P2bvvXAKIKiYqv3L0bzJzqUdOjqpPGdOpWlnOaRk3ILVYPTCb//sXuyJ8US8b3jJJvIuw4673yWELG/H91PiBfJWILF8qHQpxTLblu8iCV2jmLHx0KouZTGygt807jgTxlQGoBp8Xxg3GMeazPWQm7ebZF0bNKwwav4kyEW+rSjrbuoQ6ONVz00C8RVyV8OzXhw2QC7QB8VrLVBeaWew1JVq/6HjeUprzVLybPX7vquwicJqcxn6tmo5cGuM18HNSg9LuVUuAjfNN914bLDnaOOG5KkLqH7J6pVKAzo2xs2P0JAfkA7GpSuAzm1lFNQuoZJhq3b29CfvjC82g7uutg0sHq3lNOBKbMadXVWgtqIubI+c1LIKWBPWbDFFhNTeoLhLRQcNJ8/K+hPZvh+RZ0KKK9BbbiUU0FeB8NZc+VRf/hvHaGbJUaO1LPYUX13xNtmdeD+ij2W8ajjQilcBKyN2Ew87s+9Ynf52lTzaD7zTGjG890iMdev9FkR+BNEM/lWsI50dWymaT9H+wXuf2DKaBb4KpKyGzQf/EUTdZ4SNns4M1bz+pEknSU3NzZ+jUtH5/s/HYgnG1vniaSY+EU8PzjaCD+W6M9b2wLrMv/6ktJhXBRQKzB/P+6x2Aubbzisk91qkLFI4xqMZ1a5Oxe8Cs0PwHDg0mL0/wDCVHiibwUAAA=="
};
const hashes={impeccable:'fab04b31f946573b00a8559db1fc070f8ea5825254d491c2b13156e5661a86d7',
  'windows-desktop':'8869f57ed29b3368bcdbbb9ef71d9a87eae929e882f01c5bc346cc36cf8e64a8'};
const files=Object.keys(released).map(name=>'.dsh/skills/'+name+'/SKILL.md');
function fixture(t){
  const base=fs.realpathSync(os.tmpdir()),root=fs.mkdtempSync(path.join(base,'qx-skill-upgrade-'));
  t.after(()=>{assert.equal(path.dirname(path.resolve(root)),base);fs.rmSync(root,{recursive:true,force:true})});
  const data=path.join(root,'data'),payload=path.join(root,'app'),originals=new Map(),updated=new Map();
  for(const name of Object.keys(released)){
    const relative='.dsh/skills/'+name+'/SKILL.md',old=gunzipSync(Buffer.from(released[name],'base64'));
    assert.equal(createHash('sha256').update(old).digest('hex'),hashes[name]);
    const next=Buffer.from('Corrected instructions for '+name+'\n');
    originals.set(relative,old);updated.set(relative,next);
    for(const [directory,contents] of [[path.join(data,'workspace'),old],[path.join(payload,'workspace-seed'),next]]){
      const file=path.join(directory,relative);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,contents);
    }
  }
  return {data,payload,originals,updated,run:()=>migrateInstalledSkillFixes({data,payload})};
}

test('skill upgrade replaces only released defaults and keeps exact backups',t=>{
  const f=fixture(t),result=f.run();
  assert.deepEqual(result.changedFiles,files);
  for(const file of files){
    assert.deepEqual(fs.readFileSync(path.join(f.data,'workspace',file)),f.updated.get(file));
    assert.deepEqual(fs.readFileSync(path.join(result.backupDirectory,file.replaceAll('/','__'))),f.originals.get(file));
  }
});

test('customized helper skill stays untouched while the other default is updated',t=>{
  const f=fixture(t),custom=Buffer.from('My own instructions with CRLF\r\n');
  fs.writeFileSync(path.join(f.data,'workspace',files[0]),custom);
  const result=f.run();
  assert.deepEqual(fs.readFileSync(path.join(f.data,'workspace',files[0])),custom);
  assert.deepEqual(result.preservedCustom,[files[0]]);
  assert.deepEqual(result.changedFiles,[files[1]]);
  assert.deepEqual(fs.readFileSync(path.join(f.data,'workspace',files[1])),f.updated.get(files[1]));
});

test('a second startup makes no additional changes or backups',t=>{
  const f=fixture(t),first=f.run();
  const migrationRoot=path.join(f.data,'.local/migrations'),before=fs.readdirSync(migrationRoot).sort();
  const result=f.run();
  assert.equal(result.status,'already-applied');assert.deepEqual(result.changedFiles,[]);
  assert.deepEqual(fs.readdirSync(migrationRoot).sort(),before);
  assert.ok(fs.existsSync(first.backupDirectory));
});

test('fresh installations already containing the seed need no replacement or backup',t=>{
  const f=fixture(t);
  for(const file of files)fs.writeFileSync(path.join(f.data,'workspace',file),f.updated.get(file));
  const result=f.run();
  assert.deepEqual(result.changedFiles,[]);assert.deepEqual(result.preservedCustom,[]);
  assert.equal(result.backupDirectory,null);
});

test('missing optional helper skills do not block startup or recreate deleted user files',t=>{
  const f=fixture(t);
  fs.unlinkSync(path.join(f.data,'workspace',files[0]));
  const result=f.run();
  assert.deepEqual(result.changedFiles,[files[1]]);
  assert.equal(fs.existsSync(path.join(f.data,'workspace',files[0])),false);
});

test('a partial seed defers only the missing update and retries when the package is complete',t=>{
  const f=fixture(t),seed=path.join(f.payload,'workspace-seed',files[1]);
  fs.unlinkSync(seed);
  assert.equal(f.run().status,'deferred');
  assert.deepEqual(fs.readFileSync(path.join(f.data,'workspace',files[1])),f.originals.get(files[1]));
  fs.writeFileSync(seed,f.updated.get(files[1]));
  assert.deepEqual(f.run().changedFiles,[files[1]]);
  assert.deepEqual(fs.readFileSync(path.join(f.data,'workspace',files[1])),f.updated.get(files[1]));
});

test('initialize upgrades existing default skills after non-overwriting workspace seeding',t=>{
  const f=fixture(t);
  const write=(relative,contents)=>{const file=path.join(f.payload,relative);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,contents)};
  fs.mkdirSync(path.join(f.payload,'node_modules'));
  write('workspace-seed/AGENTS.md','## 本机律所知识库\n合成知识库规则。\nContract: new\n');
  const contractFiles=['.dsh/skills/qx-contract-review/SKILL.md','.dsh/skills/qx-contract-review/references/method.md'];
  for(const file of contractFiles)write('workspace-seed/'+file,'new contract default');
  write('config/contract-0.2.0-defaults.json',JSON.stringify({files:Object.fromEntries(contractFiles.map(file=>[file,'0'.repeat(64)])),instructionPrefix:'Contract:',oldInstruction:'Contract: old'}));
  write('config/portable.json',JSON.stringify([{insert:[
    {id:'qx-knowledge-ui',name:'@APP@/plugins/knowledge/index.mjs'},
    {id:'qx-knowledge',name:'@deepseek-ai/dsh-mcp-client'},
    {id:'qx-upload-privacy',name:'@APP@/plugins/privacy/index.mjs'},
  ]},{id:'llm-deepseek',config:{retryPolicy:{mode:'normal',maxRetries:5,retryableCodes:['MALFORMED_RESPONSE','STREAM_CLOSED']}}}]));
  write('config/profile-package.json','{}');write('config/profile-cordis.yml','[]');
  require('./installed-runtime.cjs').initialize(f.payload,f.data);
  for(const file of files)assert.deepEqual(fs.readFileSync(path.join(f.data,'workspace',file)),f.updated.get(file));
  assert.equal(f.run().status,'already-applied');
});
