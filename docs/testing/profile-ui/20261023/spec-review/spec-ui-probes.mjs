import test from 'node:test';
import assert from 'node:assert/strict';
import {opened,calls,mutations,failure} from './generation-fixture.mjs';
import {fixture as panelFixture,saved,deferred} from './panel-fixture.mjs';

test('existing plus failed GET never reauthorizes or reposts; later authorization loss clears state',async()=>{
  const f=await opened({approval:{ok:true,status:'existing'}});
  f.api.findGenerationRequest=async(_id,request)=>{f.calls.push(['find',request]);throw failure('NETWORK_UNKNOWN',503);};
  assert.equal(await f.c.send(),false);await f.c.send();await f.c.refreshGeneration();
  assert.equal(calls(f,'approve').length,1);assert.equal(calls(f,'preview').length,1);assert.equal(mutations(f).length,0);
  const requested=calls(f,'approve')[0][1].request_id;
  assert.ok(calls(f,'find').every(c=>c[1]===requested));
  f.api.findGenerationRequest=async()=>{throw failure('AUTHORIZATION_REQUIRED',401);};
  await f.c.refreshGeneration();assert.equal(f.c.state.status,'revoked');
  assert.equal(f.c.state.text,'');assert.deepEqual(f.c.state.generation.items,[]);assert.equal(mutations(f).length,0);
});

test('acknowledged profile POST followed by permission loss cannot leave local result or trigger another send',async()=>{
  const f=await opened(),submit=f.api.submitProfileGeneration;
  f.api.submitProfileGeneration=async(...args)=>{const result=await submit(...args);
    f.api.getConversation=async()=>{throw failure('CROSS_MATTER_DENIED',403);};return result;};
  assert.equal(await f.c.send(),false);assert.equal(f.c.state.status,'revoked');
  assert.equal(f.c.state.text,'');assert.deepEqual(f.c.state.generation.items,[]);
  await f.c.send();await f.c.refreshGeneration();
  assert.equal(calls(f,'profile').length,1);assert.equal(calls(f,'approve').length,1);assert.equal(calls(f,'plain').length,0);
});

test('closed and reopened profile reads reject the earlier response without clearing the newer panel',async()=>{
  const f=panelFixture(),gate=deferred();f.read=()=>gate.promise;
  const earlier=f.panel.open();f.panel.close();
  f.read=async()=>({...saved(),revision:8});assert.equal(await f.panel.open(),true);
  gate.resolve(saved());assert.equal(await earlier,false);
  assert.equal(f.at('profile-preview').hidden,false);assert.match(f.at('profile-notice').textContent,/版本 8/);
  assert.match(f.at('profile-content').textContent,/9999999999999999\.12345678/);
  assert.equal(f.calls.length,2);
});
