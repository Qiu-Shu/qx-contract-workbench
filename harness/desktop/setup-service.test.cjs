const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateKey}=require('./setup-service.cjs');

test('reject blank keys before contacting provider',async()=>{
  let called=false;
  const result=await validateKey(' ',async()=>{called=true});
  assert.equal(result.ok,false);assert.equal(called,false);
});
test('verify via fixed official endpoint without a model request',async()=>{
  const result=await validateKey('sk-synthetic-key-0123456789',async(url,options)=>{
    assert.equal(url,'https://api.deepseek.com/user/balance');
    assert.equal(options.headers.Authorization,'Bearer sk-synthetic-key-0123456789');
    assert.equal(options.redirect,'error');
    return {ok:true,json:async()=>({is_available:true,balance_infos:[]})};
  });
  assert.equal(result.ok,true);
});
test('authentication and network failures are useful and contain no secret',async()=>{
  const key='sk-synthetic-key-0123456789';
  const invalid=await validateKey(key,async()=>({ok:false,status:401}));
  const offline=await validateKey(key,async()=>{throw Error(key)});
  assert.equal(invalid.ok,false);assert.equal(offline.ok,false);
  assert.match(invalid.message,/API Key/);assert.match(offline.message,/网络/);
  assert.equal(JSON.stringify([invalid,offline]).includes(key),false);
});
