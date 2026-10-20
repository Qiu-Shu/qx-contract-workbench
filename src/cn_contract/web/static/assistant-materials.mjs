// Local receipt controls. Writes use the draft controller's single channel.
import * as api from './assistant-api.mjs';
import {errorText} from './assistant-render.mjs';

export function bindMaterials({controller,readonly=false,root=document,onPreview=()=>{}}) {
  const byId=id=>root.getElementById(id);
  const node=(tag,text)=>{const item=root.createElement(tag);item.textContent=text;return item;};
  let identity=null,revision=null,previewEpoch=0,chosen=null,previousAction=null;
  const feedback=text=>{byId('material-notice').textContent=text;};
  const action=(title,run)=>{const button=node('button',title);button.type='button';button.className='text-button';
    button.addEventListener('click',()=>void run());return button;};
  function closePreview(){++previewEpoch;byId('material-preview').hidden=true;
    byId('material-preview-content').replaceChildren();root.body.classList.remove('source-open');}
  function picker(open){byId('material-picker').hidden=!open;byId('add-material').setAttribute('aria-expanded',String(open));}
  function enableUpload(){
    const busy=readonly || controller.state.loading || Boolean(controller.state.materialAction)
      || ['saving','conflict','revoked'].includes(controller.state.status);
    byId('upload-material').disabled=busy || !chosen || !byId('material-consent').checked;
    byId('material-file').disabled=byId('material-consent').disabled=busy;
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
      host.replaceChildren();
      host.append(node('p',`${(attachment.byte_size/1024).toFixed(1)} KiB · 原件已保存 · 待核实`));
      const download=node('a','下载受保护原件');download.href=api.originalUrl(cid,attachment.id);download.download='';host.append(download);
      if(!parsed)host.append(node('p','此版本尚未读取，读取只在本机进行。'));
      else {
        const labels={readable:'已读取，内容仍待核实',partial:'部分可读，有未读项待核对',needs_baseline:'含修订，需要选择读取方式',failed:'读取失败，原件保留，可重新读取'};
        host.append(node('p',`读取版本 ${revision} · ${labels[parsed.reading_status]}`));
      }
      if(!readonly && selected){
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
  byId('add-material').addEventListener('click',()=>{picker(byId('material-picker').hidden);byId('material-file').focus();});
  byId('close-material-picker').addEventListener('click',()=>{picker(false);byId('add-material').focus();});
  byId('close-material-preview').addEventListener('click',()=>{closePreview();byId('add-material').focus();});
  byId('material-file').addEventListener('change',event=>{chosen=event.target.files[0]||null;feedback('');enableUpload();});
  byId('material-consent').addEventListener('change',enableUpload);
  byId('upload-material').addEventListener('click',async()=>{
    const file=chosen;if(!file || !byId('material-consent').checked)return;
    const policy={policy_id:'assistant-local-docx-v1',material_mode:root.body.dataset.localMaterials==='true'?'local':'synthetic',
      local_processing_accepted:true,external_processing:false};
    feedback('正在保存原件…');
    if(await write(()=>controller.upload(file,policy))){
      chosen=null;byId('material-file').value='';byId('material-consent').checked=false;
      feedback('原件已保存到本次对话，点击材料可读取和核对。');enableUpload();picker(false);
    }else feedback('尚未确认保存。所选材料保留，请查看输入框下方的提示并核对结果。');
  });
  return {
    state(state){
      if(previousAction==='upload' && !state.materialAction && state.status!=='error'){
        chosen=null;byId('material-file').value='';byId('material-consent').checked=false;picker(false);
      }
      previousAction=state.materialAction;
      if(state.id!==identity || state.status==='revoked'){
        closePreview();identity=state.id;revision=undefined;
        if(state.status==='revoked' || !state.id){chosen=null;byId('material-file').value='';
          byId('material-consent').checked=false;feedback('');picker(false);}
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
          node('p',selected?(selected.parse_revision?`读取版本 ${selected.parse_revision} · 待核实`:'原件已保存 · 尚未读取'):'已移出本次材料 · 原件仍保留'));
        const buttons=node('div','');buttons.className='material-actions';
        buttons.append(action('核对原文',()=>preview(attachment)));
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
    close:closePreview,hasSelection:()=>Boolean(chosen),
    dispose(){closePreview();chosen=null;},
  };
}
