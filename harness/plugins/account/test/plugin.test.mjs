import test from 'node:test';
import assert from 'node:assert/strict';
import {apply,inject} from '../index.mjs';
test('registers exclusively through the authenticated owner-only Harness API channel',async()=>{
  let route;const ctx={credentials:{async resolve(name){assert.equal(name,'DEEPSEEK_API_KEY');return undefined;}},connection:{fetch:{register(value){route=value;return()=>{};}}}};
  apply(ctx);assert.deepEqual(inject,['connection','credentials']);assert.equal(route.path,'/api/qx-account/balance');assert.deepEqual(route.methods,['GET']);
  const res=await route.fetch(new Request('http://127.0.0.1/api/qx-account/balance'));const body=await res.json();
  assert.equal(body.status,'unavailable');assert.equal(res.headers.get('cache-control'),'no-store');
});
