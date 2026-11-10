import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir,copyFile,mkdtemp} from 'node:fs/promises';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {fixture} from './helpers.mjs';
import {apply} from '../plugins/knowledge/index.mjs';
test('real library upload classifies, links, indexes and preserves saved files when linking changes',async()=>{
  const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),installed=resolve(dirname(process.execPath),'..');
  await mkdir(join(root,'bridge'),{recursive:true});for(const file of ['knowledge.py','store.py','reader.py'])await copyFile(join(installed,'bridge',file),join(root,'bridge',file));
  await mkdir(join(root,'tests/.fixtures'),{recursive:true});const workspace=await mkdtemp(join(root,'tests/.fixtures/upload-'));
  const f=fixture(),routes=new Map(),cleanup=[];f.add('upload');let rejectLink=false;
  const oldLegacy=process.env.QX_LEGACY_ROOT;process.env.QX_LEGACY_ROOT=join(installed,'legacy');
  apply({connection:{fetch:{register:r=>routes.set(r.path,r)}},serial:async(name,data)=>{if(rejectLink&&name==='qx/knowledge/document')throw Error('simulated scope changed');return f.listeners.get(name)?.(data);},effect:fn=>cleanup.push(fn())},{workspace,python:join(installed,'runtime/python/python.exe')});
  const call=async(route,body)=>routes.get('/api/qx-knowledge/'+route).fetch(new Request('http://localhost/api/qx-knowledge/'+route,{method:body?'POST':'GET',headers:{'x-qx-knowledge':'1','x-qx-session':'upload','x-qx-filename':encodeURIComponent('虚构采购合同.txt')},...(body?{body}:{})}));
  const settled=async()=>{for(let i=0;i<60;i++){const result=await(await call('documents')).json();if(result.documents.length&&!result.documents.some(d=>d.busy))return result;await new Promise(r=>setTimeout(r,100));}throw Error('document indexing did not settle');};
  try{
    const upload=await call('upload','独立虚构测试：验收期限七日，不含任何真实客户资料。');assert.equal(upload.status,201);const saved=await upload.json();assert.equal(saved.linkWarning,undefined);
    const list=await settled();assert.equal(list.documents[0].category,'合同与协议');assert.equal(list.documents[0].state,'ready');
    const project=f.store.binding('upload');assert.equal(f.store.resources(project)[0].document,saved.id);
    rejectLink=true;const second=await(await call('upload','第二版独立虚构测试材料。')).json();assert.match(second.linkWarning,/无需重复上传/);const both=await settled();assert.equal(both.total,2);assert.equal(f.store.resources(project).length,1);
  }finally{for(const close of cleanup)close();f.service.dispose();if(oldLegacy===undefined)delete process.env.QX_LEGACY_ROOT;else process.env.QX_LEGACY_ROOT=oldLegacy;}
});
