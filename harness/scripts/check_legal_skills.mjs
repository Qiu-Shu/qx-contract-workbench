// Offline check through the installed official provider; no model or network.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile, readdir, mkdir, writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const workspace=join(root,'workspace');
const reportDir=join(root,'docs','checks','legal-skills');
let providerEntry=process.argv[2];
if(!providerEntry){
  const pnpm=join(root,'node_modules','.pnpm');
  // pnpm shortens long virtual-store names on Windows.
  const packages=(await readdir(pnpm)).filter(name=>name.startsWith('@deepseek-ai+dsh-skill-file')).sort();
  assert.equal(packages.length,1,'Expected one installed official skill-filesystem version');
  const packageDir=join(pnpm,packages[0],'node_modules','@deepseek-ai','dsh-skill-filesystem');
  providerEntry=createRequire(join(packageDir,'package.json')).resolve('@deepseek-ai/dsh-skill-filesystem');
}
const {FileSystemSkillProvider}=await import(pathToFileURL(resolve(providerEntry)).href);
assert.equal(typeof FileSystemSkillProvider,'function');
const warnings=[];
const lifetime=new AbortController();
const provider=new FileSystemSkillProvider({get:()=>undefined,logger:{warn:message=>warnings.push(message)}},
  {signal:lifetime.signal,invalidate(){}},
  {watch:false,dshHome:join(reportDir,'empty-user-home'),agentsHome:join(reportDir,'empty-agents-home'),
   bundledSkillDir:join(reportDir,'empty-bundled-home')});
try {
  const observation=await provider.list({cwd:workspace});
  const candidates=Array.isArray(observation)?observation:observation.candidates;
  assert.equal(Array.isArray(observation)||observation.complete,true,'Discovery must be complete');
  const legal=candidates.filter(skill=>skill.name.startsWith('legal-zh-')||skill.name.startsWith('chinese-legal-'));
  assert.equal(legal.length,175);
  assert.equal(new Set(candidates.map(skill=>skill.name)).size,candidates.length);
  assert.ok(candidates.every(skill=>skill.source==='project-dsh'&&skill.rank===100));
  const name='legal-zh-commercial-review';
  const candidate=candidates.find(skill=>skill.name===name);
  assert.ok(candidate,'Contract review must be discoverable by its unique name');
  const loaded=await provider.get(candidate,{cwd:workspace});
  assert.equal(loaded.name,name);
  const lifecycle=JSON.parse(await readFile(join(root,'config/skill-lifecycle.json'),'utf8'));
  const intentionallyDisabled=lifecycle.skills.some(row=>row.name===name&&row.action==='disable');
  assert.equal(loaded.invocation.modelInvocable,!intentionallyDisabled);
  if(intentionallyDisabled) assert.equal(loaded.invocation.userInvocable,false);
  const primary=await provider.get(candidates.find(item=>item.name==='qx-contract-review'),{cwd:workspace});
  assert.equal(primary.invocation.modelInvocable,true);
  assert.ok(primary.content.trim());
  const original=await readFile(join(workspace,'legal-library','zh','commercial-legal','skills','review','SKILL.md'),'utf8');
  const originalBody=original.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/,'').trim();
  const adapted=await readFile(join(workspace,'.dsh/skills',name,'SKILL.md'),'utf8');
  const adaptedBody=adapted.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/,'').trim();
  assert.equal(loaded.content.trim(),adaptedBody,'Loader must return the current adapted workflow, without appending retired instructions');
  assert.equal(loaded.resourceBase.kind,'directory');
  const reference=await readFile(join(loaded.resourceBase.path,'references','contract-law-core.md'),'utf8');
  const originalReference=await readFile(join(workspace,'legal-library','zh','commercial-legal','references','contract-law-core.md'),'utf8');
  assert.equal(reference,originalReference,'Resource base must resolve the preserved contract reference');
  const context=await readFile(join(workspace,'legal-library','zh','commercial-legal','CLAUDE.md'),'utf8');
  assert.ok(context.trim());
  const addedSkills=[];
  for(const extra of ['humanizer','impeccable','design-taste-frontend','bb-browser','scrapling','windows-desktop']){
    const item=candidates.find(skill=>skill.name===extra);
    assert.ok(item,`Missing integrated skill: ${extra}`);
    const detail=await provider.get(item,{cwd:workspace});
    assert.equal(detail.invocation.modelInvocable,true);
    assert.ok(detail.content.trim());
    addedSkills.push({name:extra,modelInvocable:true,bodyCharacters:detail.content.length});
  }
  assert.deepEqual(warnings,[]);
  const report={status:'passed',providerEntry,workspace,catalogCount:candidates.length,
    addedSkills,
    scope:'Official filesystem provider discovery, preserved contract adapter/source, active primary contract workflow and six helper loads; no model calls or claim of all legal workflows executed.',
    primaryContractWorkflow:{name:primary.name,modelInvocable:true},
    loadedSkill:{name:loaded.name,path:loaded.path,source:loaded.source,modelInvocable:loaded.invocation.modelInvocable,intentionallyDisabled,
      bodyCharacters:loaded.content.length,originalBodyComplete:loaded.content.endsWith(originalBody),adaptedBodyComplete:true,resourceBase:loaded.resourceBase,
      referenceSha256:createHash('sha256').update(reference).digest('hex'),domainContextReadable:true},warnings};
  await mkdir(reportDir,{recursive:true});
  await writeFile(join(reportDir,'report.json'),JSON.stringify(report,null,2)+'\n','utf8');
  console.log(JSON.stringify(report,null,2));
} finally {
  lifetime.abort();
  await provider.dispose();
}
