import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {pathToFileURL,fileURLToPath} from 'node:url';import {execFileSync} from 'node:child_process';
import {createKnowledgeReader,createKnowledgeManager} from '../plugins/case-memory/index.mjs';import {fixture} from './helpers.mjs';import {installKnowledge} from '../desktop/integration/knowledge-api.mjs';
const installed=(process.env.QX_TEST_APP||path.resolve(path.dirname(process.execPath),'..')),stage=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),python=path.join(installed,'runtime/python/python.exe');
const env={...process.env,PYTHONIOENCODING:'utf-8',QX_HINDSIGHT_URL:'',QX_HINDSIGHT_TOKEN:'',QX_HINDSIGHT_INSTANCE_ID:''};
test('actual case records stay in their provider across two relocated Chinese and space paths',async()=>{
  for(const label of ['律所 甲','Second office']){
    const root=fs.mkdtempSync(path.join(os.tmpdir(),label+'-')),bridge=path.join(root,'provider'),workspace=path.join(root,'业务 数据');fs.mkdirSync(bridge,{recursive:true});
    for(const name of ['case_memory.py','business_store.py','store.py'])fs.copyFileSync(fs.existsSync(path.join(stage,'bridge',name))?path.join(stage,'bridge',name):path.join(installed,'bridge',name),path.join(bridge,name));
    const seed="import json,sys;from business_store import CaseStore;from case_memory import CaseMemoryStore;c=CaseStore(sys.argv[1]);a=c.create('独立虚构案件');n=c.add_note(a['id'],'fact','虚构交付日期五月十日','虚构电话记录');m=CaseMemoryStore(sys.argv[1]);r=m.add(a['id'],note_id=n['id']);print(json.dumps({'case':a,'note':n['id'],'memory':r['memory']['id']}))";
    const seeded=JSON.parse(execFileSync(python,['-c',seed,workspace],{cwd:bridge,env,encoding:'utf8'}));
    const run=async(action,args)=>{const r=JSON.parse(execFileSync(python,[path.join(bridge,'case_memory.py'),'--workspace',workspace],{input:JSON.stringify({action,args}),env,encoding:'utf8'}));if(!r.ok)throw Object.assign(Error(r.error),{status:r.status});return r.result;};
    const queued=[],f=fixture({caseMemory:createKnowledgeReader(run),caseMemoryManage:createKnowledgeManager(run,id=>queued.push(id))});
    try{
      f.add('a');await f.request('case-scope',{caseId:seeded.case.id,title:seeded.case.title});f.store.bind('a',seeded.case.id);
      const page=await(await f.request('list?project='+seeded.case.id)).json();assert.equal(page.memories.items.length,1);assert.equal(f.store.list(seeded.case.id).length,0,'no copy of authoritative memory into knowledge rows');
      assert.equal((await f.request('memory-review',{project:seeded.case.id,memoryId:seeded.memory,revision:1,content:'纠正：六月十日'})).status,200);assert.equal(queued.length,1);
      assert.equal((await f.request('memory-review',{project:seeded.case.id,memoryId:seeded.memory,revision:1,content:'旧版本覆盖'})).status,409);
      const saved=await run('read',{case_id:seeded.case.id,memory_id:seeded.memory});assert.equal(saved.content,'纠正：六月十日');assert.equal(saved.source.snapshot,'虚构交付日期五月十日');
      await run('settings',{case_id:seeded.case.id,enabled:false});assert.deepEqual((await f.call('knowledge_recall',{query:'六月'},'a')),[]);
      assert.equal((await f.request('memory-review',{project:seeded.case.id,memoryId:seeded.memory,revision:2,content:'已停用'})).status,409);
      assert.equal((await run('read',{case_id:seeded.case.id,memory_id:seeded.memory})).content,'纠正：六月十日');
    }finally{f.service.dispose();}
  }
});
test('knowledge runtime respects the configured data root and works without a case provider',async()=>{
  const before=process.env.QX_INSTALL_DATA;
  try{for(const label of ['安装 一','install two']){
    const root=fs.mkdtempSync(path.join(os.tmpdir(),label+'-'));process.env.QX_INSTALL_DATA=root;
    const f=fixture();let service;try{service=installKnowledge(f.ctx,{source:f.source,schedule:false});f.add('new');
      const response=await(await f.request('state?sessionId=new')).json();assert.ok(response.project.startsWith('task-'));assert.deepEqual(response.cases,[]);assert.ok(fs.existsSync(path.join(root,'.local/layered-knowledge.sqlite')));
    }finally{service?.dispose();f.service.dispose();}
  }}finally{if(before===undefined)delete process.env.QX_INSTALL_DATA;else process.env.QX_INSTALL_DATA=before;}
  for(const name of ['knowledge-memory.mjs','knowledge-api.mjs'])assert.ok(!/[A-Za-z]:[\\/]/.test(fs.readFileSync(path.join(stage,'desktop/integration',name),'utf8')),'no machine drive path in '+name);
});
