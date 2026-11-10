// Local receipt controls. Writes use the draft controller's single channel.
import * as api from './assistant-api.mjs';
import {errorText} from './assistant-render.mjs';

const ACCEPTED={
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document':['.docx'],
  'application/msword':['.doc'],
  'application/vnd.ms-excel':['.xls'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':['.xlsx'],
  'application/vnd.ms-powerpoint':['.ppt'],
  'application/vnd.openxmlformats-officedocument.presentationml.presentation':['.pptx'],
  'application/vnd.oasis.opendocument.text':['.odt'],
  'application/vnd.oasis.opendocument.spreadsheet':['.ods'],
  'application/vnd.oasis.opendocument.presentation':['.odp'],
  'application/pdf':['.pdf'],
  'text/plain':['.txt'],
  'text/markdown':['.md'],
  'text/tab-separated-values':['.tsv'],
  'application/json':['.json'],
  'text/html':['.html','.htm'],
  'application/rtf':['.rtf'],
  'image/png':['.png'],
  'image/jpeg':['.jpg','.jpeg'],
  'image/webp':['.webp'],
  'image/gif':['.gif'],
  'image/bmp':['.bmp'],
  'image/tiff':['.tif','.tiff'],
  'text/csv':['.csv'],
};
const MIME_BY_EXTENSION=Object.fromEntries(Object.entries(ACCEPTED).flatMap(([mime,extensions])=>extensions.map(extension=>[extension,mime])));
const extensionOf=name=>String(name||'').toLowerCase().match(/\.[^.]+$/)?.[0]||'';
const KIND_LABEL={docx:'Word',doc:'Word',xls:'表格',xlsx:'表格',csv:'表格',tsv:'表格',pdf:'PDF',
  ppt:'演示文稿',pptx:'演示文稿',odt:'文档',ods:'表格',odp:'演示文稿',txt:'文本',md:'Markdown',
  json:'JSON',html:'网页文档',rtf:'富文本文档',png:'图片',jpeg:'图片',webp:'图片',gif:'图片',bmp:'图片',tiff:'图片',file:'文件'};
const READING_NOTES={
  OCR_IS_UNVERIFIED:'图片文字已识别，请核对数字、日期和否定词',
  NO_READABLE_TEXT:'未识别到可读文字，请上传更清晰的文件',
  SPREADSHEET_VALUES_ONLY_FORMULAS_NOT_EXECUTED:'已读取表格保存的数值，未执行公式或外部链接',
  PRESENTATION_TEXT_ONLY:'已读取幻灯片文字与备注',
  LEGACY_PRESENTATION_TEXT_EXTRACTION:'已提取旧版幻灯片文字',
  OPENDOCUMENT_TEXT_ONLY:'已提取文档文字',
  LEGACY_WORD_TEXT_ONLY_REVISIONS_NOT_RESOLVED:'已提取旧版 Word 文字，修订记录需对照原件',
};
function readingNote(value){
  const [code,,page]=value.split(':');
  const label=READING_NOTES[code];
  return label?`${/^\d+$/.test(page||'')?`第 ${page} 页：`:''}${label}`:value;
}
function accepted(file) {
  // Browser MIME guesses vary by OS; only the backend verifies the actual bytes.
  return Object.hasOwn(MIME_BY_EXTENSION,extensionOf(file.name));
}
function canonicalFile(file) {
  const mime=MIME_BY_EXTENSION[extensionOf(file.name)];
  return file.type===mime?file:new File([file],file.name,{type:mime,lastModified:file.lastModified});
}
function kindOf(attachment) {
  const extension=extensionOf(attachment.original_name)||ACCEPTED[attachment.mime]?.[0]||'';
  const kind=extension.slice(1);
  return ({jpg:'jpeg',tif:'tiff',htm:'html'})[kind]|| (Object.hasOwn(KIND_LABEL,kind)?kind:'file');
}

export function bindMaterials({controller,readonly=false,root=document,onQueueChange=()=>{},onPreview=()=>{}}) {
  const byId=id=>root.getElementById(id);
  const node=(tag,text)=>{const item=root.createElement(tag);item.textContent=text;return item;};
  let identity=null,revision=null,previewEpoch=0,queue=[],inflight=null,previousAction=null,uploading=false,pickerEpoch=null,selectionEpoch=0;
  const previews=new Map(),objectUrls=root.defaultView?.URL;
  function releasePreviews(){for(const [file,url] of previews)if(!queue.includes(file)){objectUrls.revokeObjectURL(url);previews.delete(file);}}
  const feedback=text=>{byId('material-notice').textContent=text;};
  const action=(title,run)=>{const button=node('button',title);button.type='button';button.className='text-button';
    button.addEventListener('click',()=>void run());return button;};
  function closePreview(){++previewEpoch;byId('material-preview').hidden=true;
    byId('material-preview-content').replaceChildren();root.body.classList.remove('source-open');}
  function picker(open){byId('material-picker').hidden=!open;byId('add-material').setAttribute('aria-expanded',String(open));}
  function busy(){return readonly || controller.state.loading || Boolean(controller.state.materialAction)
    || ['saving','conflict','revoked'].includes(controller.state.status);}
  function drawQueue(){
    releasePreviews();
    const host=byId('material-queue');host.replaceChildren();
    for(const file of queue){
      const chip=node('span','');chip.className='queue-chip';
      chip.append(node('span',`${file.name}（${(file.size/1024).toFixed(1)} KiB）`));
      if(/\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name)&&objectUrls?.createObjectURL){
        if(!previews.has(file))previews.set(file,objectUrls.createObjectURL(canonicalFile(file)));
        const image=root.createElement('img');image.src=previews.get(file);image.alt='';image.className='queue-preview';
        chip.append(image);
      }
      const remove=node('button','×');remove.type='button';remove.className='queue-remove';
      remove.setAttribute('aria-label',`移除待传文件 ${file.name}`);
      remove.addEventListener('click',()=>{queue=queue.filter(item=>item!==file);feedback('');drawQueue();enableUpload();onQueueChange();});
      chip.append(remove);host.append(chip);
    }
    byId('clear-material-queue').hidden=!queue.length;
  }
  function enableUpload(){
    const held=busy()||uploading;
    const upload=byId('upload-material');
    upload.disabled=held || !queue.length;
    upload.textContent=queue.length>1?`保存 ${queue.length} 个文件在本机`:'保存在本机';
    byId('material-file').disabled=held;byId('clear-material-queue').disabled=held;
    for(const chip of byId('material-queue').children)
      for(const child of chip.children)if(child.tagName==='button')child.disabled=held;
  }
  function enqueue(files,source){
    if(uploading||readonly||controller.state.loading||controller.state.materialAction||
        ['conflict','revoked'].includes(controller.state.status)){
      feedback('当前操作尚未完成或不能接收附件，请处理后重新选择文件。');return;
    }
    const incoming=[...files||[]];if(!incoming.length)return;
    const rejected=incoming.filter(file=>!accepted(file));
    const kept=incoming.filter(file=>accepted(file)&&!queue.some(item=>item.name===file.name&&item.size===file.size));
    queue.push(...kept);
    if(rejected.length)feedback(`不支持 ${rejected.map(file=>file.name).join('、')}；可添加办公文档、PDF、文本、网页、表格或图片。`);
    else if(kept.length)feedback(source==='drop'?'已加入待传列表，按回车或发送即可保存。':'');
    if(kept.length&&!rejected.length)picker(false);
    drawQueue();enableUpload();onQueueChange();
  }
  function failure(error){if(!controller.revoke(error))feedback(errorText(error));}
  async function write(operation){
    try {
      return await operation();
    } catch(error){failure(error);return false;}
  }
  async function parse(attachment,baseline=null){
    const cid=controller.state.id,token=previewEpoch;
    if(await write(()=>controller.parse(attachment.id,baseline)) && cid===controller.state.id && token===previewEpoch)
      await preview(attachment);
  }
  async function preview(attachment){
    onPreview();
    const cid=controller.state.id,token=++previewEpoch;
    const current=()=>token===previewEpoch && cid===controller.state.id && controller.state.status!=='revoked';
    const host=byId('material-preview-content');
    byId('material-preview-title').textContent=attachment.original_name;
    byId('material-preview').hidden=false;root.body.classList.add('source-open');
    byId('close-material-preview').focus();host.replaceChildren(node('p','正在读取原文…'));
    try {
      const selected=controller.state.materials?.items.find(item=>item.attachment_id===attachment.id);
      const revision=selected?.parse_revision;
      const parsed=revision?await api.getParse(cid,attachment.id,revision):null;
      if(!current())return;
      const kind=kindOf(attachment);
      const readableKind=kind!=='file';
      host.replaceChildren();
      host.append(node('p',`${KIND_LABEL[kind]} · ${(attachment.byte_size/1024).toFixed(1)} KiB · 原件已保存 · 待核实`));
      const download=node('a','下载受保护原件');download.href=api.originalUrl(cid,attachment.id);download.download='';host.append(download);
      if(!readableKind)host.append(node('p','该格式暂不支持读取原文，原件仅在本机保存，可下载核对。'));
      if(!parsed && readableKind)host.append(node('p','此版本尚未读取，读取只在本机进行。'));
      else if(parsed){
        const labels={readable:'已读取，内容仍待核实',partial:'部分可读，有未读项待核对',needs_baseline:'含修订，需要选择读取方式',failed:'读取失败，原件保留，可重新读取'};
        const status=kind==='pdf'&&parsed.reading_status==='needs_baseline'?'读取状态异常，请重新读取':labels[parsed.reading_status];
        host.append(node('p',`读取版本 ${revision} · ${status}`));
        if(kind==='pdf'&&parsed.reading_status!=='readable')host.append(node('p',
          '已读取可识别的内容，请对照原件核对未读项及识别结果。'));
      }
      if(!readonly && selected && readableKind){
        if(kind==='docx'&&parsed?.reading_status==='needs_baseline'){
          const label=node('label','选择保留原稿还是采用修订');
          const select=root.createElement('select');select.setAttribute('aria-label','修订读取方式');
          for(const [value,title] of [['','请选择'],['original','原始内容'],['accepted_view','接受修订后的内容'],['rejected_view','拒绝修订后的内容']]){
            const option=node('option',title);option.value=value;select.append(option);
          }
          label.append(select);host.append(label);
          const button=action('按所选方式读取',()=>parse(attachment,select.value));button.disabled=true;
          select.addEventListener('change',()=>{button.disabled=!select.value;});host.append(button);
        } else host.append(action(parsed?'重新读取，保留历史版本':`读取 ${kind.toUpperCase()}`,()=>parse(attachment)));
      }
      if(parsed?.result){
        const issues=[...parsed.result.quality_issues,...parsed.result.unsupported_parts];
        if(issues.length){const section=node('section','');section.append(node('h3',`待核对的读取范围（${issues.length} 项）`));
          const details=root.createElement('details');details.append(node('summary','查看读取说明'));
          details.append(node('pre',issues.map(readingNote).join('\n')));section.append(details);host.append(section);}
        let rendered=0;const section=node('section','');section.append(node('h3','已读取的原文'));
        const more=action('显示更多原文',()=>{append();});
        function append(){
          const batch=parsed.result.anchors.slice(rendered,rendered+100);
          for(const anchor of batch){const paragraph=node('section','');
            const location=node('p',`${anchor.part_name} · ${anchor.page?`第 ${anchor.page} 页 · `:''}${anchor.element_id}`);location.className='source-location';
            paragraph.append(location,node('p',anchor.quote));section.insertBefore(paragraph,more);}
          rendered+=batch.length;more.hidden=rendered>=parsed.result.anchors.length;
        }
        section.append(more);append();host.append(section);
      }
    }catch(error){if(current()){if(!controller.revoke(error))host.replaceChildren(node('p',errorText(error)));}}
  }
  function clearQueue(){queue=[];inflight=null;byId('material-file').value='';
    feedback('');drawQueue();enableUpload();}
  byId('add-material').addEventListener('click',()=>{
    const file=byId('material-file');
    if(typeof file.click==='function'){pickerEpoch=selectionEpoch;file.click();}
    else {picker(byId('material-picker').hidden);file.focus();}
  });
  byId('close-material-picker').addEventListener('click',()=>{picker(false);byId('add-material').focus();});
  byId('close-material-preview').addEventListener('click',()=>{closePreview();byId('add-material').focus();});
  byId('clear-material-queue').addEventListener('click',()=>{if(uploading||busy())return;clearQueue();onQueueChange();});
  byId('material-file').addEventListener('click',()=>{pickerEpoch=selectionEpoch;});
  byId('material-file').addEventListener('change',event=>{
    const origin=pickerEpoch;pickerEpoch=null;
    if(origin!==null&&origin!==selectionEpoch){
      event.target.value='';feedback('对话或访问状态已变化，请在当前对话重新选择文件。');return;
    }
    enqueue(event.target.files);event.target.value='';if(queue.length)byId('composer')?.focus();
  });
  async function uploadSelected(){
    if(uploading)return false;
    if(!queue.length)return true;
    if(readonly||controller.state.loading||controller.state.conflict||controller.state.materialAction||controller.state.status==='revoked')return false;
    uploading=true;enableUpload();
    const mode=root.body.dataset.localMaterials==='true'?'local':'synthetic';
    const policy={policy_id:'assistant-local-files-v2',material_mode:mode,
      local_processing_accepted:true,external_processing:false};
    const batch=[...queue];let saved=0;
    try{
      if(controller.state.status==='saving'&&!await controller.save())return false;
      if(busy())return false;
      if(!controller.state.id&&!await controller.ensureConversation())return false;
      const owner=controller.state.id;
      for(const file of batch){
        if(controller.state.id!==owner)break;
        feedback(batch.length>1?`正在保存 ${saved+1}/${batch.length}：${file.name}`:'正在保存原件…');
        inflight=file;
        const done=await write(()=>controller.upload(canonicalFile(file),policy));
        if(controller.state.id!==owner)return false;
        if(done){inflight=null;saved++;queue=queue.filter(item=>item!==file);drawQueue();}
        else break;
      }
      if(saved===batch.length){
        clearQueue();picker(false);
        feedback(batch.length>1?`${batch.length} 个原件已保存到本次对话，点击材料可核对。`:'原件已保存到本次对话，点击材料可读取和核对。');
      }else{
        feedback(`已保存 ${saved}/${batch.length} 个文件；剩余待传文件保留在列表中，请查看提示后重试。`);
        enableUpload();
      }
      return saved===batch.length;
    }finally{uploading=false;enableUpload();onQueueChange();}
  }
  byId('upload-material').addEventListener('click',uploadSelected);
  if(!readonly){
    let depth=0;
    const overlay=byId('drop-overlay');
    const containsFiles=event=>[...event.dataTransfer?.types||[]].includes('Files');
    root.addEventListener('dragover',event=>{
      if(!containsFiles(event)||busy())return;
      event.preventDefault();overlay.hidden=false;
    });
    root.addEventListener('dragenter',event=>{if(containsFiles(event))depth++;});
    root.addEventListener('dragleave',event=>{if(containsFiles(event)&&--depth<=0){depth=0;overlay.hidden=true;}});
    root.addEventListener('drop',event=>{
      if(!containsFiles(event))return;
      event.preventDefault();depth=0;overlay.hidden=true;
      if(busy())return;
      enqueue(event.dataTransfer?.files,'drop');if(queue.length)byId('composer')?.focus();
    });
  }
  return {
    state(state){
      // A draft's own autosave/create keeps its picker; navigation and revocation invalidate it.
      if(state.loading||state.status==='revoked'||identity&&state.id!==identity)selectionEpoch++;
      if(previousAction && !state.materialAction && state.status!=='error'){
        // A reconciled unknown upload retires its queued file as well.
        if(inflight)queue=queue.filter(item=>item!==inflight),inflight=null,drawQueue();
        if(!queue.length){byId('material-file').value='';picker(false);}
      }
      previousAction=state.materialAction;
      if(state.id!==identity || state.status==='revoked'){
        closePreview();const prior=identity;identity=state.id;revision=undefined;
        if(prior && state.id!==prior)clearQueue(),picker(false);
        if(state.status==='revoked' || !state.id&&!uploading&&!state.materialAction)clearQueue(),picker(false);
      }
      enableUpload();
      root.querySelectorAll('[data-material-write]').forEach(button=>{
        button.disabled=readonly || state.loading || ['saving','conflict','revoked','error'].includes(state.status);
      });
      const data=state.materials;
      if(data===revision)return;revision=data;
      const host=byId('material-list');host.replaceChildren();byId('material-section').hidden=!data?.attachments.length;
      for(const attachment of data?.attachments||[]){
        const selected=data.items.find(item=>item.attachment_id===attachment.id);
        const row=node('div','');row.className='material-row';
        const info=node('div','');info.className='material-info';info.append(node('strong',attachment.original_name),
          node('p',`${KIND_LABEL[kindOf(attachment)]} · `+(selected?(selected.parse_revision?`读取版本 ${selected.parse_revision} · 待核实`:'原件已保存 · 尚未读取'):'已移出本次材料 · 原件仍保留')));
        const buttons=node('div','');buttons.className='material-actions';
        buttons.append(action(kindOf(attachment)!=='file'?'核对原文':'查看信息',()=>preview(attachment)));
        if(!readonly){
          const button=action(selected?'移出本次':'加入本次',()=>write(()=>{
            const current=controller.state.materials.items;
            return controller.selectMaterials(selected?current.filter(item=>item.attachment_id!==attachment.id)
              :[...current.filter(item=>item.attachment_id!==attachment.id),{attachment_id:attachment.id,parse_revision:null}]);
          }));
          button.dataset.materialWrite='true';button.disabled=state.loading || ['saving','conflict','revoked','error'].includes(state.status);
          buttons.append(button);
        }
        row.append(info,buttons);host.append(row);
      }
    },
    uploadSelected,close:closePreview,hasSelection:()=>Boolean(queue.length),
    dispose(){closePreview();queue=[];releasePreviews();},
  };
}
