const fs=require('node:fs/promises');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const {hash,TOOL_HASHES}=require('./incremental-package.cjs');
const URL='https://github.com/sisong/HDiffPatch/releases/download/v5.1.3/hdiffpatch_v5.1.3_bin_windows64.zip';
const ARCHIVE_SHA='77f141386e5d8f785c1c846e10fbbc19b6c05aa00e3f59cc44670fb3f0e2ae94';
async function verify(dir){for(const [name,digest] of Object.entries(TOOL_HASHES))if(await hash(path.join(dir,name))!==digest)throw Error('HDiffPatch tool checksum mismatch');return dir;}
async function ensureHdiffTools(sevenZip){
  sevenZip??=await require('./toolchain.cjs').sevenZip();
  if(process.env.QX_HDIFFPATCH_DIR)return verify(path.resolve(process.env.QX_HDIFFPATCH_DIR));
  const cache=path.resolve(process.env.QX_BUILD_CACHE||path.join(__dirname,'../.local/build-tools'),'hdiffpatch/5.1.3'),dir=path.join(cache,'windows64');
  try{return await verify(dir)}catch(error){if(error.code!=='ENOENT')throw error}
  const response=await fetch(URL,{signal:AbortSignal.timeout(120000)});if(!response.ok)throw Error('Cannot download fixed HDiffPatch tools: HTTP '+response.status);
  const chunks=[];let size=0;for await(const chunk of response.body){size+=chunk.length;if(size>16*1024*1024)throw Error('Unexpected HDiffPatch archive size');chunks.push(chunk)}
  const archive=Buffer.concat(chunks);if(createHash('sha256').update(archive).digest('hex')!==ARCHIVE_SHA)throw Error('HDiffPatch archive checksum mismatch');
  await fs.mkdir(cache,{recursive:true});const zip=path.join(cache,'official.zip');await fs.writeFile(zip,archive);
  await promisify(execFile)(sevenZip,['x',zip,'-o'+cache,'-y','-bso0','-bsp0'],{windowsHide:true});
  return verify(dir);
}
module.exports={ensureHdiffTools};
