// Local receipt controls. Writes use the draft controller's single channel.
import * as api from './assistant-api.mjs';
import {errorText} from './assistant-render.mjs';

const DOCX_MIME='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const ACCEPTED={
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document':['.docx'],
  'application/msword':['.doc'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':['.xlsx'],
  'application/pdf':['.pdf'],
  'image/png':['.png'],
  'image/jpeg':['.jpg','.jpeg'],
  'text/csv':['.csv'],
};
const KIND_LABEL={docx:'Word',doc:'Word',xlsx:'表格',csv:'表格',pdf:'PDF',png:'图片',jpeg:'图片'};
function accepted(file) {
  const name=(file.name||'').toLowerCase();
  const mime=file.type||'';
  if(ACCEPTED[mime]?.some(extension=>name.endsWith(extension)))return true;
  // Dragged files occasionally arrive with an empty or generic type; the
  // extension decides here and the server re-checks the actual bytes anyway.
  if(!mime||mime==='application/octet-stream'||mime==='text/plain')
    return Object.values(ACCEPTED).flat().some(extension=>name.endsWith(extension));
  return false;
}
function kindOf(attachment) {
  const mime=attachment.mime||'';
  if(mime===DOCX_MIME)return 'docx';
  if(mime==='application/msword')return 'doc';
  if(mime==='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')return 'xlsx';
  if(mime==='application/pdf')return 'pdf';
  if(mime==='image/png')return 'png';
  if(mime==='image/jpeg')return 'jpeg';
  if(mime==='text/csv')return 'csv';
  return 'docx';
}

export function bindMaterials({controller,readonly=false,root=document,onPreview=()=>{}}) {
  const byId=id=>root.getElementById(id);
  const node=(tag,text)=>{const item=root.createElement(tag);item.textContent=text;return item;};
  let identity=null,revision=null,previewEpoch=0,queue=[],inflight=null,previousAction=null;
  const feedback=text=>{byId('material-notice').textContent=text;};
  const action=(title,run)=>{const button=node('button',title);button.type='button';button.className='text-button';
    button.addEventListener('click',()=>void run());return button;};
  function closePreview(){++previewEpoch;byId('material-preview').hidden=true;
    byId('material-preview-content').replaceChildren();root.body.classList.remove('source-open');}
  function picker(open){byId('material-picker').hidden=!open;byId('add-material').setAttribute('aria-expanded',String(open));}
  function busy(){return readonly || controller.state.loading || Boolean(controller.state.materialAction)
    || ['saving','conflict','revoked'].includes(controller.state.status);}
  function drawQueue(){
    const host=byId('material-queue');host.replaceChildren();
    for(const file of queue){
      const chip=node('span','');chip.className='queue-chip';
      chip.append(node('span',`${file.name}（${(file.size/1024).toFixed(1)} KiB）`));
      const remove=node('button','×');remove.type='button';remove.className='queue-remove';
      remove.setAttribute('aria-label',`移除待传文件 ${file.name}`);
      remove.addEventListener('click',()=>{queue=queue.filter(item=>item!==file);feedback('');drawQueue();enableUpload();});
      chip.append(remove);host.append(chip);
    }
    byId('clear-material-queue').hidden=!queue.length;
  }
  function enableUpload(){
    const held=busy();
    const upload=byId('upload-material');
    upload.disabled=held || !queue.length || !byId('material-consent').checked;
    upload.textContent=queue.length>1?`保存 ${queue.length} 个文件在本机`:'保存在本机';
    byId('material-file').disabled=byId('material-consent').disabled=held;
    for(const chip of byId('material-queue').children)
      for(const child of chip.children)if(child.tagName==='button')child.disabled=held;
  }
  function enqueue(files,source){
    const incoming=[...files||[]];if(!incoming.length)return;
    const rejected=incoming.filter(file=>!accepted(file));
    const kept=incoming.filter(file=>accepted(file)&&!queue.some(item=>item.name===file.name&&item.size===file.size));
    queue.push(...kept);
    if(rejected.length)feedback(`不支持 ${rejected.map(file=>file.name).join('、')}；可传 Word、PDF、表格或图片。`);
    else if(kept.length)feedback(source==='drop'?'已加入待传列表，确认后可保存。':'');
    drawQueue();enableUpload();
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
      host.replaceChildren();
      host.append(node('p',`${KIND_LABEL[kind]} · ${(attachment.byte_size/1024).toFixed(1)} KiB · 原件已保存 · 待核实`));
      const download=node('a','下载受保护原件');download.href=api.originalUrl(cid,attachment.id);download.download='';host.append(download);
      if(kind!=='docx')host.append(node('p','该格式暂不支持读取原文，原件仅在本机保存，可下载核对。'));
      if(!parsed && kind==='docx')host.append(node('p','此版本尚未读取，读取只在本机进行。'));
      else if(parsed){
        const labels={readable:'已读取，内容仍待核实',partial:'部分可读，有未读项待核对',needs_baseline:'含修订，需要选择读取方式',failed:'读取失败，原件保留，可重新读取'};
        host.append(node('p',`读取版本 ${revision} · ${labels[parsed.reading_status]}`));
      }
      if(!readonly && selected && kind==='docx'){
        if(parsed?.reading_status==='needs_baseline'){
          const label=node('label','选择保留原稿还是采用修订');
          const select=root.createElement('select');select.setAttribute('aria-label','修订读取方式');
          for(const [value,title] of [['','请选择'],['original','原始内容'],['accepted_view','接受修订后的内容'],['rejected_view','拒绝修订后的内容']]){
            const option=node('option',title);option.value=value;select.append(option);
          }
          label.append(select);host.append(label);
          const button=action('按所选方式读取',()=>parse(attachment,select.value));button.disabled=true;
          select.addEventListener('change',()=>{button.disabled=!select.value;});host.append(button);
        } else host.append(action(parsed?'重新读取，保留历史版本':'读取 DOCX',()=>parse(attachment)));
      }
      if(parsed?.result){
        const issues=[...parsed.result.quality_issues,...parsed.result.unsupported_parts];
        if(issues.length){const section=node('section','');section.append(node('h3',`待核对的读取范围（${issues.length} 项）`));
          const details=root.createElement('details');details.append(node('summary','展开未读项'));
          details.append(node('pre',issues.join('\n')));section.append(details);host.append(section);}
        let rendered=0;const section=node('section','');section.append(node('h3','已读取的原文'));
        const more=action('显示更多原文',()=>{append();});
        function append(){
          const batch=parsed.result.anchors.slice(rendered,rendered+100);
          for(const anchor of batch){const paragraph=node('section','');
            const location=node('p',`${anchor.part_name} · ${anchor.element_id}`);location.className='source-location';
            paragraph.append(location,node('p',anchor.quote));section.insertBefore(paragraph,more);}
          rendered+=batch.length;more.hidden=rendered>=parsed.result.anchors.length;
        }
        section.append(more);append();host.append(section);
      }
    }catch(error){if(current()){if(!controller.revoke(error))host.replaceChildren(node('p',errorText(error)));}}
  }
  function clearQueue(){queue=[];inflight=null;byId('material-file').value='';byId('material-consent').checked=false;
    feedback('');drawQueue();enableUpload();}
  byId('add-material').addEventListener('click',()=>{picker(byId('material-picker').hidden);byId('material-file').focus();});
  byId('close-material-picker').addEventListener('click',()=>{picker(false);byId('add-material').focus();});
  byId('close-material-preview').addEventListener('click',()=>{closePreview();byId('add-material').focus();});
  byId('clear-material-queue').addEventListener('click',clearQueue);
  byId('material-file').addEventListener('change',event=>{enqueue(event.target.files);event.target.value='';});
  byId('material-consent').addEventListener('change',enableUpload);
  byId('upload-material').addEventListener('click',async()=>{
    if(!queue.length || !byId('material-consent').checked)return;
    const policy={policy_id:'assistant-local-files-v2',material_mode:root.body.dataset.localMaterials==='true'?'local':'synthetic',
      local_processing_accepted:true,external_processing:false};
    const batch=[...queue];let saved=0;
    for(const file of batch){
      feedback(batch.length>1?`正在保存 ${saved+1}/${batch.length}：${file.name}`:'正在保存原件…');
      inflight=file;
      const done=await write(()=>controller.upload(file,policy));
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
  });
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
      enqueue(event.dataTransfer?.files,'drop');picker(true);
    });
  }
  return {
    state(state){
      if(previousAction==='upload' && !state.materialAction && state.status!=='error'){
        // A reconciled unknown upload retires its queued file as well.
        if(inflight)queue=queue.filter(item=>item!==inflight),inflight=null,drawQueue();
        if(!queue.length){byId('material-file').value='';byId('material-consent').checked=false;picker(false);}
      }
      previousAction=state.materialAction;
      if(state.id!==identity || state.status==='revoked'){
        closePreview();identity=state.id;revision=undefined;
        if(state.status==='revoked' || !state.id)clearQueue(),picker(false);
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
        buttons.append(action(kindOf(attachment)==='docx'?'核对原文':'查看信息',()=>preview(attachment)));
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
    close:closePreview,hasSelection:()=>Boolean(queue.length),
    dispose(){closePreview();queue=[];},
  };
}
