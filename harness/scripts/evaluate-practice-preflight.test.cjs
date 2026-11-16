const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const {createModelCredentialStore}=require('../desktop/model-credentials.cjs');
const root=path.resolve(__dirname,'..');

for(const mode of ['missing-runtime','existing-result'])test('live evaluator fails '+mode+' even when the credential boundary catches callback errors',async t=>{
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'qx-e2e-preflight-'));
 t.after(()=>{
  assert.ok(path.resolve(temporary).startsWith(path.resolve(os.tmpdir())+path.sep+'qx-e2e-preflight-'));
  fs.rmSync(temporary,{recursive:true,force:true});
 });
 const safeStorage={isAsyncEncryptionAvailable:async()=>true,encryptStringAsync:async s=>Buffer.from(s),decryptStringAsync:async b=>({result:b.toString(),shouldReEncrypt:false})};
 const secret='synthetic-review-secret-never-valid';
 const store=createModelCredentialStore({dataParent:path.join(temporary,'desktop'),safeStorage,platform:'win32'});
 assert.equal((await store.save(secret)).status,'saved');
 const report=path.join(temporary,'harness/docs/checks/employment-live-20261116');
 const output=path.join(report,'e2e/offline-review/wage-supported.json');
 if(mode==='existing-result'){fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,'preserved-result');}
 let completion,exitCode=null,fetches=0;
 const env={QX_REAL_MODEL_TEST:'1',QX_SKILL_EVAL_CAMPAIGN:'employment-live-20261116',APPDATA:temporary};
 const app={setPath(){},whenReady(){return {then(fn){completion=fn();return completion;}}},exit(code){exitCode=code}};
 const localRequire=name=>{
  if(name==='electron')return {app,safeStorage};
  if(name==='../desktop/model-credentials.cjs')return {createModelCredentialStore:()=>store};
  if(name==='./skill-eval-campaign.cjs')return {evaluationPaths:workspace=>require('./skill-eval-campaign.cjs').evaluationPaths(workspace,env)};
  if(name.startsWith('./'))return require(path.join(root,'scripts',name));
  return require(name);
 };
 const context={require:localRequire,__dirname:path.join(temporary,'harness/scripts'),
  process:{argv:['node','evaluate_practice_e2e.cjs','offline-review','wage-supported'],env,pid:12345},
  console,Buffer,setTimeout,clearTimeout,AbortSignal,fetch:()=>{fetches++;throw Error('Network forbidden in offline regression');}};
 vm.runInNewContext(fs.readFileSync(path.join(root,'scripts/evaluate_practice_e2e.cjs'),'utf8'),context,{filename:'evaluate_practice_e2e.cjs'});
 await completion;
 assert.equal(fetches,0);
 assert.equal(exitCode,1);
 const progress=fs.readFileSync(path.join(report,'e2e/offline-review/progress.jsonl'),'utf8');
 assert.match(progress,/run-failed/);assert.equal(progress.includes(secret),false);
 assert.equal(fs.existsSync(path.join(temporary,'harness/docs/checks/skills-quality/model/run.lock')),false);
 if(mode==='existing-result')assert.equal(fs.readFileSync(output,'utf8'),'preserved-result');
});
