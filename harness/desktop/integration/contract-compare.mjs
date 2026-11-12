import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {open,realpath,lstat} from 'node:fs/promises';
import {resolve,relative,isAbsolute,sep,extname} from 'node:path';
import {createRequire} from 'node:module';
import {DatabaseSync} from 'node:sqlite';
const {diffArrays,diffChars}=createRequire(import.meta.url)('diff');
const MAX_TEXT=200000,MAX_PARAGRAPHS=4000;
const digest=value=>createHash('sha256').update(value).digest('hex');
export function comparisonError(message,status=400){return Object.assign(Error(message),{status});}
export async function confinedPath(root,input,{directory=false,internal=false}={}){
  if(typeof input!=='string'||input.length>4096||/[\x00-\x1f]/.test(input))throw comparisonError('文件位置无效');
  root=await realpath(root);const target=resolve(root,input),rel=relative(root,target);
  const upload=rel.split(sep).join('/').startsWith('inbox/.harness/attachments/v1/files/');
  if((!rel&&!directory)||rel==='..'||rel.startsWith('..'+sep)||isAbsolute(rel)||(!internal&&rel.split(sep).some(p=>p.startsWith('.')&&!(upload&&p==='.harness'))))throw comparisonError('只允许读取当前工作区的合同文件',403);
  let current=root;
  for(const part of rel.split(sep).filter(Boolean)){current=resolve(current,part);if((await lstat(current)).isSymbolicLink())throw comparisonError('不读取链接或目录联接',403);}
  const actual=await realpath(target),actualRel=relative(root,actual);
  if(actualRel==='..'||actualRel.startsWith('..'+sep)||isAbsolute(actualRel))throw comparisonError('文件不在当前工作区',403);
  const info=await lstat(actual);if(directory?!info.isDirectory():!info.isFile())throw comparisonError('请选择普通合同文件');
  return {root,path:actual,key:actualRel.split(sep).join('/'),info};
}
export async function indexedContractPaths(root){
  let db;
  try{const index=await confinedPath(root,'.qx-materials/index.sqlite',{internal:true});db=new DatabaseSync(index.path,{readOnly:true});const result=[];
    for(const row of db.prepare('SELECT path FROM materials ORDER BY path LIMIT 1000').all()){
      if(!/\.(txt|md|docx?|pdf|rtf|odt)$/i.test(row.path))continue;
      try{result.push((await confinedPath(root,row.path)).key);}catch{/* A stale or external index row is not a selectable original. */}
    }return result;
  }catch{return [];}finally{db?.close();}
}
async function fileHash(path){const hash=createHash('sha256');for await(const bytes of createReadStream(path))hash.update(bytes);return hash.digest('hex');}
async function boundedTextBytes(path){
  const handle=await open(path,'r'),buffer=Buffer.alloc(MAX_TEXT*4+1);let length=0;
  try{
    while(length<buffer.length){const {bytesRead}=await handle.read(buffer,length,buffer.length-length,null);if(!bytesRead)break;length+=bytesRead;}
    return length>MAX_TEXT*4?null:buffer.subarray(0,length);
  }finally{await handle.close();}
}
function scopeId(scope,root){return digest(JSON.stringify([root,scope.sessionId]));}
function paragraphs(chunks){
  const result=[];
  for(const chunk of chunks){let offset=0,line=chunk.line??null;
    for(const text of chunk.text.match(/[^\n]*\n|[^\n]+$/g)||[]){
      result.push({text,location:chunk.location,page:chunk.page??null,line,chunk:chunk.ordinal,offset,paragraph:result.length+1});
      offset+=text.length;if(line!==null)line++;
    }
  }return result;
}
async function snapshot(scope,input){
  const file=await confinedPath(scope.root,input);await scope.authorize?.(file.path);
  const sha256=await fileHash(file.path),warnings=[];let chunks=[],status='complete';
  if(['.txt','.md'].includes(extname(file.path).toLowerCase())){
    const bytes=await boundedTextBytes(file.path);
    if(bytes===null){status='unavailable';warnings.push('文本超过本次对比范围，请拆分条款后对比。');}
    else try{const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);if(text.includes('\0'))throw Error();chunks=[{ordinal:0,text,location:'text',line:1}];}catch{status='unavailable';warnings.push('文字编码不可读，请另存 UTF-8 文本，原件保留。');}
  }else{
    let db;
    try{
      const index=await confinedPath(file.root,'.qx-materials/index.sqlite',{internal:true});
      db=new DatabaseSync(index.path,{readOnly:true});
      // Metadata, warnings and chunks must describe one parser generation, including during WAL writes.
      db.exec('BEGIN');
      const material=db.prepare('SELECT sha256,status,warnings FROM materials WHERE path=?').get(file.key);
      if(!material||material.sha256!==sha256)throw Error('unparsed');
      const issues=JSON.parse(material.warnings||'[]');warnings.push(...(Array.isArray(issues)?issues.map(String):[]));
      status=material.status==='ready'?'complete':'partial';
      // Only the existing parser supplies page numbers and source anchors; never infer Office page layout.
      chunks=db.prepare('SELECT ordinal,page,location,text FROM chunks WHERE path=? ORDER BY ordinal LIMIT ?').all(file.key,MAX_PARAGRAPHS+1);
      warnings.push('仅比较已提取文字；表格结构、图片、版式和修订显示请对照原件。');
      if(warnings.some(w=>!/^(DOCX 修订视图：original|仅比较已提取文字)/.test(w)))status='partial';
      if(extname(file.path).toLowerCase()==='.docx'&&!warnings.includes('DOCX 修订视图：original')){chunks=[];status='unavailable';warnings.push('当前索引并非已确认的原文修订视图，请按 original 重新解析。');}
      if(!chunks.length){status='unavailable';warnings.push('没有可比较文字，请先解析材料或核对扫描件。');}
    }catch(error){if(error.status===403)throw error;status='unavailable';warnings.push('尚无当前版本的文字索引。请在对话中让助手先读取并解析这两份合同，再重试对比。');}
    finally{db?.close();}
  }
  let rows=paragraphs(chunks),used=0;const kept=[];
  for(const row of rows){if(kept.length>=MAX_PARAGRAPHS||used+row.text.length>MAX_TEXT){status='partial';warnings.push('文字较长，本次仅对比前200000字符及前4000个提取段；其余内容未比较。');break;}kept.push(row);used+=row.text.length;}
  if(await fileHash(file.path)!==sha256)throw comparisonError('原文件已变化，请重新对比',409);
  return {path:file.key,absolutePath:file.path,sha256,scope:scopeId(scope,file.root),status,warnings:[...new Set(warnings)],paragraphs:kept};
}
function side(document,row){if(!row)return null;return {text:row.text,reference:{scope:document.scope,path:document.path,sha256:document.sha256,paragraph:row.paragraph,chunk:row.chunk,location:row.location,page:row.page,line:row.line,offset:row.offset,quoteSha256:digest(row.text)}};}
const metadata=({paragraphs,absolutePath,...document})=>document;
export function refineContractChanges(changes,deadline){
  let limited=false;
  for(const change of changes){const remaining=deadline-performance.now();
    const parts=remaining>0?diffChars(change.before?.text||'',change.after?.text||'',{timeout:Math.min(100,remaining),maxEditLength:8000}):undefined;
    change.parts=parts||[{value:change.before?.text||'',removed:true},{value:change.after?.text||'',added:true}];change.characterDetail=!!parts;limited||=!parts;
  }return limited;
}
export async function compareContracts(scope,beforePath,afterPath){
  const before=await snapshot(scope,beforePath),after=await snapshot(scope,afterPath),warnings=[...before.warnings,...after.warnings];
  if([before,after].some(d=>d.status==='unavailable'))return {status:'unavailable',equal:null,before:metadata(before),after:metadata(after),changes:[],warnings:[...new Set(warnings)]};
  const deadline=performance.now()+1500;
  const blocks=diffArrays(before.paragraphs.map(p=>p.text),after.paragraphs.map(p=>p.text),{timeout:1000,maxEditLength:6000});
  if(!blocks)return {status:'partial',equal:null,before:metadata(before),after:metadata(after),changes:[],warnings:[...warnings,'差异计算达到本次上限，未能生成完整对比，请分段重试。']};
  const changes=[];let old=0,next=0;
  for(let i=0;i<blocks.length;i++){
    const block=blocks[i];if(!block.added&&!block.removed){old+=block.count;next+=block.count;continue;}
    let deleted=0,added=0;
    if(block.removed){deleted=block.count;if(blocks[i+1]?.added)added=blocks[++i].count;}else added=block.count;
    for(let n=0;n<Math.max(deleted,added);n++){
      const left=side(before,n<deleted?before.paragraphs[old+n]:null),right=side(after,n<added?after.paragraphs[next+n]:null);
      changes.push({before:left,after:right});
    }old+=deleted;next+=added;
  }
  if(refineContractChanges(changes,deadline))warnings.push('部分段落达到字符细化总预算，已保留整段增删，请对照原文。');
  const status=[before,after].every(d=>d.status==='complete')?'complete':'partial';
  return {status,equal:status==='complete'?changes.length===0:null,before:metadata(before),after:metadata(after),changes,warnings:[...new Set(warnings)]};
}
export async function resolveContractReference(scope,reference){
  const root=await realpath(scope.root);
  if(!reference||reference.scope!==scopeId(scope,root))throw comparisonError('引用归属已变化，请在原对话与工作区重新对比',409);
  const document=await snapshot(scope,reference.path);
  if(document.sha256!==reference.sha256)throw comparisonError('原文件已变化，旧引用失效，请重新对比',409);
  const row=document.paragraphs[reference.paragraph-1],expected=row&&side(document,row).reference;
  if(!expected||Object.keys(expected).some(key=>expected[key]!==reference[key]))throw comparisonError('原文定位已失效，请重新解析并对比',409);
  return {...side(document,row),absolutePath:document.absolutePath,context:document.paragraphs.slice(Math.max(0,row.paragraph-2),row.paragraph+1).map(item=>({text:item.text,paragraph:item.paragraph,selected:item.paragraph===row.paragraph})),warnings:document.warnings};
}
