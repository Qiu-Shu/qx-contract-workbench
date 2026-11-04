// Exercise the official provider and actual skill-tool boundary; no model requests.
import assert from 'node:assert/strict';
import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {checkSkillRoutes,selfTest as routeParserSelfTest} from './check_skill_routes.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),workspace=join(root,'workspace');
const spec=JSON.parse(await readFile(join(root,'config/skill-lifecycle.json'),'utf8'));
const additions=JSON.parse(await readFile(join(root,'config/practice-skill-additions.json'),'utf8'));
assert.equal(spec.originalBatchCount,91);
assert.equal(spec.skills.length,91+spec.dependencyCount);assert.equal(new Set(spec.skills.map(r=>r.name)).size,spec.skills.length);
async function packageEntry(prefix,name){
 const names=(await readdir(join(root,'node_modules/.pnpm'))).filter(n=>n.startsWith(prefix));assert.equal(names.length,1);
 return createRequire(join(root,'node_modules/.pnpm',names[0],'node_modules',name,'package.json')).resolve(name);
}
const {FileSystemSkillProvider}=await import(pathToFileURL(await packageEntry('@deepseek-ai+dsh-skill-file','@deepseek-ai/dsh-skill-filesystem')).href);
const {apply}=await import(pathToFileURL(await packageEntry('@deepseek-ai+dsh-tool-skill','@deepseek-ai/dsh-tool-skill')).href);
const warnings=[],control=new AbortController(),out=join(root,'docs/checks/practice-gaps/release-selection/runtime');
const provider=new FileSystemSkillProvider({get:()=>undefined,logger:{warn:s=>warnings.push(s)}},{signal:control.signal,invalidate(){}},
 {watch:false,dshHome:join(out,'empty-dsh'),agentsHome:join(out,'empty-agents'),bundledSkillDir:join(out,'empty-bundled')});
try{
 const observation=await provider.list({cwd:workspace}),candidates=Array.isArray(observation)?observation:observation.candidates;
 const definitions=[];for(const candidate of candidates)definitions.push(await provider.get(candidate,{cwd:workspace}));
 assert.equal(definitions.length,additions.baselineCount+additions.skills.length);assert.deepEqual(warnings,[]);
 const byName=new Map(definitions.map(r=>[r.name,r])),hooks=[];let tool;
 for(const name of additions.withheld||[])assert.ok(!byName.has(name),'Withheld Skill discovered: '+name);
 for(const name of additions.skills){assert.equal(byName.get(name)?.invocation.modelInvocable,true,name);assert.ok(byName.get(name)?.content.trim());}
 apply({tools:{register:t=>{tool=t;},get:()=>tool},skills:{list:async()=>definitions,get:async n=>byName.get(n),snapshot:async()=>({skills:definitions,complete:true})},
  workingDirectory:{ensure:async()=>workspace},on:(_,f)=>hooks.push(f)});
 assert.equal(tool.name,'skill');
 const exec={signal:control.signal},disabled=spec.skills.filter(r=>r.action==='disable');
 for(const row of disabled){
  const skill=byName.get(row.name);assert.equal(skill.invocation.modelInvocable,false,row.name);assert.equal(skill.invocation.userInvocable,false,row.name);
  await assert.rejects(tool.execute({name:row.name},exec),/not available for model invocation/);
 }
  for(const row of spec.skills.filter(r=>r.action!=='disable')){
  const value=await tool.execute({name:row.name},exec);assert.equal(value.name,row.name);assert.ok(value.content.trim());
  if(row.replacement&&byName.has(row.replacement))assert.equal(byName.get(row.replacement).invocation.modelInvocable,true,row.name+' replacement');
 }
 routeParserSelfTest();
 const routes=await checkSkillRoutes(root);
 assert.equal(routes.violations.length,0,JSON.stringify(routes.violations));
 const agent={session:{surface:{nodes:[]},seq:0}};
 const rendered=await hooks.at(-1)({agent,signal:control.signal},async()=>({kind:'continue',messages:[]}));
 const catalog=JSON.stringify(rendered.messages);
 for(const row of disabled)assert.ok(!catalog.includes('"'+row.name+'"'),row.name+' leaked into automatic catalog');
 for(const name of additions.withheld||[]){
  assert.ok(!catalog.includes('"'+name+'"'),name+' leaked into automatic catalog');
  await assert.rejects(tool.execute({name},exec));
 }
 for(const name of ['qx-case-work','qx-contract-review','qx-client-reception','qx-mock-hearing'])assert.ok(catalog.includes(name));
  const report={officialProvider:true,officialToolBoundary:true,discovered:definitions.length,practiceSkills:additions.skills,disabled:disabled.map(r=>r.name),
  automaticallyAvailable:definitions.filter(r=>r.invocation.modelInvocable).length,repairedInvocationsVerified:spec.skills.length-disabled.length,
  evidence:'Disabled entries rejected by actual Harness skill execute and absent from actual rendered catalog; active replacements load.',routes,warnings};
 await mkdir(out,{recursive:true});await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
}finally{control.abort();await provider.dispose();}
