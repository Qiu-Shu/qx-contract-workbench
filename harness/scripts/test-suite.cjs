// Explicit modes keep native/payload checks and paid evaluations out of npm test.
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const windows=new Set([
  'packaging/incremental-install.test.cjs','packaging/incremental-package.test.cjs',
  'tests/audit-upgrade.test.cjs','tests/audit-spec-root.test.mjs','tests/audit-standards-provider.test.mjs',
  'tests/unified-portability.test.mjs',
  'plugins/case-memory/mcp-env.test.mjs',
  'plugins/wechat/test/login.test.mjs','plugins/wechat/test/qx-plugin.test.mjs',
  'plugins/wechat/test/qx-settings.test.mjs','plugins/wechat/test/credentials-windows.test.mjs',
  'bridge/test_image_objects.py','bridge/test_title_excerpt.py','bridge/test_privacy.py',
]);
function discover(){
  const node=[],python=[];
  function visit(folder){
    for(const entry of fs.readdirSync(path.join(root,folder),{withFileTypes:true})){
      if(entry.isSymbolicLink()||['node_modules','.local','.fixtures','__pycache__'].includes(entry.name))continue;
      const file=folder+'/'+entry.name;
      if(entry.isDirectory())visit(file);
      else if(/\.test\.(?:cjs|mjs|js)$/.test(entry.name)||['scripts/test-practice-e2e-checks.cjs','plugins/privacy/test-privacy.mjs','plugins/privacy/test-review.mjs'].includes(file))node.push(file);
      else if(/^test_.*\.py$/.test(entry.name))python.push(file);
    }
  }
  for(const folder of ['desktop','plugins','packaging','scripts','bridge','tests','evals'])visit(folder);
  return {node:node.sort(),python:python.sort()};
}
function plan(mode){
  const all=discover();
  return Object.fromEntries(Object.entries(all).map(([kind,files])=>[kind,files.filter(file=>windows.has(file)===(mode==='windows'))]));
}
function run(command,args,env){
  const result=spawnSync(command,args,{cwd:root,env,windowsHide:true,stdio:'inherit'});
  if(result.error){console.error(result.error.message);return 1;}
  return result.status??1;
}
function testEnvironment(){
  const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONIOENCODING:'utf-8',
    PYTEST_DISABLE_PLUGIN_AUTOLOAD:'1',QX_LEGACY_ROOT:path.join(root,'legacy'),
    QX_TEST_NODE:process.execPath,QX_TEST_PYTHON:process.env.QX_TEST_PYTHON||(process.platform==='win32'?'python':'python3'),
    PYTHONPATH:[path.join(root,'bridge'),path.join(root,'legacy/src'),process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    DEEPSEEK_API_KEY:'',OPENAI_API_KEY:'',ANTHROPIC_API_KEY:'',QX_HINDSIGHT_URL:'',QX_HINDSIGHT_TOKEN:'',QX_HINDSIGHT_INSTANCE_ID:''};
  return env;
}
function checkQualityResults(directory,cases){
  for(const item of cases){
    const result=JSON.parse(fs.readFileSync(path.join(directory,item.id+'.json'),'utf8'));
    if(result.status!=='response-received')throw Error('Model evaluation failed or incomplete: '+item.id);
  }
}
function quality(args){
  if(process.env.QX_REAL_MODEL_TEST!=='1')throw Error('Paid synthetic quality evaluation requires QX_REAL_MODEL_TEST=1, an explicit phase and scenario JSON files.');
  if(!args.length||!args[0]||args.length<2)throw Error('Usage: npm run test:quality -- <phase> <synthetic-scenarios.json> [...]');
  const electron=process.env.QX_TEST_ELECTRON;
  if(!electron||!fs.existsSync(electron))throw Error('Set QX_TEST_ELECTRON to an installed Electron executable.');
  const {evaluationPaths}=require('./skill-eval-campaign.cjs'),output=path.join(evaluationPaths(root).reportRoot,'model',args[0]);
  const cases=args.slice(1).flatMap(file=>JSON.parse(fs.readFileSync(path.resolve(root,file),'utf8'))).filter(item=>args[0].endsWith('smoke')?item.kind==='smoke':item.kind!=='smoke');
  if(!cases.length)throw Error('No scenarios selected.');
  if(fs.existsSync(output))throw Error('Evaluation output exists; use a new phase to avoid counting stale results.');
  const status=run(electron,['scripts/evaluate_skills.cjs',...args],process.env);
  if(status)return status;
  checkQualityResults(output,cases);
  console.log(`${cases.length} model responses collected. Legal and semantic quality still requires review.`);
  return 0;
}
function main(args=process.argv.slice(2)){
  const mode=args.shift()||'offline';
  if(mode==='quality')return quality(args);
  if(!['offline','windows'].includes(mode))throw Error('Use offline, windows, or quality.');
  const selected=plan(mode);
  if(args.length===1&&args[0]==='--list'){console.log(JSON.stringify(selected,null,2));return 0;}
  if(args.length)throw Error('Only --list is supported for test suites.');
  const env=testEnvironment();
  if(mode==='windows'){
    if(process.platform!=='win32')throw Error('Windows integration tests require Windows.');
    for(const key of ['QX_TEST_APP','QX_HDIFFPATCH_DIR'])if(!env[key]||!fs.existsSync(env[key]))throw Error('Windows integration prerequisite missing: '+key);
    env.QX_HPATCHZ_TEST_EXE=path.join(env.QX_HDIFFPATCH_DIR,'hpatchz.exe');
    env.QX_HDIFFZ_TEST_EXE=path.join(env.QX_HDIFFPATCH_DIR,'hdiffz.exe');
    for(const key of ['QX_HPATCHZ_TEST_EXE','QX_HDIFFZ_TEST_EXE'])if(!fs.existsSync(env[key]))throw Error('Windows integration prerequisite missing: '+key);
  }
  console.log(`${mode}: ${selected.node.length} Node files, ${selected.python.length} Python files; synthetic data, no paid model requests.`);
  const node=run(process.execPath,['--test','--test-concurrency=4',...selected.node],env);
  const python=run(env.QX_TEST_PYTHON,['-m','pytest','-q',...selected.python],env);
  return node||python;
}
if(require.main===module){try{process.exitCode=main();}catch(error){console.error(error.message);process.exitCode=1;}}
module.exports={plan,run,testEnvironment,checkQualityResults};
