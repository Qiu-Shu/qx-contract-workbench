const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {createRequire}=require('node:module');
const dsh=createRequire(require.resolve('@deepseek-ai/dsh/package.json'));
const web=createRequire(dsh.resolve('@deepseek-ai/dsh-web-app/package.json'));
function component(folder,name){
  const source=fs.readFileSync(web.resolve(`@deepseek-ai/dsh-client-ui-${folder==='chat-edit'?'chat':'attachment'}/client`),'utf8');
  const start=source.indexOf(`function ${name}(`),end=source.indexOf('//#endregion',start);
  assert.ok(start>=0&&end>start);
  const jsx=(type,props)=>({type,props});
  return vm.runInNewContext(source.slice(start,end)+`;${name}`,{
    react_jsx_runtime:{jsx,jsxs:jsx},react:{Fragment:'fragment'},EMPTY_LABELS:[],
    FileCard_module_css_default:new Proxy({},{get:(_,key)=>key}),MessageItem_module_css_default:new Proxy({},{get:(_,key)=>key}),
    _deepseek_ai_dsh_client_ui_primitives:{fileExtension:()=> 'docx',fileSizeText:()=> '42 B',FileTypeIcon:'icon',UserMessageBubble:'bubble'},
  });
}
function buttons(node){if(!node||typeof node!=='object')return [];return [...(node.type==='button'?[node]:[]),...[node.props?.children].flat(3).flatMap(buttons)];}
test('completed composer file exposes a native preview button without changing remove or error retry',()=>{
  const FileCard=component('attachment-edit','FileCard');let opened=0,removed=0,retried=0;
  const props={name:'合同.docx',bytes:42,state:'ready',labels:{remove:'移除',retry:'重试',label:'文件'},onRemove:()=>removed++,onRetry:()=>retried++,onOpen:()=>opened++};
  const ready=buttons(FileCard(props));const preview=ready.find(x=>x.props['aria-label']==='预览 合同.docx');
  assert.ok(preview);preview.props.onClick();ready.find(x=>x.props['aria-label']==='移除').props.onClick();
  assert.equal(opened,1);assert.equal(removed,1);
  assert.equal(buttons(FileCard({...props,state:'uploading'})).filter(x=>x.props['aria-label']?.startsWith('预览')).length,0);
  const error=buttons(FileCard({...props,state:'error'}));error.find(x=>x.props['aria-label']==='重试').props.onClick();
  assert.equal(retried,1);assert.equal(error.filter(x=>x.props['aria-label']?.startsWith('预览')).length,0);
});
test('historical user file opens its exact attachment reference, including duplicate names',()=>{
  const UserContent=component('chat-edit','UserContent');const opened=[];
  const first={attachmentId:'sha256:'+'a'.repeat(64),name:'合同.docx',bytes:42},second={...first,attachmentId:'sha256:'+'b'.repeat(64)};
  const result=UserContent({content:{text:'',attachments:[{type:'file',file:first},{type:'file',file:second}],extraBlocks:[]},openUploadedFile:ref=>opened.push(ref),t:key=>key});
  const preview=buttons(result).filter(x=>x.props['aria-label']==='预览 合同.docx');assert.equal(preview.length,2);
  preview[0].props.onClick();preview[1].props.onClick();assert.deepEqual(opened,[first,second]);
});
