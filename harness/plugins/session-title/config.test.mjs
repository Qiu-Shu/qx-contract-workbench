import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {realpathSync,mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {dirname,resolve} from 'node:path';

test('real profile composition disables the old provider and registers the upload-aware plugin',async t=>{
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
  const local=createRequire(root+'/package.json');
  const anchor=realpathSync(local.resolve('@deepseek-ai/dsh/package.json'));
  const dsh=createRequire(anchor);
  const boot=await import(pathToFileURL(dsh.resolve('@deepseek-ai/dsh-app-boot')).href);
  const directory=mkdtempSync(resolve(tmpdir(),'qx-title-profile-'));
  t.after(()=>rmSync(directory,{recursive:true,force:true}));
  writeFileSync(resolve(directory,'package.json'),readFileSync(resolve(root,'packaging/payload-config/profile-package.json')));
  const portable=readFileSync(resolve(root,'packaging/payload-config/portable.json'),'utf8').replaceAll('@APP@',root.replaceAll('\\','/')).replaceAll('@DATA@',directory.replaceAll('\\','/'));
  writeFileSync(resolve(directory,'cordis.patch.yml'),portable);
  const profile=boot.loadProfileDirectory('dsh',directory,anchor);
  const warnings=[];
  const rows=boot.composeEntries([...profile.layers.map(x=>x.patches),profile.patches],message=>warnings.push(message));
  assert.deepEqual(warnings,[]);
  assert.equal(rows.find(x=>x.id==='session-title-llm')?.disabled,true);
  const plugin=rows.filter(x=>x.id==='qx-first-content-title');
  assert.equal(plugin.length,1);assert.ok(!plugin[0].disabled);
  assert.ok(plugin[0].name.endsWith('/plugins/session-title/index.mjs'));
});
