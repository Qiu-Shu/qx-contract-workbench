export {compareContracts,resolveContractReference} from './contract-compare.mjs';
export {installContractComparison} from './contract-compare-api.mjs';
// Resolve only an opaque upload reference; actual file access remains with workspaceFiles.
export function attachmentPreviewPath(attachments,input){
  if(!input||typeof input!=='object'||Object.keys(input).some(key=>!['attachmentId','name','bytes'].includes(key))||
    typeof input.attachmentId!=='string'||!/^sha256:[a-f0-9]{64}$/.test(input.attachmentId)||
    typeof input.name!=='string'||!input.name||input.name.length>255||input.name==='.'||input.name==='..'||
    /[\\/:*?"<>|\x00-\x1f\x7f]/.test(input.name)||/[. ]$/.test(input.name)||
    !Number.isSafeInteger(input.bytes)||input.bytes<0)throw Error('Invalid attachment');
  const path=attachments?.fileHostPath?.({attachmentId:input.attachmentId,name:input.name,bytes:input.bytes});
  if(typeof path!=='string'||!path)throw Error('Attachment preview unavailable');
  return path;
}
