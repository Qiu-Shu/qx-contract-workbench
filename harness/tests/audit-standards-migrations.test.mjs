import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {migrateInstalledSkillRoots}=require('../desktop/installed-migrations.cjs');

test('adding the built-in skill root retains effective custom roots from earlier patch entries',()=>{
  const data=fs.mkdtempSync(path.join(os.tmpdir(),'qx-audit-skills-'));
  const file=path.join(data,'.local/dsh-home/profiles/web/cordis.patch.yml'),custom=path.join(data,'custom-skills');
  fs.mkdirSync(path.dirname(file),{recursive:true});
  fs.writeFileSync(file,JSON.stringify([{id:'skill-filesystem',config:{customSkillDirs:[custom]}},{id:'skill-filesystem',disabled:true}]));
  migrateInstalledSkillRoots({data,portableConfig:[{id:'skill-filesystem',config:{customSkillDirs:['builtin-template']}}]});
  const rows=JSON.parse(fs.readFileSync(file,'utf8')),effective=Object.assign({},...rows.filter(r=>r.id==='skill-filesystem').map(r=>r.config||{}));
  const roots=effective.customSkillDirs.map(value=>path.resolve(value));
  assert.ok(roots.includes(path.resolve(custom)),'effective custom roots must survive a later partial entry');
  assert.ok(roots.includes(path.resolve(data,'workspace/.dsh/skills')));
  assert.equal(rows.at(-1).disabled,true);
});
