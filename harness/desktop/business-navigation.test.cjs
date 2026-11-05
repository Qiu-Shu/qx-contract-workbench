const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {createRequire}=require('node:module');
const dsh=createRequire(require.resolve('@deepseek-ai/dsh/package.json'));
const web=createRequire(dsh.resolve('@deepseek-ai/dsh-web-app/package.json'));
const source=fs.readFileSync(web.resolve('@deepseek-ai/dsh-client-ui-workspace/client'),'utf8');
const start=source.indexOf('createInWorkspace(workspace, options) {');
const end=source.indexOf('\n\t\t\t/**',start);
assert.ok(start>0&&end>start);
const create=vm.runInNewContext('({'+source.slice(start,end)+'})').createInWorkspace;
for(const mode of ['reception','contract','case','hearing'])test(`ordinary new chat skips the blank ${mode} workflow without deleting it`,()=>{
  const rows={business:{id:'business',blank:true,cwd:'/case'},ordinary:{id:'ordinary',blank:true,cwd:'/case'}};
  const owner={workspaces:{list:{getSnapshot:()=>({archivedSessionIds:[]})}},sessions:{list:{getSnapshot:()=>({ids:Object.keys(rows),byId:rows})}},canReuseBlank:id=>id!=='business',createNamed:request=>request};
  const result=create.call(owner,{workspaceId:'w',path:'/case',sessionIds:Object.keys(rows)},{});
  assert.equal(result.sessionId,'ordinary');assert.equal(rows.business.blank,true);
  delete rows.ordinary;
  assert.equal(create.call(owner,{workspaceId:'w',path:'/case',sessionIds:['business']},{}).sessionId,undefined);
});
test('ordinary blank reuse remains available without a business extension',()=>{
 const owner={workspaces:{list:{getSnapshot:()=>({archivedSessionIds:[]})}},sessions:{list:{getSnapshot:()=>({ids:['ordinary'],byId:{ordinary:{blank:true,cwd:'/case'}}})}},createNamed:request=>request};
 assert.equal(create.call(owner,{workspaceId:'w',path:'/case',sessionIds:['ordinary']},{}).sessionId,'ordinary');
});
