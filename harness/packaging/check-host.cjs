// Isolated real runtime check; this synthetic key cannot authorize a model request.
const {app,safeStorage}=require('electron');
const path=require('node:path');
const fs=require('node:fs');
const {createModelCredentialStore}=require('../desktop/model-credentials.cjs');
const {runHost}=require('../desktop/installed-runtime.cjs');
const data=path.resolve(__dirname,'../.local/installer-check-完整启动');
app.setPath('userData',path.join(data,'.local','host-control'));
app.whenReady().then(async()=>{
  const store=createModelCredentialStore({dataParent:path.join(data,'.local/desktop-data'),safeStorage});
  const result=await store.save('sk-synthetic-installer-test-not-a-real-key');
  if(result.status!=='saved')throw Error('Encryption self-check failed');
  const encrypted=fs.readFileSync(path.join(data,'.local/desktop-data/model-credentials/deepseek.bin'));
  if(encrypted.includes(Buffer.from('sk-synthetic')))throw Error('Plaintext credential');
  await runHost({payload:path.resolve(__dirname,'../.local/package-20261103-b/workbench'),data,store,app});
}).catch(error=>{console.error(error.message);app.exit(1)});
