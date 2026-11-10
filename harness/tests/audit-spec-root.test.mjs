import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {fixture} from './helpers.mjs';
import {createKnowledgeReader,createKnowledgeManager} from '../plugins/case-memory/index.mjs';

const caseId='11111111-1111-4111-8111-111111111111';
const accepting=async()=>({kind:'accept'});
async function capturedWork(){
  const f=fixture({caseMemoryManage:async(action,args)=>action==='status'?{case_id:args.case_id,enabled:true}:{cases:[]}});
  f.add('audit-synthetic','独立虚构工作',[{seq:1,role:'user',text:'虚构合同预付款十万元。'}]);
  await f.call('knowledge_start',{query:'预付款'},'audit-synthetic');
  const project=f.store.binding('audit-synthetic'),entry=f.store.list(project)[0];
  f.store.review(entry.id,{project,revision:entry.revision,action:'confirm',content:'律师已核对：虚构合同预付款已经取消。'});
  f.store.resource(project,{document:'synthetic-document',title:'独立虚构附件'});
  return {f,project,entry};
}
async function createCase(f){
  await f.listeners.get('tools/post-execute')({name:'mcp__qx_legal__create_case',agent:{session:{id:'audit-synthetic'}}},{value:{structuredContent:{id:caseId,title:'独立虚构案件'}}},accepting);
  await f.service.runner.run({incremental:true,sessionId:'audit-synthetic'});
}

test('audit: creating a case keeps the current work lawyer correction available',async()=>{
  const {f}=await capturedWork();
  try{await createCase(f);assert.equal(f.store.binding('audit-synthetic'),caseId);
    const hits=await f.call('knowledge_recall',{query:'预付款'},'audit-synthetic');
    assert.ok(hits.some(item=>item.content.includes('已经取消')),'case creation must not replace lawyer correction with the old automatic excerpt');
  }finally{f.service.dispose();}
});
test('audit: creating a case keeps existing uploaded-resource links in current work',async()=>{
  const {f,project}=await capturedWork();
  try{await createCase(f);assert.equal(f.store.resources(project).length,1);
    assert.equal(f.store.resources(caseId).length,1,'automatically adopting current work must keep its uploaded document index');
  }finally{f.service.dispose();}
});
test('audit: undoing a scope correction restores the prior lawyer correction',async()=>{
  const {f,project}=await capturedWork();
  try{f.store.project({id:'synthetic-other',title:'虚构另一工作'});f.store.bind('audit-synthetic','synthetic-other');
    f.store.undoBinding('audit-synthetic',f.store.bindingInfo('audit-synthetic').revision);
    await f.service.runner.run({incremental:true,sessionId:'audit-synthetic'});
    assert.ok(f.store.search(project,'预付款').some(item=>item.content.includes('已经取消')),'undo must retain an already corrected source-backed record');
  }finally{f.service.dispose();}
});
test('audit: explicitly binding the already selected work still establishes human precedence',async()=>{
  const {f,project}=await capturedWork();
  try{const binding=f.store.bindingInfo('audit-synthetic');
    const response=await f.request('bind',{session:'audit-synthetic',project,expectedProject:project,revision:binding.revision});
    assert.equal(response.status,200);await createCase(f);
    assert.equal(f.store.binding('audit-synthetic'),project,'an explicit successful human binding must prevent subsequent automatic reassignment');
  }finally{f.service.dispose();}
});
test('audit: moved-work revision history survives backup and restore',async()=>{
  const {f,entry}=await capturedWork(),restored=fixture();
  try{await createCase(f);
    const before=f.store.history(entry.id,caseId);assert.ok(before.some(row=>row.content.includes('已经取消')));
    restored.store.restore(f.store.exportPage());
    const after=restored.store.history(entry.id,caseId);
    assert.deepEqual(after.map(row=>[row.revision,row.content]),before.map(row=>[row.revision,row.content]),'old-scope audit revisions must not be silently dropped when restoring the moved entry');
  }finally{restored.service.dispose();f.service.dispose();}
});
test('audit: an explicitly independent record retains its earlier source-backed audit after restore',async()=>{
  const {f,project,entry}=await capturedWork(),restored=fixture();
  try{const current=f.store.entry(entry.id,project);
    f.store.review(entry.id,{project,revision:current.revision,action:'independent'});
    const before=f.store.history(entry.id,project);assert.equal(before.length,2);
    restored.store.restore(f.store.exportPage());
    assert.equal(restored.store.entry(entry.id,project).session,'');
    assert.deepEqual(restored.store.history(entry.id,project).map(row=>[row.revision,row.content]),before.map(row=>[row.revision,row.content]),'independent records retain their original audit while source access remains detached');
  }finally{restored.service.dispose();f.service.dispose();}
});
test('audit: scope migration rejects old scope reads and leaves other sessions and independent entries behind',async()=>{
  const {f,project,entry}=await capturedWork();
  try{
    f.add('other-synthetic','另一独立虚构对话',[{seq:1,role:'user',text:'另一对话的虚构交付要求。'}]);
    f.store.bind('other-synthetic',project);await f.service.runner.run({incremental:true,sessionId:'other-synthetic'});
    const other=f.store.list(project).find(row=>row.session==='other-synthetic');assert.ok(other);
    const version=f.store.origins().find(row=>row.session==='audit-synthetic').version;
    const [independent]=f.store.upsertBatch('audit-synthetic',version,'independent-fixture',[{kind:'summary',title:'独立条目',content:'已明确另存的独立记录',sources:[{seq:1,quote:'虚构合同'}]}]);
    f.store.review(independent,{project,revision:1,action:'independent'});
    const before=f.store.entry(entry.id,project);await createCase(f);
    assert.equal(f.store.entry(entry.id,caseId).revision,before.revision+1);
    assert.equal((await f.request('entry?project='+project+'&entryId='+entry.id)).status,404);
    assert.equal((await f.request('history?project='+project+'&entryId='+entry.id)).status,404);
    assert.equal((await f.request('trace',{project,entryId:entry.id,seq:1})).status,404);
    assert.equal(f.store.binding('other-synthetic'),project);assert.equal(f.store.entry(other.id,project).session,'other-synthetic');
    assert.equal(f.store.entry(independent,project).session,'');assert.equal(f.store.entry(independent,project).state,'confirmed');
    assert.equal(f.store.resources(caseId).length,0,'resources of a scope shared with another session must not follow the moved session');
  }finally{f.service.dispose();}
});
test('audit: pending and rejected records keep their state through migration and undo',async()=>{
  const {f,project}=await capturedWork();
  try{const version=f.store.origins().find(row=>row.session==='audit-synthetic').version;
    const [pending,rejected]=f.store.upsertBatch('audit-synthetic',version,'pending-fixture',[
      {kind:'rule',title:'待确认规则',content:'规则尚未获律师确认',sources:[{seq:1,quote:'虚构合同'}]},
      {kind:'decision',title:'已驳回决策',content:'这项方案已经驳回',sources:[{seq:1,quote:'虚构合同'}]},
    ]);
    f.store.review(rejected,{project,revision:1,action:'reject'});await createCase(f);
    assert.equal(f.store.entry(pending,caseId).state,'pending');assert.equal(f.store.entry(rejected,caseId).state,'rejected');
    assert.ok(!f.store.search(caseId,'规则 方案').some(row=>[pending,rejected].includes(row.id)));
    f.store.undoBinding('audit-synthetic',f.store.bindingInfo('audit-synthetic').revision);
    assert.equal(f.store.entry(pending,project).state,'pending');assert.equal(f.store.entry(rejected,project).state,'rejected');
  }finally{f.service.dispose();}
});
test('audit: manually moving a conversation cannot copy an existing cases resources to another case',async()=>{
  const {f}=await capturedWork(),otherCase='33333333-3333-4333-8333-333333333333';
  try{f.store.project({id:caseId,title:'虚构案件甲'});f.store.project({id:otherCase,title:'虚构案件乙'});
    f.store.bind('audit-synthetic',caseId);f.store.resource(caseId,{document:'case-a-private-resource',title:'仅甲案资料'});
    f.store.bind('audit-synthetic',otherCase,{adoptPrivateResources:true});
    assert.equal(f.store.resources(caseId).length,1);assert.equal(f.store.resources(otherCase).length,0);
  }finally{f.service.dispose();}
});

const installed=(process.env.QX_TEST_APP||path.resolve(path.dirname(process.execPath),'..')),staging=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const env={...process.env,PYTHONIOENCODING:'utf-8',QX_HINDSIGHT_URL:'',QX_HINDSIGHT_TOKEN:'',QX_HINDSIGHT_INSTANCE_ID:''};
function duplicateProvider(distinctCount=2){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'knowledge-audit-synthetic-'));
  const bridge=path.join(root,'provider'),workspace=path.join(root,'synthetic-data'),python=path.join(installed,'runtime/python/python.exe');
  fs.mkdirSync(bridge,{recursive:true});
  for(const name of ['case_memory.py','business_store.py','store.py']){
    const candidate=path.join(staging,'bridge',name);
    fs.copyFileSync(fs.existsSync(candidate)?candidate:path.join(installed,'bridge',name),path.join(bridge,name));
  }
  const seed=[
    'import json,sys',
    'from business_store import CaseStore',
    'from case_memory import CaseMemoryStore',
    'c=CaseStore(sys.argv[1])',
    "a=c.create('独立虚构分页案件')",
    "n=c.add_note(a['id'],'fact','验收：重复第一条要求','独立来源甲')",
    'm=CaseMemoryStore(sys.argv[1])',
    "duplicates=[m.add(a['id'],note_id=n['id']) for _ in range(21)]",
    'independent=[]',
    'for index in range(int(sys.argv[2])-1):',
    "    note=c.add_note(a['id'],'fact','验收：独有第二条要求','独立来源 '+str(index))",
    "    independent.append(m.add(a['id'],note_id=note['id'])['memory']['id'])",
    "print(json.dumps({'case':a,'unique':independent[0],'distinct':independent}))",
  ].join('\n');
  const seeded=JSON.parse(execFileSync(python,['-c',seed,workspace,String(distinctCount)],{cwd:bridge,env,encoding:'utf8'}));
  const run=async(action,args)=>{const r=JSON.parse(execFileSync(python,[path.join(bridge,'case_memory.py'),'--workspace',workspace],{input:JSON.stringify({action,args}),env,encoding:'utf8'}));if(!r.ok)throw Error(r.error);return r.result;};
  const f=fixture({caseMemory:createKnowledgeReader(run),caseMemoryManage:createKnowledgeManager(run,()=>{})});
  f.store.project({id:seeded.case.id,title:seeded.case.title});
  return {f,seeded};
}
test('audit: duplicates must not fill the provider recall limit and hide a distinct match',async()=>{
  const {f,seeded}=duplicateProvider();
  try{const data=await(await f.request('list?project='+seeded.case.id+'&query='+encodeURIComponent('验收'))).json();
    assert.ok(data.memories.items.some(m=>m.id==='memory-'+seeded.unique),'deduplication after provider top-8 hides a distinct matching source');
  }finally{f.service.dispose();}
});
test('audit: the same source must not reappear on subsequent case-memory pages',async()=>{
  const {f,seeded}=duplicateProvider();
  try{const collected=[];let offset=0,pages=0;
    do{const page=await(await f.request('memories?project='+seeded.case.id+'&offset='+offset)).json();
      assert.equal(page.available,true,page.notice);assert.ok(++pages<=10,'provider pagination must terminate');
      for(const item of page.items){assert.ok(!collected.some(a=>a.sourceNote===item.sourceNote&&a.content===item.content&&a.revision===item.revision),'same-source same-revision duplicate crossed provider page boundary');collected.push(item);}
      offset=page.next??null;
    }while(offset!==null);
    assert.equal(collected.length,2,'21 copies of one source plus one independent source yield exactly two records');
  }finally{f.service.dispose();}
});
test('audit: twenty-two independent sources still paginate without merging identical prose',async()=>{
  const {f,seeded}=duplicateProvider(22);
  try{const first=await(await f.request('memories?project='+seeded.case.id)).json();
    assert.equal(first.items.length,20);assert.notEqual(first.next,null);
    const second=await(await f.request('memories?project='+seeded.case.id+'&offset='+first.next)).json();
    assert.equal(second.items.length,2);assert.equal(second.next,null);
    const all=[...first.items,...second.items];assert.equal(new Set(all.map(item=>item.sourceNote)).size,22);
    for(const memory of seeded.distinct)assert.ok(all.some(item=>item.id==='memory-'+memory),'different sources with identical prose remain available');
  }finally{f.service.dispose();}
});
