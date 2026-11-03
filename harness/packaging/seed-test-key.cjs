// QA-only; excluded from the installer. Never reads or copies an existing key.
const {app,safeStorage}=require('electron');
const path=require('node:path');
const {createModelCredentialStore}=require('../desktop/model-credentials.cjs');
const data=process.env.QX_INSTALL_DATA;
if(!data||!data.includes('installer-check-'))throw Error('Isolated test directory required');
app.setName('群兴法律工作台');app.setPath('userData',path.join(data,'.local/desktop-data'));
app.whenReady().then(async()=>{
  const result=await createModelCredentialStore({dataParent:app.getPath('userData'),safeStorage}).save('sk-synthetic-packaged-installer-check-key');
  app.exit(result.status==='saved'?0:1);
}).catch(()=>app.exit(1));
