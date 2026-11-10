import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './helpers.mjs';

test('late source metadata cannot invalidate a newer accepted generation',async()=>{
  const f=fixture();let release;
  try{
    f.add('a');await f.call('knowledge_start',{query:'合同'},'a');const project=f.store.binding('a'),original=f.store.list(project)[0];
    f.store.review(original.id,{project,revision:original.revision,action:'confirm'});
    const describe=f.source.describe;let enter,delay=true;const gate=new Promise(resolve=>release=resolve),ready=new Promise(resolve=>enter=resolve);
    f.source.describe=async session=>{const snapshot=await describe(session);if(delay){delay=false;enter();await gate;}return snapshot;};
    const late=f.service.runner.syncMaterials('a').catch(error=>error);await ready;
    f.sessions.get('a').messages.push({seq:2,role:'user',text:'新的合成补充，原确认保持有效。'});
    await f.service.runner.run({incremental:true});
    assert.equal(f.store.entry(original.id,project).state,'confirmed');
    release();await late;
    assert.equal(f.store.entry(original.id,project).state,'confirmed','out-of-order source snapshots must not revoke newer validated records');
    assert.equal(f.store.db.prepare('SELECT version FROM origins WHERE session=?').get('a').version,await f.source.current('a'));
  }finally{release?.();f.service.dispose();}
});

test('a late fresh snapshot cannot invalidate a newer accepted generation',async()=>{
  const f=fixture();let release;
  try{
    f.add('a');await f.call('knowledge_start',{query:'合同'},'a');const project=f.store.binding('a'),original=f.store.list(project)[0];
    f.store.review(original.id,{project,revision:original.revision,action:'confirm'});
    f.sessions.get('a').messages.push({seq:2,role:'user',text:'第一次合成补充。'});
    const describe=f.source.describe;let enter,delay=true;const gate=new Promise(resolve=>release=resolve),ready=new Promise(resolve=>enter=resolve);
    f.source.describe=async session=>{const snapshot=await describe(session);if(delay){delay=false;enter();await gate;}return snapshot;};
    const late=f.service.runner.fresh('a').catch(error=>error);await ready;
    f.sessions.get('a').messages.push({seq:3,role:'user',text:'第二次合成补充，原确认保持有效。'});
    await f.service.runner.run({incremental:true});
    assert.equal(f.store.entry(original.id,project).state,'confirmed');
    release();const result=await late;
    assert.equal(result.status,409);
    assert.equal(f.store.entry(original.id,project).state,'confirmed','late freshness checks must not revoke newer validated records');
    assert.equal(f.store.db.prepare('SELECT version FROM origins WHERE session=?').get('a').version,await f.source.current('a'));
  }finally{release?.();f.service.dispose();}
});
