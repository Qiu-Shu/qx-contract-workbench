import assert from 'node:assert/strict';
import test from 'node:test';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';
import {bindComposer} from '../src/cn_contract/web/static/assistant-composer.mjs';
import {bindMaterials} from '../src/cn_contract/web/static/assistant-materials.mjs';

const copy=value=>structuredClone(value);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document';

// Only the DOM operations used by the material controls; no browser/layout claims.
class Element {
  constructor(tag='div') {
    this.tagName=tag;this.children=[];this.listeners=new Map();this.dataset={};
    this.textContent='';this.hidden=false;this.disabled=false;this.checked=false;this.value='';
    const classes=new Set();
    this.classList={add:value=>classes.add(value),remove:value=>classes.delete(value),contains:value=>classes.has(value)};
  }
  addEventListener(name,listener){this.listeners.set(name,listener);}
  removeEventListener(name){this.listeners.delete(name);}
  setAttribute(name,value){this[name]=String(value);}
  focus(){this.focused=true;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  insertBefore(child,before){this.children.splice(this.children.indexOf(before),0,child);}
  fire(name,event={}){return this.listeners.get(name)?.(event);}
}
function dom() {
  const elements=new Map(),rootListeners=new Map();
  const root={
    body:new Element('body'),
    getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},
    createElement:tag=>new Element(tag),
    addEventListener(name,listener){rootListeners.set(name,listener);},
    fire(name,event={}){return rootListeners.get(name)?.(event);},
    querySelectorAll(selector){
      assert.equal(selector,'[data-material-write]');
      return [...elements.values()].flatMap(walk).filter(element=>element.dataset.materialWrite);
    },
  };
  root.body.dataset.localMaterials='true';return root;
}
function walk(element){return [element,...element.children.flatMap(walk)];}
function button(root,id,label) {
  const found=walk(root.getElementById(id)).find(element=>element.tagName==='button' && element.textContent===label);
  assert.ok(found,`missing button: ${label}`);return found;
}
function fixture(t,{withMaterials=true}={}) {
  const root=dom(),calls=[],receipts=new Map();let sequence=0;
  const view=id=>({scope:{workspace_id:'workspace',conversation_id:id,scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:id==='one'&&withMaterials?1:0},
    composer_revision:0,draft_input:'',messages:[]});
  const views={one:view('one'),two:view('two')};
  const file=id=>({id,conversation_id:'one',original_name:`合成材料-${id}.docx`,mime,byte_size:123});
  const records={one:{items:withMaterials?[{attachment_id:'A',parse_revision:1},{attachment_id:'B',parse_revision:1}]:[],
    attachments:withMaterials?[file('A'),file('B')]:[]},two:{items:[],attachments:[]}};
  const api={
    async getConversation(id){return copy(views[id]);},
    async getMaterials(id){return copy({scope:views[id].scope,...records[id]});},
    async saveDraft(id,body){views[id]={...views[id],draft_input:body.content,composer_revision:views[id].composer_revision+1};return copy(views[id]);},
    async parseAttachment(id,attachment,body){
      calls.push(['parse',id,attachment,body.request_id,body.baseline_view]);
      records[id].items=records[id].items.map(item=>item.attachment_id===attachment?{...item,parse_revision:item.parse_revision+1}:item);
      views[id].scope.materials_revision++;return {materials_revision:views[id].scope.materials_revision};
    },
    async uploadAttachment(id,body,source){
      calls.push(['upload',id,body.request_id]);const attachment={...file(`upload-${calls.length}`),original_name:source.name,mime:source.type};
      records[id].items.push({attachment_id:attachment.id,parse_revision:null});records[id].attachments.push(attachment);
      views[id].scope.materials_revision++;const result={attachment,materials_revision:views[id].scope.materials_revision};
      receipts.set(body.request_id,result);return copy(result);
    },
    async findAttachmentRequest(id,key){calls.push(['lookup',id,key]);return copy(receipts.get(key)||null);},
  };
  const oldFetch=globalThis.fetch;
  globalThis.fetch=async path=>{calls.push(['preview',path]);return {ok:true,json:async()=>({reading_status:'readable',result:null})};};
  let materials;
  const controller=createDraftController(api,{uuid:()=>`synthetic-${++sequence}`,onChange:state=>materials?.state(state)});
  materials=bindMaterials({controller,root});
  t.after(()=>{materials.dispose();controller.close();globalThis.fetch=oldFetch;});
  return {root,api,controller,materials,calls,views,records};
}
async function preview(f,index=0) {
  const row=f.root.getElementById('material-list').children[index];
  assert.ok(row);walk(row).find(element=>element.tagName==='button').fire('click');await tick();
}
async function beginParse(f) {
  const gate=deferred(),normal=f.api.parseAttachment;
  f.api.parseAttachment=async(...args)=>{await gate.promise;return normal(...args);};
  button(f.root,'material-preview-content','重新读取，保留历史版本').fire('click');await tick();
  assert.equal(f.controller.state.materialAction,'parse');return gate;
}

test('late parse completion cannot reopen a preview explicitly closed by the lawyer',async t=>{
  const f=fixture(t);await f.controller.open('one');await preview(f);
  const gate=await beginParse(f);
  f.root.getElementById('close-material-preview').fire('click');
  assert.equal(f.root.getElementById('material-preview').hidden,true);
  gate.resolve();await tick();await tick();
  assert.equal(f.controller.state.status,'saved');
  assert.equal(f.root.getElementById('material-preview').hidden,true);
  assert.equal(f.root.getElementById('material-preview-content').children.length,0);
});

test('late parse completion cannot replace a newer attachment preview',async t=>{
  const f=fixture(t);await f.controller.open('one');await preview(f);
  const gate=await beginParse(f);await preview(f,1);
  assert.equal(f.root.getElementById('material-preview-title').textContent,'合成材料-B.docx');
  gate.resolve();await tick();await tick();
  assert.equal(f.controller.state.status,'saved');
  assert.equal(f.root.getElementById('material-preview-title').textContent,'合成材料-B.docx');
  assert.equal(f.root.getElementById('material-preview').hidden,false);
});

test('switching conversations suppresses the prior parse callback while the target is loading',async t=>{
  const f=fixture(t);await f.controller.open('one');await preview(f);
  const parseGate=await beginParse(f),readGate=deferred(),normal=f.api.getConversation;
  f.api.getConversation=async id=>{if(id==='two')await readGate.promise;return normal(id);};
  const opening=f.controller.open('two');parseGate.resolve();await tick();await tick();
  assert.equal(f.controller.state.loading,true);
  assert.equal(f.root.getElementById('material-preview').hidden,true);
  assert.equal(f.root.getElementById('material-list').children.length,0);
  readGate.resolve();assert.equal(await opening,true);await tick();
  assert.equal(f.controller.state.id,'two');
  assert.equal(f.root.getElementById('material-preview').hidden,true);
  assert.equal(f.root.getElementById('material-list').children.length,0);
});

test('new conversation clears prior material rows, preview and unsubmitted picker selection',async t=>{
  const f=fixture(t);await f.controller.open('one');await preview(f);
  await f.root.getElementById('material-file').fire('change',{target:{files:[{name:'未上传.docx',type:mime}]}});
  assert.equal(f.materials.hasSelection(),true);
  assert.equal(await f.controller.newConversation(),true);
  assert.equal(f.root.getElementById('material-list').children.length,0);
  assert.equal(f.root.getElementById('material-section').hidden,true);
  assert.equal(f.root.getElementById('material-preview').hidden,true);
  assert.equal(f.materials.hasSelection(),false);
});

test('revocation clears materials immediately and a delayed source response stays discarded',async t=>{
  const f=fixture(t);await f.controller.open('one');const readGate=deferred();
  globalThis.fetch=async()=>{await readGate.promise;return {ok:true,json:async()=>({reading_status:'readable',result:null})};};
  await preview(f);
  f.controller.revoke({status:403,code:'CROSS_MATTER_DENIED'});
  assert.equal(f.root.getElementById('material-list').children.length,0);
  assert.equal(f.root.getElementById('material-preview').hidden,true);
  readGate.resolve();await tick();await tick();
  assert.equal(f.controller.state.status,'revoked');
  assert.equal(f.root.getElementById('material-preview').hidden,true);
  assert.equal(f.root.getElementById('material-preview-content').children.length,0);
});

test('successful unknown-upload reconciliation disarms the picker instead of creating another receipt',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const normal=f.api.uploadAttachment;
  f.api.uploadAttachment=async(...args)=>{await normal(...args);throw Object.assign(Error('unknown'),{status:0,code:'NETWORK_UNKNOWN'});};
  await f.root.getElementById('material-file').fire('change',{target:{files:[{name:'待核对上传.docx',type:mime,size:2048}]}});
  await f.root.getElementById('upload-material').fire('click');
  assert.equal(f.controller.state.status,'error');assert.equal(f.materials.hasSelection(),true);
  assert.equal(await f.controller.retry(),true);
  assert.equal(f.materials.hasSelection(),false);
  assert.equal(f.root.getElementById('upload-material').disabled,true);
  await f.root.getElementById('upload-material').fire('click');
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
  assert.equal(f.calls.filter(call=>call[0]==='lookup').length,1);
});

const fileStub=(name,type,size=1024)=>({name,type,size});
function chipNames(f){return walk(f.root.getElementById('material-queue'))
  .filter(element=>element.className==='queue-chip').map(chip=>chip.children[0].textContent);}

test('multi-select builds a removable queue and uploads each file in order with its own receipt',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');
  await f.root.getElementById('material-file').fire('change',{target:{files:[
    fileStub('合同扫描.pdf','application/pdf'),fileStub('现场照片.png','image/png'),fileStub('清单.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]}});
  assert.deepEqual(chipNames(f).map(text=>text.split('（')[0]),['合同扫描.pdf','现场照片.png','清单.xlsx']);
  assert.equal(f.root.getElementById('upload-material').textContent,'保存 3 个文件在本机');
  const removeButtons=walk(f.root.getElementById('material-queue')).filter(element=>element.className==='queue-remove');
  assert.equal(removeButtons.length,3);
  await removeButtons[1].fire('click');
  assert.deepEqual(chipNames(f).map(text=>text.split('（')[0]),['合同扫描.pdf','清单.xlsx']);
  assert.equal(f.root.getElementById('upload-material').disabled,false,'selection is the explicit upload action');
  await f.root.getElementById('upload-material').fire('click');
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,2);
  assert.equal(f.materials.hasSelection(),false);
  assert.equal(f.root.getElementById('material-picker').hidden,true);
  assert.equal(f.root.getElementById('material-notice').textContent,'2 个原件已保存到本次对话，点击材料可核对。');
});

test('a failed batch keeps the remaining queue and reports the partial count',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');
  await f.root.getElementById('material-file').fire('change',{target:{files:[
    fileStub('一.docx',mime),fileStub('二.docx',mime),fileStub('三.docx',mime)]}});
  const normal=f.api.uploadAttachment;let attempts=0;
  f.api.uploadAttachment=async(...args)=>{attempts++;if(attempts===2)throw Object.assign(Error('conflict'),{status:409,code:'STATE_CONFLICT'});return normal(...args);};
  await f.root.getElementById('upload-material').fire('click');
  assert.equal(attempts,2,'stops at the first failure');
  assert.deepEqual(chipNames(f).map(text=>text.split('（')[0]),['二.docx','三.docx']);
  assert.equal(f.root.getElementById('material-notice').textContent.includes('已保存 1/3'),true);
});

test('dropping files on the page queues them and rejects unsupported types by name',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');
  let prevented=0;
  const event={dataTransfer:{types:['Files'],files:[fileStub('证据.pdf','application/pdf'),fileStub('旧版合同.doc','application/msword'),fileStub('程序.exe','application/x-msdownload')]},
    preventDefault(){prevented++;}};
  f.root.fire('dragover',event);
  assert.equal(f.root.getElementById('drop-overlay').hidden,false);
  f.root.fire('drop',event);
  assert.equal(prevented,2);
  assert.equal(f.root.getElementById('drop-overlay').hidden,true);
  assert.equal(f.root.getElementById('material-picker').hidden,false,'drop opens the picker');
  assert.deepEqual(chipNames(f).map(text=>text.split('（')[0]),['证据.pdf','旧版合同.doc']);
  assert.equal(f.root.getElementById('material-notice').textContent.includes('程序.exe'),true);
});

test('non-readable formats preview without a parse control',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('清单.csv','text/csv')]}});
  await f.root.getElementById('upload-material').fire('click');
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
  const row=f.root.getElementById('material-list').children[0];
  assert.ok(row);walk(row).find(element=>element.textContent==='查看信息').fire('click');await tick();
  const host=f.root.getElementById('material-preview-content');
  const labels=walk(host).map(element=>element.textContent);
  assert.equal(labels.some(text=>['读取 DOCX','读取 PDF','重新读取，保留历史版本','按所选方式读取'].includes(text)),false,'no parse action for CSV');
  assert.equal(labels.some(text=>String(text).includes('暂不支持读取原文')),true);
});

test('PDF preview offers local reading, protected originals and page anchored excerpts without a revision chooser',async t=>{
  const f=fixture(t,{withMaterials:false});
  f.records.one={attachments:[{id:'P',conversation_id:'one',original_name:'合成合同.pdf',mime:'application/pdf',byte_size:123}],
    items:[{attachment_id:'P',parse_revision:null}]};
  await f.controller.open('one');await preview(f);
  button(f.root,'material-preview-content','读取 PDF').fire('click');await tick();await tick();
  assert.equal(f.calls.find(call=>call[0]==='parse')[4],null,'PDF uses the original/default baseline, never a DOCX revision choice');
  const links=walk(f.root.getElementById('material-preview-content')).filter(el=>el.tagName==='a');
  assert.equal(links[0].href,'/api/assistant/conversations/one/attachments/P/original');
  f.records.one.items[0].parse_revision=1;
  globalThis.fetch=async()=>({ok:true,json:async()=>({reading_status:'partial',parser_version:'qx-pdf-attachments-v1',baseline_view:'original',result:{
    quality_issues:['OCR_NOT_DEPLOYED:page:2'],unsupported_parts:['page:2'],anchors:[
      {part_name:'page:1',element_id:'span:0',page:1,quote:'独立虚构价款：13750元',bbox:[1,2,3,4]}]}})});
  await f.controller.refresh();await preview(f);
  const content=walk(f.root.getElementById('material-preview-content'));
  assert.ok(content.some(el=>el.textContent==='独立虚构价款：13750元'));
  assert.ok(content.some(el=>String(el.textContent).includes('第 1 页')));
  assert.ok(content.some(el=>String(el.textContent).includes('人工核对')&&String(el.textContent).includes('不可冻结')));
  assert.equal(content.some(el=>el.tagName==='select'),false);
  assert.equal(content.some(el=>String(el.textContent).includes('暂不支持读取原文')),false);
  button(f.root,'material-preview-content','重新读取，保留历史版本');
});

test('PDF never shows DOCX revision choices even when a malformed read status asks for a baseline',async t=>{
  const f=fixture(t,{withMaterials:false});
  f.records.one={attachments:[{id:'P',conversation_id:'one',original_name:'合成合同.pdf',mime:'application/pdf',byte_size:123}],
    items:[{attachment_id:'P',parse_revision:1}]};
  globalThis.fetch=async()=>({ok:true,json:async()=>({reading_status:'needs_baseline',result:null})});
  await f.controller.open('one');await preview(f);
  const content=walk(f.root.getElementById('material-preview-content'));
  assert.equal(content.some(el=>el.tagName==='select'),false);
  button(f.root,'material-preview-content','重新读取，保留历史版本');
});

for(const local of [true,false])test('upload uses the server-provided local material policy '+local,async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');f.root.body.dataset.localMaterials=String(local);
  const policies=[],normal=f.api.uploadAttachment;
  f.api.uploadAttachment=async(id,body,file)=>{policies.push(body.policy);return normal(id,body,file);};
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('独立虚构.docx',mime)]}});
  await f.root.getElementById('upload-material').fire('click');
  assert.equal(policies.length,1);assert.equal(policies[0].material_mode,local?'local':'synthetic');
});

test('selected local files upload directly without consent controls',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');let policy;
  const normal=f.api.uploadAttachment;f.api.uploadAttachment=async(id,body,file)=>{policy=body.policy;return normal(id,body,file);};
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('独立虚构合同.docx',mime)]}});
  assert.equal(f.root.getElementById('upload-material').disabled,false);
  assert.equal(f.root.getElementById('composer').focused,true,'selection returns focus to Enter-to-send input');
  assert.equal(await f.materials.uploadSelected(),true);
  assert.equal(policy.material_mode,'local');assert.equal(policy.local_processing_accepted,true);
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
});

function composerFor(f){
  let sends=0;
  const input=f.root.getElementById('composer'),form=f.root.getElementById('composer-form');
  const binding=bindComposer({input,form,onEdit:text=>f.controller.edit(text),beforeSend:()=>f.materials.uploadSelected(),
    onSend:()=>{if(f.controller.state.text.trim()){sends++;assert.equal(f.materials.hasSelection(),false);}}});
  return {input,form,binding,sends:()=>sends,edit(text){input.value=text;input.fire('input');},key:(extra={})=>input.fire('keydown',{key:'Enter',preventDefault(){},...extra})};
}
test('fresh files-only Enter creates one chat and uploads a batch with no model dispatch',async t=>{
  const f=fixture(t,{withMaterials:false});let creates=0;
  f.api.createConversation=async()=>{creates++;return copy(f.views.one);};
  const c=composerFor(f);
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('一.docx',mime),fileStub('二.docx',mime)]}});
  assert.equal(await c.key(),true);assert.equal(creates,1);assert.equal(f.controller.state.id,'one');
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,2);assert.equal(c.sends(),0);c.binding.dispose();
});
test('Enter uploads before sending current text and serializes rapid Enter and button submit',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const c=composerFor(f),gate=deferred();
  const normal=f.api.uploadAttachment;f.api.uploadAttachment=async(...args)=>{await gate.promise;return normal(...args);};
  c.edit('独立虚构问题');await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  const first=c.key();await tick();c.key();c.form.fire('submit',{preventDefault(){}});assert.equal(c.sends(),0);
  gate.resolve();await first;
  assert.equal(c.sends(),1);assert.equal(f.controller.state.text,'独立虚构问题');
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);c.binding.dispose();
});
test('failed or unknown upload never sends text and reconciles one receipt before retry',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const c=composerFor(f),normal=f.api.uploadAttachment;
  c.edit('仍保留的问题');f.api.uploadAttachment=async(...args)=>{await normal(...args);throw Object.assign(Error('unknown'),{status:0,code:'NETWORK_UNKNOWN'});};
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  assert.equal(await c.key(),false);assert.equal(c.sends(),0);assert.equal(f.materials.hasSelection(),true);
  assert.equal(await c.key(),false);assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
  assert.equal(await f.controller.retry(),true);await c.key();assert.equal(c.sends(),1);
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);c.binding.dispose();
});
test('IME Enter Shift Enter and held Enter do not upload queued files',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const c=composerFor(f);
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  c.input.fire('compositionstart');c.key();c.input.fire('compositionend');
  c.key({shiftKey:true});c.key({repeat:true});c.key({isComposing:true});await tick();
  assert.equal(f.calls.length,0);assert.equal(f.materials.hasSelection(),true);c.binding.dispose();
});
test('queued files from an existing conversation never move to another chat',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  await f.controller.open('two');assert.equal(f.materials.hasSelection(),false);
  await f.materials.uploadSelected();assert.equal(f.calls.filter(call=>call[0]==='upload').length,0);
});

test('Enter waits for an existing autosave before uploading selected files',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const c=composerFor(f),gate=deferred();
  await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  const normal=f.api.saveDraft;f.api.saveDraft=async(...args)=>{await gate.promise;return normal(...args);};
  c.edit('虚构问题');const saving=f.controller.save();await tick();assert.equal(f.controller.state.status,'saving');
  const sent=c.key();await tick();assert.equal(c.sends(),0);assert.equal(f.calls.filter(call=>call[0]==='upload').length,0);
  gate.resolve();await saving;await sent;assert.equal(c.sends(),1);assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
  c.binding.dispose();
});

for(const initial of ['', '原始虚构问题'])test('upload preserves original send intent when edited: '+(initial?'text+file':'file only'),async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const c=composerFor(f),gate=deferred();
  const normal=f.api.uploadAttachment;f.api.uploadAttachment=async(...args)=>{await gate.promise;return normal(...args);};
  c.edit(initial);await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  const pending=c.key();await tick();c.edit('等待期间输入的下一段');gate.resolve();await pending;
  assert.equal(f.calls.filter(call=>call[0]==='upload').length,1);
  assert.equal(c.sends(),0,'typing during upload is not another send action');
  assert.equal(f.controller.state.text,'等待期间输入的下一段');assert.equal(c.input.disabled,false);
  await c.key();assert.equal(c.sends(),1,'a second explicit Enter sends the retained text');c.binding.dispose();
});
test('edit then undo while upload waits still requires a new explicit send',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const c=composerFor(f),gate=deferred();
  const normal=f.api.uploadAttachment;f.api.uploadAttachment=async(...args)=>{await gate.promise;return normal(...args);};
  c.edit('原始虚构问题');await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  const pending=c.key();await tick();c.edit('修改');c.edit('原始虚构问题');gate.resolve();await pending;
  assert.equal(c.sends(),0);assert.equal(f.controller.state.text,'原始虚构问题');await c.key();assert.equal(c.sends(),1);c.binding.dispose();
});
test('starting composition during upload cancels the text send without locking input',async t=>{
  const f=fixture(t,{withMaterials:false});await f.controller.open('one');const c=composerFor(f),gate=deferred();
  const normal=f.api.uploadAttachment;f.api.uploadAttachment=async(...args)=>{await gate.promise;return normal(...args);};
  c.edit('原始虚构问题');await f.root.getElementById('material-file').fire('change',{target:{files:[fileStub('合同.docx',mime)]}});
  const pending=c.key();await tick();c.input.fire('compositionstart');gate.resolve();await pending;
  assert.equal(c.sends(),0);assert.equal(c.input.disabled,false);c.input.fire('compositionend');c.binding.dispose();
});
