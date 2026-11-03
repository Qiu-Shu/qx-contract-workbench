import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as pause} from 'node:timers/promises';
import {apply} from './index.mjs';

const python=process.env.QX_TEST_PYTHON;
test('isolated Harness bridge workflow: original Host, upload, citations, backup and merge', {skip:!python}, async()=>{
  const workspaces=[];const disposers=[];
  async function service(){
    const workspace=await mkdtemp(join(tmpdir(),'qx-kb-routes-'));workspaces.push(workspace);
    const routes=new Map();
    apply({connection:{fetch:{register:r=>routes.set(r.path,r)}},effect:f=>disposers.push(f())},{workspace,python});
    return async(path,options={})=>{
      const request=new Request('http://dsh.internal/api/qx-knowledge/'+path,{...options,
        headers:{host:'127.0.0.1:3080','x-qx-knowledge':'1',
          ...(options.method==='POST'?{origin:'http://127.0.0.1:3080'}:{}),...options.headers}});
      const route=routes.get(new URL(request.url).pathname);
      assert.ok(route);assert.ok(route.methods.includes(request.method));
      return route.fetch(request);
    };
  }
  async function body(response){const data=await response.json();assert.ok(response.ok,JSON.stringify(data));return data;}
  try{
    const request=await service();
    assert.equal((await request('backup',{method:'POST',headers:{'x-qx-knowledge':''}})).status,403);
    assert.equal((await request('backup',{method:'POST',headers:{origin:'https://attacker.invalid'}})).status,403);
    assert.equal((await request('backup',{method:'POST',headers:{origin:'http://127.0.0.1:3081'}})).status,403);
    assert.equal((await request('backup',{method:'POST',headers:{origin:'http://dsh.internal'}})).status,403);
    assert.equal((await request('upload',{method:'POST',headers:{'x-qx-filename':'..%2Fbad.txt'},body:'x'})).status,400);
    const uploaded=await body(await request('upload',{method:'POST',headers:{origin:'http://127.0.0.1:3080','x-qx-filename':encodeURIComponent('范本.txt')},body:'x'.repeat(3998)+'劳动合同解除'}));
    let ready=false;
    for(let attempt=0;attempt<150;attempt++){
      const catalog=await body(await request('documents'));
      if(catalog.documents[0]?.state==='error')assert.fail(catalog.documents[0].error);
      if(catalog.documents[0]?.state==='ready'&&!catalog.documents[0]?.busy){ready=true;break;}
      await pause(200);
    }
    assert.ok(ready,'isolated text indexing completes');
    const found=await body(await request('search?q='+encodeURIComponent('劳动合同')));
    assert.equal(found.matches.length,1);assert.equal(found.matches[0].citations.length,2);
    for(const ref of found.matches[0].citations)await body(await request('citation?reference='+encodeURIComponent(ref.citation)));
    const backup=await body(await request('backup',{method:'POST'}));
    const downloaded=await request(backup.download.split('/api/qx-knowledge/')[1]);
    assert.equal(downloaded.headers.get('content-type'),'application/zip');
    const archive=await downloaded.arrayBuffer();assert.ok(archive.byteLength>0);
    const second=await service();
    const restored=await body(await second('restore',{method:'POST',body:archive}));
    assert.equal(restored.imported,1);
    assert.equal((await body(await second('restore',{method:'POST',body:archive}))).skipped,1);
    assert.equal((await body(await second('search?q='+encodeURIComponent('劳动合同')))).matches[0].citation,found.matches[0].citation);
    assert.equal((await second('restore',{method:'POST',body:'not a zip'})).status,400);
    await body(await second('archive?id='+uploaded.id,{method:'POST'}));
    assert.equal((await body(await second('search?q='+encodeURIComponent('劳动合同')))).matches.length,0);
    await body(await second('archive?id='+uploaded.id+'&restore=1',{method:'POST'}));
    const source=await second('source?id='+uploaded.id);assert.equal(source.headers.get('x-content-type-options'),'nosniff');
    assert.equal((await source.text()).slice(-6),'劳动合同解除');
  }finally{
    for(const dispose of disposers)dispose();
    await pause(300);
    for(const workspace of workspaces)await rm(workspace,{recursive:true,force:true,maxRetries:5,retryDelay:200});
  }
});
