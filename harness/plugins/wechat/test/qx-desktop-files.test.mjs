import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath,symlink} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createDesktopFileAccess} from '../qx-desktop-files.js';

async function fixture(t){
  const root=await mkdtemp(join(tmpdir(),'qx-desktop-files-'));t.after(()=>rm(root,{recursive:true,force:true}));
  const desktop=join(root,'重定向桌面'),shared=join(root,'公共桌面'),workspace=join(root,'workspace');
  for(const dir of [desktop,shared,workspace])await mkdir(dir);
  const api=createDesktopFileAccess({workspace,getDirectories:async()=>[desktop,shared]});
  return {root,desktop,shared,workspace,api};
}
test('matches names only, reports multiple candidates and never reads file text',async t=>{
  const f=await fixture(t);
  for(const dir of [f.desktop,f.shared])await writeFile(join(dir,'租赁合同.docx'),'synthetic private text');
  await writeFile(join(f.desktop,'other.docx'),'unrelated');
  const result=await f.api.find('租赁');
  assert.equal(result.files.length,2);assert.equal(result.truncated,false);
  assert.ok(result.files.every(x=>x.name==='租赁合同.docx'));
  assert.ok(!JSON.stringify(result).includes('synthetic private text'));
  await assert.rejects(f.api.find(''),/文件名/);
});
test('copies only requested desktop file without changing original; workspace files pass directly',async t=>{
  const f=await fixture(t),file=join(f.desktop,'合同.docx');await writeFile(file,'synthetic original');
  const staged=await f.api.prepare(file);
  assert.ok(staged.startsWith(await realpath(f.workspace)));assert.notEqual(staged,file);
  assert.equal(await readFile(staged,'utf8'),'synthetic original');
  assert.equal(await readFile(file,'utf8'),'synthetic original');
  assert.equal(await f.api.prepare(staged),staged);
});
test('outside files, directories, shortcuts and escaped directory searches are refused',async t=>{
  const f=await fixture(t);const outside=join(f.root,'private.txt');await writeFile(outside,'not authorized');
  await writeFile(join(f.desktop,'外部文件.lnk'),'synthetic shortcut');
  await assert.rejects(f.api.prepare(outside),/工作区或桌面/);
  await assert.rejects(f.api.prepare(f.desktop),/工作区或桌面/);
  await assert.rejects(f.api.prepare(join(f.desktop,'外部文件.lnk')),/快捷方式/);
  await assert.rejects(f.api.find('private','..'),/桌面/);
});
test('nested desktop files are available only inside named desktop subfolder; outside junctions blocked',async t=>{
  const f=await fixture(t);await mkdir(join(f.desktop,'案件'));await writeFile(join(f.desktop,'案件','意见.docx'),'synthetic');
  assert.equal((await f.api.find('意见','案件')).files.length,1);
  await mkdir(join(f.root,'outside'));await writeFile(join(f.root,'outside','secret.docx'),'synthetic');
  await symlink(join(f.root,'outside'),join(f.desktop,'linked'),'junction');
  await assert.rejects(f.api.find('secret','linked'),/桌面/);
  await assert.rejects(f.api.prepare(join(f.desktop,'linked','secret.docx')),/工作区或桌面/);
});
test('workspace sending never triggers desktop discovery, and results are bounded',async t=>{
  const f=await fixture(t),file=join(f.workspace,'result.txt');await writeFile(file,'synthetic');
  const api=createDesktopFileAccess({workspace:f.workspace,getDirectories:async()=>{throw Error('must not inspect desktop');}});
  assert.equal(await api.prepare(file),await realpath(file));
  await Promise.all(Array.from({length:35},(_,i)=>writeFile(join(f.desktop,`合同${i}.txt`),'synthetic')));
  const result=await f.api.find('合同');assert.equal(result.files.length,30);assert.equal(result.truncated,true);
});
