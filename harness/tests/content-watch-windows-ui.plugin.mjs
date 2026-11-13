// Test transport only. The installed desktop integration supplies the real knowledge service.
import assert from 'node:assert/strict';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
export const name='qx-content-windows-ui-fixture';
export const inject=['connection','agents','workspaceRegistry','qxKnowledge'];
export async function apply(ctx,config){
  const fixture=new URL(config.fixtureApi);
  assert.equal(fixture.protocol,'http:');assert.equal(fixture.hostname,'127.0.0.1');
  const {installContentWatch}=await import(pathToFileURL(join(config.productRoot,'plugins/content-watch/index.mjs')).href);
  await installContentWatch(ctx,{workspace:config.workspace,stateDir:config.stateDir},{
    fetchImpl(input,options){
      const original=new URL(input);assert.equal(original.origin,'https://api.justoneapi.com');
      assert.ok(['/api/xiaohongshu/search-note/v4','/api/xiaohongshu/get-note-detail/v1'].includes(original.pathname));
      return fetch(new URL(original.pathname+original.search,fixture),options);
    },
  });
}
