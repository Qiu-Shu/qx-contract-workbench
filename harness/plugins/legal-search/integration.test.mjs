import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createRequire} from 'node:module';
import {apply} from './index.mjs';
const require=createRequire(import.meta.url);
const migrations=require('../../desktop/installed-migrations.cjs');
test('older payload without optional search plugin still starts and can migrate later',()=>{
 assert.equal(migrations.migrateInstalledLegalSearch({portableConfig:[]}).status,'deferred');
});
test('tools have Chinese cards and persisted read does not search again',async t=>{
 const workspace=await mkdtemp(join(tmpdir(),'qx-search-plugin-'));t.after(()=>rm(workspace,{recursive:true,force:true}));
 const tools=new Map(),sections=[];let calls=0;
 apply({web:{search:async()=>{calls++;return {sources:[{url:'https://court.gov.cn/a',title:'公开司法资料',summary:'公开摘要'}]};}},tools:{register:x=>tools.set(x.name,x)},systemPrompt:{section:x=>sections.push(x)},effect:()=>{}},{workspace,python:'unused'});
 assert.match(sections[0].text,/legal_search/);
 const search=tools.get('legal_search'),read=tools.get('legal_search_read');
 assert.equal(search.presentCall({queries:['合同']}).title,'法律资料检索');
 const value=await search.execute({queries:['合同']},{signal:new AbortController().signal});
 const content=search.output.render({},value),meta=search.presentResult({}, {content});
 assert.equal(meta.title,'法律资料检索');assert.equal(meta.sources.length,1);
 const record=JSON.parse(value),detail=JSON.parse(await read.execute({recordId:record.recordId,entry:0}));assert.match(detail.text,/公开摘要/);assert.equal(calls,1);
 assert.equal(read.presentCall().title,'读取法律检索资料');
});
test('upgrade appends only missing plugin, keeps custom settings and is idempotent',async t=>{
 const data=await mkdtemp(join(tmpdir(),'qx-search-migrate-'));t.after(()=>rm(data,{recursive:true,force:true}));
 const profile=join(data,'.local/dsh-home/profiles/web');await mkdir(profile,{recursive:true});
 const patch=join(profile,'cordis.patch.yml'),prior=[{id:'llm-deepseek',config:{model:'custom'}},{insert:[{id:'my-plugin',name:'custom'}]}];
 await writeFile(patch,JSON.stringify(prior));
 const portableConfig=[{insert:[{id:'qx-legal-search',name:'app/plugins/legal-search/index.mjs',config:{workspace:'work'}}]}];
 const first=migrations.migrateInstalledLegalSearch({data,portableConfig});assert.equal(first.status,'applied');
 const updated=JSON.parse(await readFile(patch,'utf8'));assert.deepEqual(updated.slice(0,2),prior);assert.equal(updated[2].insert[0].id,'qx-legal-search');
 assert.equal(migrations.migrateInstalledLegalSearch({data,portableConfig}).status,'already-applied');
 const customData=await mkdtemp(join(tmpdir(),'qx-search-custom-'));t.after(()=>rm(customData,{recursive:true,force:true}));
 const customProfile=join(customData,'.local/dsh-home/profiles/web');await mkdir(customProfile,{recursive:true});
 const custom=[{insert:[{id:'qx-legal-search',name:'custom',disabled:true}]}],customPath=join(customProfile,'cordis.patch.yml');await writeFile(customPath,JSON.stringify(custom));
 migrations.migrateInstalledLegalSearch({data:customData,portableConfig});assert.deepEqual(JSON.parse(await readFile(customPath,'utf8')),custom);
});
test('application-owned extension refreshes across upgrades without altering its existing profile entry',async t=>{
 const data=await mkdtemp(join(tmpdir(),'qx-search-extension-'));t.after(()=>rm(data,{recursive:true,force:true}));
 const payload=join(data,'payload'),relativeFiles=['plugins/legal-search/index.mjs','plugins/legal-search/core.mjs','bridge/legal_search_fallback.py','bridge/vendor/union_search/so360_parser.py'];
 for(const relative of relativeFiles){const file=join(payload,relative);await mkdir(join(file,'..'),{recursive:true});await writeFile(file,'first');}
 const profile=join(data,'.local/dsh-home/profiles/web');await mkdir(profile,{recursive:true});await writeFile(join(profile,'cordis.patch.yml'),'[]');
 const name=join(data,'.local/legal-search-runtime/plugins/legal-search/index.mjs');
 const portableConfig=[{insert:[{id:'qx-legal-search',name}]}];
 migrations.migrateInstalledLegalSearch({data,payload,portableConfig});assert.equal(await readFile(name,'utf8'),'first');
 await writeFile(join(payload,'plugins/legal-search/index.mjs'),'updated');migrations.migrateInstalledLegalSearch({data,payload,portableConfig});assert.equal(await readFile(name,'utf8'),'updated');
 assert.equal(JSON.parse(await readFile(join(profile,'cordis.patch.yml'),'utf8')).length,1);
});
