import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm,mkdir,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import * as compare from './attachment-preview.mjs';
import * as engine from './contract-compare.mjs';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
test('whole-operation character detail budget falls back to honest full paragraphs',()=>{
  assert.equal(typeof engine.refineContractChanges,'function','shared detail budget is missing');
  const changes=[{before:{text:'原文'},after:{text:'新文'}},{before:null,after:{text:'新增'}}];
  assert.equal(engine.refineContractChanges(changes,-Infinity),true);
  assert.ok(changes.every(change=>change.characterDetail===false));assert.equal(changes[0].parts[0].value,'原文');
});
test('indexed uploaded contract aliases can be selected without exposing other hidden folders',async t=>{
  assert.equal(typeof engine.indexedContractPaths,'function','indexed upload listing is missing');
  const root=await fixture(t),key='inbox/.harness/attachments/v1/files/ab/abcdef/合同.txt';await mkdir(join(root,'inbox/.harness/attachments/v1/files/ab/abcdef'),{recursive:true});await mkdir(join(root,'.qx-materials'));
  await writeFile(join(root,key),'上传正文');await writeFile(join(root,'b.txt'),'修改正文');
  const db=new DatabaseSync(join(root,'.qx-materials/index.sqlite'));db.exec('CREATE TABLE materials(path TEXT)');for(const value of [key,'../secret.txt','.git/secret.txt'])db.prepare('INSERT INTO materials VALUES(?)').run(value);db.close();
  assert.deepEqual(await engine.indexedContractPaths(root),[key]);assert.equal((await compare.compareContracts({root,sessionId:'s'},key,'b.txt')).status,'complete');
});
async function fixture(t){const root=await mkdtemp(join(tmpdir(),'qx-compare-'));t.after(()=>rm(root,{recursive:true,force:true}));return root;}
test('Chinese paragraph and Unicode changes preserve both originals and exact source lines',async t=>{
  assert.equal(typeof compare.compareContracts,'function','contract comparison entry is missing');
  const root=await fixture(t),old='第一条 保密义务。\n第二条 价款为人民币100元😀。\n第三条 旧条款。',next='第一条 保密义务。\n第二条 价款为人民币200元𠮷。\n第三条 新条款。\n第四条 新增。';
  await writeFile(join(root,'甲.txt'),old);await writeFile(join(root,'乙.txt'),next);
  const result=await compare.compareContracts({root,sessionId:'s'},'甲.txt','乙.txt');
  assert.equal(result.status,'complete');assert.equal(result.equal,false);assert.ok(result.changes.length>=2);
  const changed=result.changes.find(c=>c.before?.text.includes('100'));
  assert.ok(changed.parts.some(p=>p.removed&&p.value.includes('😀')));assert.ok(changed.parts.some(p=>p.added&&p.value.includes('𠮷')));
  assert.equal(changed.before.reference.line,2);assert.equal(changed.before.reference.sha256,hash(old));
  const location=await compare.resolveContractReference({root,sessionId:'s'},changed.before.reference);
  assert.equal(location.text,changed.before.text);assert.equal(location.reference.line,2);
  assert.equal(await readFile(join(root,'甲.txt'),'utf8'),old);assert.equal(await readFile(join(root,'乙.txt'),'utf8'),next);
});
test('identical and empty readable text are equal; added and removed paragraphs retain their side',async t=>{
  const root=await fixture(t);await writeFile(join(root,'a.txt'),'');await writeFile(join(root,'b.txt'),'');
  assert.equal((await compare.compareContracts({root,sessionId:'s'},'a.txt','b.txt')).equal,true);
  await writeFile(join(root,'b.txt'),'新增\n');const added=await compare.compareContracts({root,sessionId:'s'},'a.txt','b.txt');
  assert.equal(added.changes[0].before,null);assert.equal(added.changes[0].after.text,'新增\n');
  const removed=await compare.compareContracts({root,sessionId:'s'},'b.txt','a.txt');assert.equal(removed.changes[0].after,null);
});
test('stale hashes, modified quotes, cross-session and cross-workspace references are rejected',async t=>{
  const root=await fixture(t),other=await fixture(t);await writeFile(join(root,'a.txt'),'原文');await writeFile(join(root,'b.txt'),'修改');await writeFile(join(other,'a.txt'),'原文');
  const scope={root,sessionId:'s'},r=await compare.compareContracts(scope,'a.txt','b.txt'),ref=r.changes[0].before.reference;
  await assert.rejects(compare.resolveContractReference({...scope,sessionId:'other'},ref),/归属/);
  await assert.rejects(compare.resolveContractReference({root:other,sessionId:'s'},ref),/归属/);
  await assert.rejects(compare.resolveContractReference(scope,{...ref,quoteSha256:'0'.repeat(64)}),/定位/);
  await writeFile(join(root,'a.txt'),'改文');await assert.rejects(compare.resolveContractReference(scope,ref),/原文件已变化/);
});
test('out-of-root paths and symlink targets are refused before any content is returned',async t=>{
  const root=await fixture(t),outside=await fixture(t);await writeFile(join(root,'a.txt'),'内');await writeFile(join(outside,'b.txt'),'外');
  await assert.rejects(compare.compareContracts({root,sessionId:'s'},join(outside,'b.txt'),'a.txt'),/工作区/);
  await mkdir(join(outside,'sub'));await writeFile(join(outside,'sub','c.txt'),'链接');await symlink(join(outside,'sub'),join(root,'linked'),'junction');
  await assert.rejects(compare.compareContracts({root,sessionId:'s'},'linked/c.txt','a.txt'),/工作区|链接/);
});
test('unindexed binary and invalid text cannot produce a false no-change conclusion',async t=>{
  const root=await fixture(t);await writeFile(join(root,'a.docx'),'not a docx');await writeFile(join(root,'b.txt'),Buffer.from([0xff,0]));
  const r=await compare.compareContracts({root,sessionId:'s'},'a.docx','b.txt');assert.equal(r.status,'unavailable');assert.equal(r.equal,null);assert.deepEqual(r.changes,[]);assert.ok(r.warnings.length);
});
test('text that grows after path authorization is read with the same bounded byte limit',async t=>{
  const root=await fixture(t);await writeFile(join(root,'a.txt'),'a');await writeFile(join(root,'b.txt'),'b');
  let expanded=false;const contents='a'.repeat(4000000);
  const result=await compare.compareContracts({root,sessionId:'s',authorize:async()=>{if(!expanded){expanded=true;await writeFile(join(root,'a.txt'),contents);}}},'a.txt','b.txt');
  assert.equal(result.status,'unavailable');assert.equal(result.equal,null);assert.deepEqual(result.changes,[]);
  assert.ok(result.warnings.some(warning=>warning.includes('文本超过本次对比范围')));
  assert.equal(hash(await readFile(join(root,'a.txt'))),hash(contents));
});
test('existing material index preserves original page/location and reports partial coverage',async t=>{
  const root=await fixture(t);await mkdir(join(root,'.qx-materials'));await writeFile(join(root,'a.pdf'),'synthetic-a');await writeFile(join(root,'b.pdf'),'synthetic-b');
  const db=new DatabaseSync(join(root,'.qx-materials','index.sqlite'));
  db.exec('CREATE TABLE materials(path TEXT,sha256 TEXT,status TEXT,page_count INTEGER,warnings TEXT,mtime INTEGER);CREATE TABLE chunks(path TEXT,ordinal INTEGER,page INTEGER,location TEXT,text TEXT);');
  for(const [name,text] of [['a.pdf','100元'],['b.pdf','200元']]){db.prepare('INSERT INTO materials VALUES(?,?,?,?,?,?)').run(name,hash(await readFile(join(root,name))),'partial',3,JSON.stringify(['第3页未完成']),1794466424034000000n);db.prepare('INSERT INTO chunks VALUES(?,?,?,?,?)').run(name,2000000,2,'page:2:native:chars:0-4',text);}
  db.close();const scope={root,sessionId:'s'},result=await compare.compareContracts(scope,'a.pdf','b.pdf');
  assert.equal(result.status,'partial');assert.equal(result.equal,null);assert.equal(result.changes[0].before.reference.page,2);
  assert.equal((await compare.resolveContractReference(scope,result.changes[0].before.reference)).reference.location,'page:2:native:chars:0-4');
});
test('concurrent parser commits cannot mix ready metadata with incomplete replacement chunks',async t=>{
  const root=await fixture(t);await mkdir(join(root,'.qx-materials'));
  const writer=new DatabaseSync(join(root,'.qx-materials/index.sqlite'));
  try{
    writer.exec('PRAGMA journal_mode=WAL;CREATE TABLE materials(path TEXT,sha256 TEXT,status TEXT,warnings TEXT);CREATE TABLE chunks(path TEXT,ordinal INTEGER,page INTEGER,location TEXT,text TEXT);');
    for(const [name,text] of [['a.pdf','100元'],['b.pdf','200元']]){
      await writeFile(join(root,name),name);
      writer.prepare('INSERT INTO materials VALUES(?,?,?,?)').run(name,hash(name),'ready','[]');
      writer.prepare('INSERT INTO chunks VALUES(?,?,?,?,?)').run(name,0,1,'page:1','共同条款');
      writer.prepare('INSERT INTO chunks VALUES(?,?,?,?,?)').run(name,1,2,'page:2',text);
    }
    const prepare=DatabaseSync.prototype.prepare;let interleaved=0;
    t.mock.method(DatabaseSync.prototype,'prepare',function(sql){
      const statement=prepare.call(this,sql);
      if(!sql.startsWith('SELECT ordinal,page,location,text'))return statement;
      return {all:(key,limit)=>{
        // Commit a new partial parse after the reader already obtained the old ready metadata.
        writer.exec('BEGIN');
        writer.prepare('UPDATE materials SET status=?,warnings=? WHERE path=?').run('partial','["第二页未完成"]',key);
        writer.prepare('DELETE FROM chunks WHERE path=? AND page=2').run(key);writer.exec('COMMIT');interleaved++;
        return statement.all(key,limit);
      }};
    });
    const result=await compare.compareContracts({root,sessionId:'s'},'a.pdf','b.pdf');
    assert.equal(interleaved,2);assert.equal(result.status,'complete');assert.equal(result.equal,false);
    assert.equal(result.changes[0].before.text,'100元');assert.equal(result.changes[0].after.text,'200元');
    assert.equal(await readFile(join(root,'a.pdf'),'utf8'),'a.pdf');assert.equal(await readFile(join(root,'b.pdf'),'utf8'),'b.pdf');
  }finally{writer.close();}
});
