const {verify,createHash}=require('node:crypto');
const {createReadStream}=require('node:fs');
const {stat}=require('node:fs/promises');
function releasePayload(info){
  if(!info||!/^\d+\.\d+\.\d+$/.test(info.version)||!Array.isArray(info.files)||info.files.length!==1)throw Error('UPDATE_SIGNATURE');
  const file=info.files[0];
  if(file.url!==`Qunxing-Workbench-${info.version}-Setup.exe`||!Number.isSafeInteger(file.size)||file.size<=0||
    typeof file.sha512!=='string'||!/^[A-Za-z0-9+/]{86}==$/.test(file.sha512)||typeof info.releaseNotes!=='string'||info.releaseNotes.length>12000)throw Error('UPDATE_SIGNATURE');
  return Buffer.from(JSON.stringify({version:info.version,files:[{url:file.url,size:file.size,sha512:file.sha512}],releaseNotes:info.releaseNotes}));
}
function verifyRelease(info,publicKey){
  if(typeof info?.qxSignature!=='string'||!verify(null,releasePayload(info),publicKey,Buffer.from(info.qxSignature,'base64')))throw Error('UPDATE_SIGNATURE');
  return info;
}
async function verifyInstaller(file,info,publicKey){
  verifyRelease(info,publicKey);
  if((await stat(file)).size!==info.files[0].size)throw Error('UPDATE_SIGNATURE');
  const hash=createHash('sha512');for await(const chunk of createReadStream(file))hash.update(chunk);
  if(hash.digest('base64')!==info.files[0].sha512)throw Error('UPDATE_SIGNATURE');
}
module.exports={releasePayload,verifyRelease,verifyInstaller};
