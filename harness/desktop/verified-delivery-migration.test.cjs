const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {migrateInstalledVerifiedDelivery}=require('./installed-migrations.cjs');
test('adds delivery protection to existing profiles once and preserves opt-out',t=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx-delivery-migrate-'));t.after(()=>fs.rmSync(data,{recursive:true,force:true}));
 const patch=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml');fs.mkdirSync(path.dirname(patch),{recursive:true});
 const entry={id:'qx-verified-delivery',name:'portable/verified-delivery/index.mjs',config:{workspace:'private/workspace'}};
 fs.writeFileSync(patch,'[]');const options={data,portableConfig:[{insert:[entry]}]};
 assert.equal(migrateInstalledVerifiedDelivery({...options,portableConfig:[]}).status,'deferred');
 const result=migrateInstalledVerifiedDelivery(options);assert.equal(result.status,'applied');assert.ok(result.backupDirectory);
 assert.deepEqual(JSON.parse(fs.readFileSync(patch)).at(-1).insert,[entry]);
 assert.equal(migrateInstalledVerifiedDelivery(options).status,'already-applied');
 fs.unlinkSync(path.join(data,'.local/migrations/verified-delivery-v1.json'));
 const custom=JSON.stringify([{insert:[{...entry,disabled:true,name:'custom'}]}]);fs.writeFileSync(patch,custom);
 migrateInstalledVerifiedDelivery(options);assert.equal(fs.readFileSync(patch,'utf8'),custom);
});
