const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
for(const packaged of [false,true])test((packaged?'packaged: ':'source: ')+'UI fixture supplies the business preset, original skills and isolated upload storage without launching a model',async t=>{
 const out=fs.mkdtempSync(path.join(os.tmpdir(),'qx-ui-fixture-'));t.after(()=>fs.rmSync(out,{recursive:true,force:true}));
 let launch;const links=[];
 const filesystem={...fs,symlinkSync:(from,to)=>links.push({from,to}),createWriteStream:()=>({write(){}})};
 const child=new EventEmitter();child.stdout=new EventEmitter();child.stderr=new EventEmitter();child.kill=()=>{};
 const environment={QX_TEST_APP:path.join(out,'read-only-app'),QX_TEST_OUTPUT_ROOT:out,QX_TEST_PACKAGED:packaged?'1':'0'};
 if(packaged)for(const skill of ['qx-client-reception','qx-contract-review','qx-case-work','qx-mock-hearing'])
   fs.cpSync(path.join(__dirname,'../workspace-seed/.dsh/skills',skill),path.join(environment.QX_TEST_APP,'workspace-seed/.dsh/skills',skill),{recursive:true});
 const script=path.join(__dirname,'contract-compare-smoke.cjs');
 vm.runInNewContext(fs.readFileSync(script,'utf8'),{__dirname,require:name=>name==='node:fs'?filesystem:name==='node:child_process'?{spawn:(...args)=>{launch=args;return child}}:require(name),process:{env:environment,stdout:{write(){}},on(){},exit(){throw Error('unexpected exit')}}},{filename:script});
 const options=launch[2],profile=path.join(options.env.DSH_HOME,'profiles/web');
 const patches=JSON.parse(fs.readFileSync(path.join(profile,'cordis.patch.yml'),'utf8'));
 const inserts=patches.flatMap(p=>p.insert||[]);
 const content=inserts.find(p=>p.id==='qx-content-watch');
 assert.ok(content,'the fourth footer action must use the real content-watch plugin');
 assert.equal(content.config.workspace,options.cwd);
 assert.ok(content.config.stateDir.startsWith(out+path.sep),'content-watch state must stay isolated');
 const businessSource=fs.readFileSync(path.join(__dirname,'../desktop/integration/business-client.js'),'utf8');
 const presetId=businessSource.match(/agentPreset:'([^']+)'/)[1];
 const preset=inserts.find(p=>p.name==='@deepseek-ai/dsh-agent-preset'&&p.config?.id===presetId);
 assert.ok(preset,'business entry preset is missing from the UI fixture');
 assert.ok(preset.config.plugins.some(p=>p.name==='@deepseek-ai/dsh-skill-filesystem'));
 assert.ok(preset.config.plugins.some(p=>p.name==='@deepseek-ai/dsh-tool-skill'));
 const {instructionsFor}=await import('../desktop/integration/business-workflows.mjs');
 for(const mode of ['reception','contract','case','hearing']){
   const skill=instructionsFor({mode,stage:'new'}).match(/主动加载 ([\w-]+)/)[1];
   const fixtureFile=path.join(options.cwd,'.dsh/skills',skill,'SKILL.md');
   assert.equal(fs.readFileSync(fixtureFile,'utf8'),fs.readFileSync(path.join(__dirname,'../workspace-seed/.dsh/skills',skill,'SKILL.md'),'utf8'));
 }
 assert.match(instructionsFor({mode:'media'}),/media_context.*media_save.*media_review.*media_export.*media_job/);
 assert.equal(patches.find(p=>p.id==='attachment-local')?.config.dshHome,path.join(options.cwd,'inbox/.harness'));
 assert.equal(options.env.DEEPSEEK_BASE_URL,'http://127.0.0.1:1');
 assert.equal(options.env.DSH_TELEMETRY_MODE,'OFF');
 assert.ok(links.every(p=>p.to.startsWith(out+path.sep)));
});
