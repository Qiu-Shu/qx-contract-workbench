// Read-only checks of the generated candidate; never starts the installed app.
const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {createRequire}=require('node:module');
const asar=require('D:/qx-contract-workbench-20261102/desktop/node_modules/@electron/asar');
const yaml=createRequire(require.resolve('electron-updater'))('js-yaml');
const {verifyInstaller}=require('../desktop/update-integrity.cjs');
const root=path.resolve(__dirname,'..');
const output=path.resolve(process.argv[2]);
const hash=value=>createHash('sha256').update(value).digest('hex');
async function main(){
  const manifest=yaml.load(fs.readFileSync(path.join(output,'latest.yml'),'utf8'));
  const publicKey=JSON.parse(fs.readFileSync(path.join(root,'desktop/update-config.json'),'utf8')).publicKey;
  const installer=path.join(output,manifest.files[0].url);
  await verifyInstaller(installer,manifest,publicKey);
  const resources=path.join(path.resolve(process.argv[3]||path.join(output,'win-unpacked')),'resources'),payload=path.join(resources,'workbench');
  const checked=[];
  for(const [source,target] of [
    ['bridge/case_memory.py','bridge/case_memory.py'],['bridge/case_memory_server.py','bridge/case_memory_server.py'],
    ['plugins/case-memory/index.mjs','plugins/case-memory/index.mjs'],
    ['desktop/case-memory-runtime.cjs','desktop-runner/case-memory-runtime.cjs'],
    ['desktop/installed-runtime.cjs','desktop-runner/installed-runtime.cjs'],
    ['desktop/installed-migrations.cjs','desktop-runner/installed-migrations.cjs'],
    ['desktop/integration/client.js','node_modules/@qunxing/desktop-session/client.js'],
    ['packaging/case-memory-requirements.lock','config/case-memory-requirements.lock'],
    ['bridge/privacy.py','bridge/privacy.py'],['plugins/privacy/index.mjs','plugins/privacy/index.mjs'],
    ['plugins/privacy/client.js','plugins/privacy/client.js'],['plugins/privacy/review.js','plugins/privacy/review.js'],
  ]){
    if(hash(fs.readFileSync(path.join(root,source)))!==hash(fs.readFileSync(path.join(payload,target))))throw Error('Source mismatch: '+target);
    checked.push(target);
  }
  for(const name of ['case-memory-runtime.cjs','installed-runtime.cjs','installed-migrations.cjs']){
    if(hash(asar.extractFile(path.join(resources,'app.asar'),name))!==hash(fs.readFileSync(path.join(root,'desktop',name))))throw Error('Archive source mismatch: '+name);
    checked.push('app.asar/'+name);
  }
  const config=JSON.parse(fs.readFileSync(path.join(payload,'config/portable.json'),'utf8'));
  const plugins=config.flatMap(group=>group.insert||[]);
  const memory=plugins.find(plugin=>plugin.id==='qx-case-memory');
  if(!memory||!plugins.some(plugin=>plugin.id==='qx-case-memory-ui'))throw Error('Missing case memory configuration');
  if(memory.config.env.QX_HINDSIGHT_TOKEN?.__jsExpr!=="process.env.QX_HINDSIGHT_TOKEN || ''")throw Error('Missing runtime-only credential reference');
  if(!fs.readFileSync(path.join(payload,'workspace-seed/AGENTS.md'),'utf8').includes('## 案件记忆'))throw Error('Missing case memory rules');
  if(fs.existsSync(path.join(payload,'plugins/case-memory/ui-check.py')))throw Error('Development fixture in package');
  const result={passed:true,version:manifest.version,installer,size:fs.statSync(installer).size,
    signatureAndHashVerified:true,packagedSourcesMatch:checked,configurationVerified:true,installedOnUserMachine:false,published:false};
  fs.writeFileSync(path.join(output,'case-memory-package-check.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
