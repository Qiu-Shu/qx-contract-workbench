const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const {generateKeyPairSync,createPublicKey,sign}=require('node:crypto');
const yaml=createRequire(require('./toolchain.cjs').load.resolve('app-builder-lib'))('js-yaml');
const {releasePayload,verifyRelease}=require('../desktop/update-integrity.cjs');
const root=path.resolve(__dirname,'..');
const keyPath=process.env.QX_UPDATE_SIGNING_KEY||path.join(root,'.qx-private/update-signing-key.pem');
const configPath=path.join(root,'desktop/update-config.json');
function initialize(){
  if(fs.existsSync(keyPath)||fs.existsSync(configPath))throw Error('Signing configuration already exists; never overwrite an update identity.');
  const pair=generateKeyPairSync('ed25519');fs.mkdirSync(path.dirname(keyPath),{recursive:true});
  fs.writeFileSync(keyPath,pair.privateKey.export({type:'pkcs8',format:'pem'}),{flag:'wx',mode:0o600});
  fs.writeFileSync(configPath,JSON.stringify({feed:{provider:'github',owner:'Qiu-Shu',repo:'qx-contract-workbench',releaseType:'release'},publicKey:pair.publicKey.export({type:'spki',format:'pem'})},null,2)+'\n',{flag:'wx'});
  console.log('Update signing identity created. Private key remains in the ignored private directory.');
}
function signManifest(directory,notes){
  const file=path.join(directory,'latest.yml');
  const info=yaml.load(fs.readFileSync(file,'utf8'));
  const config=JSON.parse(fs.readFileSync(configPath,'utf8')),key=fs.readFileSync(keyPath,'utf8');
  if(createPublicKey(key).export({type:'spki',format:'pem'})!==config.publicKey)throw Error('Signing key does not match bundled public key');
  info.releaseNotes=notes;
  info.qxSignature=sign(null,releasePayload(info),key).toString('base64');verifyRelease(info,config.publicKey);
  fs.writeFileSync(file,yaml.dump(info,{lineWidth:-1}));
  return file;
}
module.exports={signManifest};
if(require.main===module){
  if(process.argv[2]==='init')initialize();
  else if(process.argv[2]==='sign')console.log(signManifest(path.resolve(process.argv[3]),fs.readFileSync(process.argv[4],'utf8')));
  else throw Error('Use init or sign <release directory> <notes file>');
}
