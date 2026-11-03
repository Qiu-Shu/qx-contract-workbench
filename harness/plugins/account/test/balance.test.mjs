import test from 'node:test';
import assert from 'node:assert/strict';
import {createBalanceReader} from '../balance.mjs';

const payload=(amount='12.340000000000000001',is_available=true)=>({is_available,balance_infos:[{currency:'CNY',total_balance:amount,granted_balance:'0.00',topped_up_balance:amount}]});
const response=value=>new Response(JSON.stringify(value),{status:200,headers:{'content-type':'application/json'}});

test('preserves exact monetary strings and real zero remains successful',async()=>{
  const read=createBalanceReader({resolveKey:async()=> 'synthetic-key',fetchImpl:async(url,init)=>{
    assert.equal(url,'https://api.deepseek.com/user/balance');assert.equal(init.redirect,'error');
    assert.equal(init.headers.Authorization,'Bearer synthetic-key');return response(payload());
  }});
  const value=await read();assert.equal(value.status,'ok');assert.equal(value.balances[0].total_balance,'12.340000000000000001');
  const zero=await createBalanceReader({resolveKey:async()=> 'synthetic-key',fetchImpl:async()=>response(payload('0.00',false))})();
  assert.equal(zero.status,'ok');assert.equal(zero.isAvailable,false);assert.equal(zero.balances[0].total_balance,'0.00');
});
test('missing credentials are unavailable and never call the provider',async()=>{
  const value=await createBalanceReader({resolveKey:async()=>undefined,fetchImpl:()=>{throw new Error('must not call');}})();
  assert.equal(value.status,'unavailable');assert.equal(value.reason,'not_configured');assert.deepEqual(value.balances,[]);
});
test('unauthorized responses never become zero or echo upstream credentials',async()=>{
  const value=await createBalanceReader({resolveKey:async()=> 'synthetic-secret',fetchImpl:async()=>new Response('synthetic-secret',{status:401})})();
  assert.equal(value.status,'error');assert.equal(value.reason,'authentication');assert.deepEqual(value.balances,[]);
  assert.equal(JSON.stringify(value).includes('synthetic-secret'),false);
});
test('network and malformed payload errors are separate from valid balances',async()=>{
  for(const fetchImpl of [async()=>{throw new Error('synthetic-secret network');},async()=>response({...payload(),balance_infos:[{currency:'CNY',total_balance:'NaN'}]})]){
    const value=await createBalanceReader({resolveKey:async()=> 'synthetic-secret',fetchImpl})();
    assert.equal(value.status,'error');assert.deepEqual(value.balances,[]);assert.equal(JSON.stringify(value).includes('synthetic-secret'),false);
  }
});
test('cache lasts 120 seconds; manual refresh is limited to one per 15 seconds',async()=>{
  let now=0,calls=0;const read=createBalanceReader({resolveKey:async()=> 'key',clock:()=>now,fetchImpl:async()=>{calls++;return response(payload());}});
  await read();now=1000;assert.equal((await read({refresh:true})).cached,true);assert.equal(calls,1);
  now=15000;await read({refresh:true});assert.equal(calls,2);
  now=134999;await read();assert.equal(calls,2);now=135000;await read();assert.equal(calls,3);
});
test('concurrent clients share one request',async()=>{
  let calls=0,release;const gate=new Promise(resolve=>release=resolve);
  const read=createBalanceReader({resolveKey:async()=> 'key',fetchImpl:async()=>{calls++;await gate;return response(payload());}});
  const a=read(),b=read();await new Promise(resolve=>setImmediate(resolve));assert.equal(calls,1);release();
  assert.deepEqual(await a,await b);
});
test('credential rotation invalidates cache and rejects an old in-flight result',async()=>{
  let key='first',calls=0,release;const gate=new Promise(resolve=>release=resolve);
  const read=createBalanceReader({resolveKey:async()=>key,fetchImpl:async()=>{calls++;if(calls===1)await gate;return response(payload());}});
  const old=read();await new Promise(resolve=>setImmediate(resolve));key='second';release();
  assert.equal((await old).reason,'credentials_changed');assert.equal((await read()).status,'ok');assert.equal(calls,2);
});
