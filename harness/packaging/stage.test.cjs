const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {copyMediaRegistry}=require('./stage.cjs');

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
