// The fixed installation anchor owns this small selector. Business data stays in its own root.
const fs=require('node:fs'),path=require('node:path'),{randomUUID}=require('node:crypto');
function failure(code){return Object.assign(Error(code),{code});}
function normalized(value,{allowUnavailable=false}={}){
  if(typeof value!=='string'||!path.isAbsolute(value)||/[\x00-\x1f<>"|?*]/.test(value)||value.startsWith('\\\\')||(process.platform==='win32'&&(!/^[a-z]:[\\/]/i.test(value)||value.slice(2).includes(':')))||value.split(/[\\/]/).some(part=>part==='..'||/[ .]$/.test(part)||/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part)))throw failure('LOCATION_INVALID');
  const result=path.resolve(value);let current=path.parse(result).root;
  for(const part of result.slice(current.length).split(path.sep).filter(Boolean)){
    current=path.join(current,part);let stat;try{stat=fs.lstatSync(current);}catch(error){if(error.code==='ENOENT')continue;throw error;}
    if(stat.isSymbolicLink())throw failure('LOCATION_LINK_REJECTED');
  }
  const missing=[];let ancestor=result;
  while(!fs.existsSync(ancestor)){const parent=path.dirname(ancestor);if(parent===ancestor){if(allowUnavailable)return result;throw failure('LOCATION_MISSING');}missing.unshift(path.basename(ancestor));ancestor=parent;}
  return path.join(fs.realpathSync.native(ancestor),...missing);
}
function same(a,b){return process.platform==='win32'?a.toLowerCase()===b.toLowerCase():a===b;}
function contains(a,b){const rel=path.relative(a,b);return !rel||(!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel));}
function readJson(file){
  const stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>65536)throw failure('LOCATION_RECORD_INVALID');
  try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch{throw failure('LOCATION_RECORD_INVALID');}
}
function recordPath(anchor){return path.join(normalized(anchor),'.local','data-location.json');}
function readSelection(anchor){
  anchor=normalized(anchor);const file=recordPath(anchor);let record;
  try{record=readJson(file);}catch(error){if(error.code==='ENOENT')return {schema:1,anchor,data:anchor,previousData:null};throw error;}
  if(record?.schema!==1||!same(normalized(record.anchor),anchor)||typeof record.data!=='string'||(record.previousData!==null&&typeof record.previousData!=='string'))throw failure('LOCATION_RECORD_INVALID');
  // A readable selector must remain recoverable when its active removable drive is offline.
  return {...record,anchor,data:normalized(record.data,{allowUnavailable:true}),previousData:record.previousData===null?null:normalized(record.previousData,{allowUnavailable:true})};
}
function validateTarget(anchor,target){
  target=normalized(target);if(same(anchor,target))return target;
  if(contains(anchor,target)||contains(target,anchor))throw failure('LOCATION_OVERLAP');
  let stat;try{stat=fs.lstatSync(target);}catch{throw failure('LOCATION_MISSING');}
  if(!stat.isDirectory())throw failure('LOCATION_INVALID');
  let receipt,initialized;try{receipt=readJson(path.join(target,'.local','restore-activation.json'));initialized=readJson(path.join(target,'.local','initialized-payload.json'));}catch{throw failure('LOCATION_RESTORE_NOT_READY');}
  if(receipt?.schema!==1||receipt.phase!=='ready'||!same(normalized(receipt.data),target)||initialized?.schema!==2||!same(normalized(initialized.data),target))throw failure('LOCATION_RESTORE_NOT_READY');
  require('./installed-stop.cjs').assertRestoreReviewed(target);return target;
}
function writeSelection(anchor,record){
  const file=recordPath(anchor);fs.mkdirSync(path.dirname(file),{recursive:true});normalized(path.dirname(file));
  if(fs.existsSync(file))readJson(file);
  const temporary=file+'.'+randomUUID()+'.tmp';
  try{fs.writeFileSync(temporary,JSON.stringify({...record,updatedAt:new Date().toISOString()},null,2),{flag:'wx',mode:0o600});fs.renameSync(temporary,file);}finally{try{fs.unlinkSync(temporary);}catch(error){if(error.code!=='ENOENT')throw error;}}
  return record;
}
function resolveDataLocation(anchor){const record=readSelection(anchor);validateTarget(record.anchor,record.data);return record;}
function selectDataLocation(anchor,target){
  const before=resolveDataLocation(anchor);target=validateTarget(before.anchor,target);
  if(!same(before.data,target)&&(contains(before.data,target)||contains(target,before.data)))throw failure('LOCATION_OVERLAP');
  if(same(before.data,target))return before;
  return writeSelection(before.anchor,{schema:1,anchor:before.anchor,data:target,previousData:before.data});
}
function rollbackDataLocation(anchor){
  const before=readSelection(anchor);if(!before.previousData)throw failure('LOCATION_NO_PREVIOUS');
  const target=validateTarget(before.anchor,before.previousData);
  return writeSelection(before.anchor,{schema:1,anchor:before.anchor,data:target,previousData:before.data});
}
function returnToOriginalData(anchor){
  anchor=normalized(anchor);const file=recordPath(anchor);
  if(fs.existsSync(file)){
    const stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1)throw failure('LOCATION_RECORD_INVALID');
    const evidence=fs.existsSync(file+'.previous')?file+'.previous.'+randomUUID():file+'.previous';
    fs.renameSync(file,evidence);
  }
  return writeSelection(anchor,{schema:1,anchor,data:anchor,previousData:null});
}
module.exports={resolveDataLocation,selectDataLocation,rollbackDataLocation,returnToOriginalData,readSelection,normalized};
