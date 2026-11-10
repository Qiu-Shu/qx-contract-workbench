import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createKnowledgeReader,createKnowledgeManager} from '../plugins/case-memory/index.mjs';
import {fixture} from './helpers.mjs';

for(const change of ['source correction','disabled memory'])test(`a ${change} between provider preflight and commit cannot partially save a rejected memory edit`,async()=>{
  const installed=(process.env.QX_TEST_APP||path.resolve(path.dirname(process.execPath),'..')),python=path.join(installed,'runtime/python/python.exe');
  const stage=fileURLToPath(new URL('../',import.meta.url));
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-audit-provider-')),bridge=path.join(root,'provider'),workspace=path.join(root,'synthetic');
  fs.mkdirSync(bridge,{recursive:true});for(const name of ['case_memory.py','business_store.py','store.py']){const staged=path.join(stage,'bridge',name);fs.copyFileSync(fs.existsSync(staged)?staged:path.join(installed,'bridge',name),path.join(bridge,name));}
  const env={...process.env,PYTHONIOENCODING:'utf-8',QX_HINDSIGHT_URL:'',QX_HINDSIGHT_TOKEN:'',QX_HINDSIGHT_INSTANCE_ID:''};
  const seed="import json,sys;from business_store import CaseStore;from case_memory import CaseMemoryStore;c=CaseStore(sys.argv[1]);a=c.create('synthetic');n=c.add_note(a['id'],'fact','original synthetic note','test');m=CaseMemoryStore(sys.argv[1]);r=m.add(a['id'],note_id=n['id']);print(json.dumps({'case':a,'note':n['id'],'memory':r['memory']['id']}))";
  const seeded=JSON.parse(execFileSync(python,['-c',seed,workspace],{cwd:bridge,env,encoding:'utf8'}));
  const raw=async(action,args)=>{const response=JSON.parse(execFileSync(python,[path.join(bridge,'case_memory.py'),'--workspace',workspace],{input:JSON.stringify({action,args}),env,encoding:'utf8'}));if(!response.ok)throw Object.assign(Error(response.error),{status:response.status});return response.result;};
  const run=async(action,args)=>{
    if(action==='update'){
      if(change==='source correction')execFileSync(python,['-c',"import sys;from business_store import CaseStore;CaseStore(sys.argv[1]).add_note(sys.argv[2],'fact','replacement synthetic note','test',supersedes=sys.argv[3])",workspace,seeded.case.id,seeded.note],{cwd:bridge,env,encoding:'utf8'});
      else await raw('settings',{case_id:seeded.case.id,enabled:false});
    }
    return raw(action,args);
  };
  const f=fixture({caseMemory:createKnowledgeReader(run),caseMemoryManage:createKnowledgeManager(run,()=>{})});
  try{
    f.store.project({id:seeded.case.id,title:'synthetic'});
    const response=await f.request('memory-review',{project:seeded.case.id,memoryId:seeded.memory,revision:1,content:'edit that should not commit'});
    assert.equal(response.status,409);
    const stored=await raw('read',{case_id:seeded.case.id,memory_id:seeded.memory});
    assert.equal(stored.content,'original synthetic note','a rejected edit must not alter authoritative content');
    assert.equal(stored.revision,1);
  }finally{f.service.dispose();}
});
