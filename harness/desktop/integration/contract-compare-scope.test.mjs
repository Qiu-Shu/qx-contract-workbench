import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm,mkdir,readdir} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {installContractComparison} from './contract-compare-api.mjs';
test('two cases in one workspace cannot list, compare or restore each other; scope changes during calls fail',async t=>{
 const root=await mkdtemp(join(tmpdir(),'qx-case-diff-'));t.after(()=>rm(root,{recursive:true,force:true}));
 for(const [file,text] of [['a.txt','A100'],['a2.txt','A200'],['b.txt','B300']])await writeFile(join(root,file),text);
 await mkdir(join(root,'.qx-materials'));const db=new DatabaseSync(join(root,'.qx-materials/index.sqlite'));
 db.exec('CREATE TABLE legal_material_links(case_id TEXT,path TEXT,sha256 TEXT,version INTEGER);');
 const a='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',b='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
 for(const [c,p] of [[a,'a.txt'],[a,'a2.txt'],[b,'b.txt']])db.prepare('INSERT INTO legal_material_links VALUES(?,?,?,1)').run(c,p,createHash('sha256').update(p==='a.txt'?'A100':p==='a2.txt'?'A200':'B300').digest('hex'));
 db.close();let binding={project:a,revision:1,paths:[]},changeDuringStat=false;const routes=new Map();
 const ctx={serial:async()=>binding,workingDirectory:{get:()=>root},sessions:{get:id=>({header:{id,cwd:root}})},workspaceFiles:{
 stat:async()=>{if(changeDuringStat)binding={project:b,revision:2,paths:[]}},
 list:async()=>({entries:(await readdir(root)).map(name=>({name,type:'file'}))})},
 connection:{fetch:{register:r=>routes.set(r.path,r)}},tools:{register(){}}};
 installContractComparison(ctx);
 const call=async(action,args={})=>routes.get('/api/qx-compare/'+action).fetch(new Request('http://localhost/api/qx-compare/'+action,{method:'POST',headers:{'content-type':'application/json','x-qx-compare':'1'},body:JSON.stringify({sessionId:'same-session',...args})}));
 const contextResponse=await call('context');assert.equal(contextResponse.status,200);const context=await contextResponse.json();
 const listing=await (await call('list')).json();assert.deepEqual(listing.entries.map(e=>e.name).sort(),['a.txt','a2.txt']);
 assert.equal((await call('compare',{before:'a.txt',after:'b.txt',expectedScope:context.scopeKey})).status,403);
 const result=await (await call('compare',{before:'a.txt',after:'a2.txt',expectedScope:context.scopeKey})).json();assert.equal(result.equal,false);
 const analysis={before:{path:result.before.path,sha256:result.before.sha256},after:{path:result.after.path,sha256:result.after.sha256},party:'甲方',expectedScope:context.scopeKey};
 assert.equal((await call('analysis-draft',analysis)).status,200);
 // Reusing A's filename for B must not leak B's current text through A's historical link.
 await writeFile(join(root,'a.txt'),'B replacement');
 const changedDB=new DatabaseSync(join(root,'.qx-materials/index.sqlite'));
 changedDB.prepare('INSERT INTO legal_material_links VALUES(?,?,?,1)').run(b,'a.txt',createHash('sha256').update('B replacement').digest('hex'));changedDB.close();
 assert.equal((await call('compare',{before:'a.txt',after:'a2.txt'})).status,403);
 await writeFile(join(root,'a.txt'),'A100');
 binding={project:b,revision:2,paths:[]};
 assert.equal((await call('analysis-draft',analysis)).status,409);
 const staleScope=await call('compare',{before:'b.txt',after:'b.txt',expectedScope:context.scopeKey});
 assert.equal(staleScope.status,409);assert.equal((await staleScope.json()).code,'SCOPE_CHANGED');
 assert.equal((await call('locate',{reference:result.changes[0].before.reference})).status,409);
 binding={project:a,revision:3,paths:[]};changeDuringStat=true;
 const changedDuringCall=await call('compare',{before:'a.txt',after:'a2.txt'});
 assert.equal(changedDuringCall.status,409);assert.equal((await changedDuringCall.json()).code,'SCOPE_CHANGED');
 binding={project:a,revision:4,paths:[]};
 assert.equal((await call('analysis-draft',{...analysis,expectedScope:undefined})).status,409);
});

test('current uploaded references are selectable without reparsing, copying or uploading again',async t=>{
 const root=await mkdtemp(join(tmpdir(),'qx-upload-diff-'));t.after(()=>rm(root,{recursive:true,force:true}));
 const path='inbox/.harness/attachments/v1/files/ab/test/contract.txt',file=join(root,path);
 await mkdir(join(root,'inbox/.harness/attachments/v1/files/ab/test'),{recursive:true});await writeFile(file,'existing original');
 const routes=new Map(),ctx={serial:async()=>({project:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',revision:1,paths:[file]}),
 sessions:{get:()=>({header:{id:'s',cwd:root}})},workspaceFiles:{stat:async()=>{},list:async()=>({entries:[{name:'inbox',type:'directory'}]})},
 connection:{fetch:{register:r=>routes.set(r.path,r)}},tools:{register(){}}};
 installContractComparison(ctx);
 const response=await routes.get('/api/qx-compare/list').fetch(new Request('http://localhost/api/qx-compare/list',{method:'POST',headers:{'x-qx-compare':'1','content-type':'application/json'},body:JSON.stringify({sessionId:'s'})}));
 assert.equal(response.status,200);assert.ok((await response.json()).entries.some(e=>e.path===path));
 assert.deepEqual(await readdir(root),['inbox']);
});
