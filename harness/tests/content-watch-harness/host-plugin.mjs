// Real application services; only the external content transport is a local fixture.
import assert from 'node:assert/strict';
import {installKnowledge} from '../../desktop/integration/knowledge-api.mjs';
import {installContentWatch} from '../../plugins/content-watch/index.mjs';
import {createSessionDelivery} from '../../plugins/content-watch/session.mjs';

export const name='qx-content-harness-fixture';
export const inject=['connection','agents','workspaceRegistry','sessions','systemPrompt','sessionQuery','tools'];
export async function apply(ctx,config){
  const fixture=new URL(config.fixtureApi);
  assert.equal(fixture.protocol,'http:');assert.equal(fixture.hostname,'127.0.0.1');
  installKnowledge(ctx,{schedule:false});
  const sessionDelivery=createSessionDelivery(ctx,{workspace:config.workspace,stateDir:config.stateDir});
  const prepare=sessionDelivery.prepare;
  sessionDelivery.prepare=async()=>{try{return await prepare();}catch(error){console.error('Synthetic fixture session preparation failed:',error.stack);throw error;}};
  await installContentWatch(ctx,{workspace:config.workspace,stateDir:config.stateDir},{
    sessionDelivery,
    fetchImpl(url,options){
      const original=new URL(url);assert.equal(original.origin,'https://api.justoneapi.com');
      assert.ok(['/api/xiaohongshu/search-note/v4','/api/xiaohongshu/get-note-detail/v1'].includes(original.pathname));
      const local=new URL(original.pathname+original.search,fixture);
      return fetch(local,options);
    },
  });
}
