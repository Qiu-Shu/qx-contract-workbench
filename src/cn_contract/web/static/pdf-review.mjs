// Local PDF.js renders immutable bytes. No PDF scripting or interactive link layer.
const panel = document.getElementById('pdf-panel');
const status = document.getElementById('pdf-status');
const canvas = document.getElementById('pdf-canvas');
let pdfjs, pdf, loading, renderTask, selected, number = 1, rotation = 0, scale = 1, box = null, generation = 0, rendition = 0;
const maxPixels = 16000000, maxSide = 8192;
let ocrLocation=null;
let pageGeometry=[];
export function nativeAnchorCanHighlight(box,view,turn,geometry) {
  return !!geometry && turn===0 && view[0]===0 && view[1]===0 &&
    geometry.media?.length===4 && geometry.crop?.length===4 &&
    view.every((v,i)=>Number.isFinite(v) && v===geometry.media[i] && v===geometry.crop[i]) &&
    box.length===4 && box.every(Number.isFinite) && box[0]>=0 && box[1]>=0 &&
    box[2]<=view[2] && box[3]<=view[3] && box[2]>box[0] && box[3]>box[1];
}
export function preservedOCRSelection(id,previousLocation,newLocation,records) {
  return previousLocation===newLocation && records.some(c=>c.result.id===id)?id:'';
}
export function ocrReference(records,id) {
  const candidate=records.find(c=>c.result.id===id);
  return {candidate_id:candidate?.result.id||null,candidate_sha256:candidate?.sha256||null};
}
export function ocrViewportPolygon(points,source,width,height,turn,zoom) {
  if(Math.abs(source.page_width_points-width)>.01 || Math.abs(source.page_height_points-height)>.01 ||
     ![0,90,180,270].includes(turn) || !Number.isFinite(zoom) || zoom<=0 || !Array.isArray(points) || points.length!==4) return null;
  if(!points.every(p=>p.length===2 && p.every(Number.isFinite) && p[0]>=0 && p[1]>=0 && p[0]<=source.bitmap_width && p[1]<=source.bitmap_height)) return null;
  return points.map(([px,py])=>{
    const x=px/source.bitmap_width*width,y=py/source.bitmap_height*height;
    const point=turn===90?[height-y,x]:turn===180?[width-x,height-y]:turn===270?[y,width-x]:[x,y];
    return point.map(v=>v*zoom);
  });
}
function say(text) { if (status) status.textContent = text; }
function controls(disabled) { panel?.querySelectorAll('button,select').forEach(item => { item.disabled = disabled; }); }

async function render() {
  if (!pdf) return;
  if (document.getElementById('page-proofreading')) document.getElementById('page-proofreading').hidden = true;
  const current = generation, rendering = ++rendition;
  controls(true);
  try {
    if (renderTask) { renderTask.cancel(); try { await renderTask.promise; } catch {} }
    const page = await pdf.getPage(number);
    if (current !== generation || rendering !== rendition) return;
    const viewport = page.getViewport({ scale, rotation: (page.rotate + rotation) % 360 });
    const width = Math.ceil(viewport.width), height = Math.ceil(viewport.height);
    if (!Number.isFinite(width * height) || width <= 0 || height <= 0 || width > maxSide || height > maxSide || width * height > maxPixels) {
      canvas.width = canvas.height = 1;
      say('该缩放超过原页显示上限，请降低缩放或交由人工处理。');
      return;
    }
    canvas.width = width; canvas.height = height;
    const context = canvas.getContext('2d');
    renderTask = page.render({ canvasContext: context, viewport, annotationMode: pdfjs.AnnotationMode.ENABLE });
    await renderTask.promise;
    if (current !== generation || rendering !== rendition) return;
    let note = '';
    if(ocrLocation) {
      const base=page.getViewport({scale:1,rotation:page.rotate});
      const points=ocrViewportPolygon(ocrLocation.polygon,ocrLocation.source,base.width,base.height,rotation,scale);
      if(points){context.strokeStyle='#176b5b';context.lineWidth=3;context.beginPath();points.forEach(([x,y],i)=>i?context.lineTo(x,y):context.moveTo(x,y));context.closePath();context.stroke();}
      else note=' 识别位置与原页尺寸不符，请人工定位；未猜测标框。';
    }
    if (box) {
      // Existing PDF anchors use top-origin media-box coordinates. Native rotations
      // and nonzero crop boxes require explicit geometry evidence before highlighting.
      const [x0, y0, x1, y1] = box;
      if (nativeAnchorCanHighlight(box,page.view,page.rotate,pageGeometry[number-1])) {
        const rect = [...viewport.convertToViewportPoint(x0, page.view[3] - y1),
          ...viewport.convertToViewportPoint(x1, page.view[3] - y0)];
        context.strokeStyle = '#b44f00'; context.lineWidth = 3;
        context.strokeRect(Math.min(rect[0], rect[2]), Math.min(rect[1], rect[3]), Math.abs(rect[2] - rect[0]), Math.abs(rect[3] - rect[1]));
      } else note = ' 此页裁剪或原始旋转需人工定位，未猜测标框。';
    }
    document.getElementById('pdf-page-label').textContent = `第 ${number} / ${pdf.numPages} 页 · 旋转 ${rotation}°`;
    say('原件静态预览；文字与图像仍需逐项核对。' + note);
    await showProofreading();
  } catch (error) {
    if (current === generation && rendering === rendition && error?.name !== 'RenderingCancelledException') { canvas.width = canvas.height = 1; say('本页显示失败，不能据此确认原文，请保留人工核对。'); }
  } finally { if (current === generation && rendering === rendition) controls(false); }
}

export async function showPdf(version, page = 1, bbox = null) {
  if (!panel || version?.mime !== 'application/pdf') return;
  panel.hidden = false; controls(true); say('正在读取受保护原件…');
  const current = ++generation;
  canvas.width = canvas.height = 1;
  if (document.getElementById('page-proofreading')) document.getElementById('page-proofreading').hidden = true;
  try {
    if (renderTask) { renderTask.cancel(); try { await renderTask.promise; } catch {} }
    if (loading) await loading.destroy();
    pdf = null; loading = null;
    const matter = document.body.dataset.matter;
    const url = `/api/matters/${encodeURIComponent(matter)}/documents/${encodeURIComponent(version.id)}/original?sha256=${encodeURIComponent(version.sha256)}`;
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok || response.headers.get('X-Content-SHA256') !== version.sha256) throw new Error('version unavailable');
    const data = new Uint8Array(await response.arrayBuffer());
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(v => v.toString(16).padStart(2, '0')).join('');
    if (current !== generation) return;
    if (digest !== version.sha256) throw new Error('original digest mismatch');
    pageGeometry=JSON.parse(response.headers.get('X-QX-PDF-Geometry')||'[]');
    pdfjs ||= await import('/static/pdfjs/build/pdf.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = '/static/pdfjs/build/pdf.worker.mjs';
    loading = pdfjs.getDocument({ data, cMapUrl:'/static/pdfjs/cmaps/', cMapPacked:true,
      standardFontDataUrl:'/static/pdfjs/standard_fonts/', wasmUrl:'/static/pdfjs/wasm/', iccUrl:'/static/pdfjs/iccs/',
      isEvalSupported:false, enableXfa:false, useSystemFonts:false, useWasm:false, stopAtErrors:true,
      disableAutoFetch:true, disableStream:true, disableRange:true, canvasMaxAreaInBytes:64000000 });
    const loaded = await loading.promise;
    if (current !== generation) { await loaded.destroy(); return; }
    if (loaded.numPages > 200) { await loaded.destroy(); throw new Error('page cap'); }
    pdf = loaded; selected = version;
    ocrLocation=null;
    number = Number.isInteger(page) && page > 0 && page <= pdf.numPages ? page : 1;
    box = Array.isArray(bbox) && bbox.length === 4 ? bbox : null;
    document.getElementById('pdf-document-name').textContent = version.original_name;
    document.getElementById('pdf-document-hash').textContent = version.sha256;
    await render();
  } catch {
    if (current === generation) { pdf = null; canvas.width = canvas.height = 1; say('原件或本地预览组件不可用。请核对权限、文件版本和组件状态，不能据此确认原文。'); }
  } finally { if (current === generation) controls(false); }
}

let proofVersion = null, proofRecords = [], proofLocation = '', ocrRecords=[];
const sourceNames = {visible_original:'可见原文核对',lawyer_transcription:'律师转录',provider_clarification:'提供者澄清'};
async function proofApi(suffix, body) {
  const headers = body ? {'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID(),
    'X-CSRF-Token':decodeURIComponent((document.cookie.split('; ').find(x=>x.startsWith('qx_csrf='))||'').slice(8))} : {};
  const response = await fetch('/api/matters/'+encodeURIComponent(document.body.dataset.matter)+suffix,
    {method:body?'POST':'GET',headers,body:body?JSON.stringify(body):undefined,credentials:'same-origin',cache:'no-store'});
  const data=await response.json();
  if (!response.ok) throw new Error(data.code==='SOURCE_VERIFICATION_UPDATE_REQUIRED' ? '请先更新来源记录，再确认新值。' : '来源记录保存或读取受阻，请刷新核对权限、原件和事实版本。');
  return data;
}
async function showProofreading() {
  const host=document.getElementById('page-proofreading');
  if (!host || !selected) return;
  const current=generation, currentPage=number;
  try {
    const [facts,records,candidates]=await Promise.all([proofApi('/facts'),proofApi('/page-verifications'),proofApi('/page-ocr')]);
    if(current!==generation || currentPage!==number) return;
    const previousLocation=proofLocation, previousOCR=document.getElementById('proof-ocr-candidate').value;
    if (proofLocation !== selected.id+':'+number) {
      document.getElementById('page-verification-form').reset();
      document.getElementById('proofreading-status').textContent='';
      proofLocation=selected.id+':'+number;
    }
    proofVersion=facts.version; proofRecords=records; host.hidden=false;
    ocrRecords=candidates.filter(c=>c.result.source.document_version_id===selected.id && c.result.source.page===number);
    const options=document.getElementById('proof-ocr-candidate'),candidateHost=document.getElementById('ocr-page-candidates');
    options.replaceChildren();candidateHost.replaceChildren();
    const none=document.createElement('option');none.value='';none.textContent='未采用OCR，独立人工核对';options.append(none);
    for (const [index,candidate] of ocrRecords.entries()) {
      const option=document.createElement('option');option.value=candidate.result.id;option.textContent='第 '+(index+1)+' 次识别 · '+candidate.result.created_at;options.append(option);
      const card=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('pre');
      summary.textContent='未核OCR候选 '+(index+1)+'（置信度不代表律师确认）';
      text.textContent=candidate.result.blocks.map(b=>(b.raw_text||'【该区域未识别出文字】')+'\n引擎置信度：'+b.confidence+'；像素位置：'+JSON.stringify(b.polygon)).join('\n\n');
      card.append(summary,text);
      for(const [blockIndex,block] of candidate.result.blocks.entries()) {
        const locate=document.createElement('button');locate.type='button';locate.textContent='原页定位候选 '+(blockIndex+1)+'：'+(block.raw_text||'未识别出文字');
        locate.onclick=async()=>{ocrLocation={source:candidate.result.source,polygon:block.polygon};box=null;await render();canvas.scrollIntoView({block:'center'});};card.append(locate);
      }
      candidateHost.append(card);
    }
    options.value=preservedOCRSelection(previousOCR,previousLocation,proofLocation,ocrRecords);
    document.getElementById('proofreading-page').textContent=selected.original_name+' · 第 '+number+' 页 · 事实版本 '+proofVersion;
    const history=document.getElementById('page-verification-history');history.replaceChildren();
    for(const record of records.filter(r=>r.input.document_version_id===selected.id && r.input.page===number)) {
      const card=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('pre');
      const superseded=records.some(r=>r.input.previous_id===record.id);
      summary.textContent=sourceNames[record.input.source_kind]+' · '+(superseded?'历史版本':'当前来源')+' · '+record.created_at;
      text.textContent=JSON.stringify(record,null,2);card.append(summary,text);history.append(card);
    }
  } catch {host.hidden=true;}
}

const proofForm=document.getElementById('page-verification-form');
if(proofForm) proofForm.onsubmit=async event=>{
  event.preventDefault();const button=event.submitter;button.disabled=true;
  const status=document.getElementById('proofreading-status');
  try {
    if(!selected || !proofVersion) throw new Error('请先加载并核对原页。');
    const data=new FormData(proofForm),field=data.get('field');
    const previous=proofRecords.find(r=>r.input.document_version_id===selected.id && r.input.page===number && r.input.field===field
      && !proofRecords.some(other=>other.input.previous_id===r.id));
    const value={document_version_id:selected.id,document_sha256:selected.sha256,fact_version:proofVersion,page:number,
      source_kind:data.get('source_kind'),observed_text:data.get('observed_text'),field,
      typed_value:{kind:data.get('kind'),value:data.get('value')},unit:data.get('unit')||null,
      reason:data.get('reason'),original_page_checked:data.get('original_page_checked')==='on',
      previous_id:previous?.id||null,...ocrReference(ocrRecords,data.get('candidate_id'))};
    await proofApi('/page-verifications',value);
    proofForm.reset();status.textContent='来源已记录，事实仍待逐项确认。';
    await showProofreading();window.dispatchEvent(new CustomEvent('qx-proofreading-saved'));
  } catch(error) {status.textContent=error.message;} finally {button.disabled=false;}
};

const ocrButton=document.getElementById('run-page-ocr');
if(ocrButton) ocrButton.onclick=async()=>{
  if(!selected) return;ocrButton.disabled=true;
  const status=document.getElementById('ocr-page-status');status.textContent='正在本机识别这一页，原始候选不会自动确认为事实…';
  const version=selected, page=number;
  try {
    await proofApi('/page-ocr',{document_version_id:version.id,document_sha256:version.sha256,page});
    if(selected.id===version.id && number===page){await showProofreading();status.textContent='识别候选已保存。请逐项对照原页，再选择来源类别和核对值。';}
  } catch(error){status.textContent=error.message;} finally{ocrButton.disabled=false;}
};

if (panel) {
  window.addEventListener('qx-pdf-view', event => { void showPdf(event.detail.version, event.detail.page, event.detail.bbox); });
  document.getElementById('pdf-previous').onclick = async () => { if (pdf && number > 1) { number--; box = null; ocrLocation=null; await render(); } };
  document.getElementById('pdf-next').onclick = async () => { if (pdf && number < pdf.numPages) { number++; box = null; ocrLocation=null; await render(); } };
  document.getElementById('pdf-rotate').onclick = async () => { rotation = (rotation + 90) % 360; await render(); };
  document.getElementById('pdf-zoom').onchange = async event => { const value = Number(event.target.value); if ([0.25,0.5,0.75,1,1.5,2,3].includes(value)) { scale = value; await render(); } };
  document.getElementById('pdf-refresh').onclick = async () => { if (selected) await showPdf(selected, number, box); };
}
