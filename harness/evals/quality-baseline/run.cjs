const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process'),{randomUUID}=require('node:crypto');
const root=path.resolve(__dirname,'../..'),args=process.argv.slice(2),live=args.includes('--live');
if(args.some(a=>a!=='--live'))throw Error('Usage: npm run eval:workflow [-- --live]');
if(live&&(process.env.QX_REAL_MODEL_TEST!=='1'||!process.env.QX_EVAL_BUDGET_CNY||!process.env.DEEPSEEK_API_KEY))throw Error('Live evaluation needs explicit QX_REAL_MODEL_TEST=1, QX_EVAL_BUDGET_CNY and DEEPSEEK_API_KEY. No calls made.');
const runId=new Date().toISOString().replaceAll(/[:.]/g,'-')+'-'+randomUUID().slice(0,8);
const directory=path.join(root,'.local/quality-baseline',runId);fs.mkdirSync(directory,{recursive:true});
const sources=['run.cjs','network-policy.cjs','preload.cjs','guarded-python.py','cases.cjs','provider.cjs','kernel.mjs','relay.py','checks.cjs','assertions.js','promptfooconfig.cjs','live.mjs','package-lock.json'].map(f=>path.join(__dirname,f));
for(const name of ['authority-check','case-comparison','issue-memo','lecture-source-pack'])sources.push(path.join(root,'config/skills/qx-'+name+'/SKILL.md'));
sources.push(path.join(root,'workspace-seed/legal-library/workbench/legal-research.md'));
fs.writeFileSync(path.join(directory,'manifest.json'),JSON.stringify({startedAt:new Date().toISOString(),mode:live?'live':'scripted',node:process.version,
 qualityStatus:'not_reviewed',syntheticOnly:true,sourceHashes:sources.map(file=>({path:path.relative(root,file).replaceAll('\\','/'),sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(file)).digest('hex')}))},null,2)+'\n');
const env={...process.env,QX_EVAL_RUN_ID:runId,QX_EVAL_MODE:live?'live':'scripted',
 PROMPTFOO_DISABLE_TELEMETRY:'1',PROMPTFOO_DISABLE_UPDATE:'1',PROMPTFOO_DISABLE_REMOTE_GENERATION:'true',
 PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION:'true',PROMPTFOO_DISABLE_SHARING:'1',PROMPTFOO_DISABLE_SHARE_EMAIL_REQUEST:'1',
 NODE_OPTIONS:'',QX_EVAL_NETWORK_LOG:path.join(directory,'network.jsonl'),
 PROMPTFOO_CONFIG_DIR:path.join(directory,'promptfoo'),PYTHONIOENCODING:'utf-8'};
if(!live)for(const key of ['DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])env[key]='';
const cli=path.join(__dirname,'node_modules/promptfoo/dist/src/main.js');
if(!fs.existsSync(cli))throw Error('Install the isolated development dependencies: cd evals/quality-baseline; npm ci.');
const result=spawnSync(process.execPath,['--require',path.join(__dirname,'preload.cjs'),cli,'eval','--config',path.join(__dirname,'promptfooconfig.cjs'),
 '--no-cache','--no-progress-bar','--max-concurrency','1','--output',path.join(directory,'promptfoo.json')],{cwd:__dirname,env,stdio:'inherit',windowsHide:true});
console.log('Evidence: '+directory+'; mode '+env.QX_EVAL_MODE+'; legal quality: not reviewed');
if(result.error)console.error(result.error.message);process.exitCode=result.status??1;
try{
 const network=require('./network-policy.cjs').summarize(env.QX_EVAL_NETWORK_LOG);
 network.passed=network.passed&&network.telemetryPatched&&network.configProbePatched&&network.guardedProcesses.some(p=>p.runtime==='node')
  &&network.guardedProcesses.some(p=>p.runtime==='python')&&(live||network.modelRequests===0);
 fs.writeFileSync(path.join(directory,'network-summary.json'),JSON.stringify(network,null,2)+'\n');
 if(!network.passed){console.error('Evaluation network policy failed; inspect network-summary.json');process.exitCode=1;}
}catch(error){console.error('Network audit missing or invalid: '+error.message);process.exitCode=1;}
