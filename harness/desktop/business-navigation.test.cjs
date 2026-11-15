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
for(const mode of ['reception','contract','case','hearing','media'])test(`ordinary new chat skips the blank ${mode} workflow without deleting it`,()=>{
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

test('unsent attachments retain their existing session across navigation, then release on removal or teardown',async()=>{
 const window={},business=fs.readFileSync(require.resolve('./integration/business-client.js'),'utf8');
 vm.runInNewContext(business,{window});assert.equal(typeof window.qxCreateDraftRetainer,'function');
 let retained=0,released=0,changed;const rows={a:{},b:{}};
 const keeper=window.qxCreateDraftRetainer({list:{getSnapshot:()=>({byId:rows}),subscribe:fn=>{changed=fn;return()=>changed=null}},
   retain:(id,options)=>{assert.equal(options.source,'qxDraft');retained++;return {ready:Promise.resolve(),release:()=>released++}}});
 keeper.update('a',{attachmentIds:['original-receipt']});keeper.update('a',{attachmentIds:['original-receipt']});
 keeper.update('b',{attachmentIds:[]});assert.equal(retained,1);assert.equal(released,0);
 keeper.update('a',{attachmentIds:[]});assert.equal(released,1);
 keeper.update('b',{attachmentIds:['other-receipt']});delete rows.b;changed();assert.equal(released,2);
 keeper.update('a',{attachmentIds:['last-receipt']});keeper.dispose();keeper.dispose();
 assert.equal(released,3);assert.equal(changed,null);
});
const business=fs.readFileSync(require.resolve('./integration/business-client.js'),'utf8');
for(const phase of ['pending','ready'])test(`business creation follows workspace readiness: ${phase}`,()=>{
 const start=business.indexOf('  function Entries('),end=business.indexOf('  function ContractComparison(',start);
 const createElement=(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)});
 const render=vm.runInNewContext('('+business.slice(start,end).trim()+')',{
  initialSelectionReady:true,useBusiness:()=>({busy:false,states:{},index:[]}),useSessions:()=>({phase,byId:phase==='ready'?{current:{id:'current',retainedBy:{mainView:1}}}:{}}),useWorkspaces:()=>({phase,items:phase==='ready'?[{workspaceId:'synthetic'}]:[]}),React:{useState:()=>[null,()=>{}]},
  h:createElement,modes:[{id:'contract',title:'合同审查'}],icon:()=>null,create:async()=>{},ctx:{uiWorkspace:{openSession(){}}}
 });
 const root=render({wide:true});const buttons=[];function walk(el){if(!el||typeof el!=='object')return;if(el.type==='button')buttons.push(el);for(const child of el.children||[])walk(child)}walk(root);
 assert.equal(buttons.find(el=>el.props['aria-label']==='新建合同审查对话').props.disabled,phase!=='ready');
});

test('business entry waits for the first workspace even when the empty list is ready',()=>{
 const start=business.indexOf('  function Entries('),end=business.indexOf('  function ContractComparison(',start);
 const render=vm.runInNewContext('('+business.slice(start,end).trim()+')',{
  initialSelectionReady:true,useBusiness:()=>({busy:false,states:{},index:[]}),useSessions:()=>({phase:'ready',byId:{}}),useWorkspaces:()=>({phase:'ready',items:[]}),React:{useState:()=>[null,()=>{}]},
  h:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}),modes:[{id:'contract',title:'合同审查'}],icon:()=>null,create:async()=>{},ctx:{uiWorkspace:{openSession(){}}}
 });
 const root=render({wide:true});let entry;function walk(el){if(!el||typeof el!=='object')return;if(el.props['aria-label']==='新建合同审查对话')entry=el;for(const child of el.children||[])walk(child)}walk(root);
 assert.equal(entry.props.disabled,true);
});

for(const initialized of [false,true])test(`no current conversation after initial selection: ${initialized}`,()=>{
 const start=business.indexOf('  function Entries('),end=business.indexOf('  function ContractComparison(',start);
 const render=vm.runInNewContext('('+business.slice(start,end).trim()+')',{
  initialSelectionReady:initialized,useBusiness:()=>({busy:false,states:{},index:[]}),useSessions:()=>({phase:'ready',byId:{}}),useWorkspaces:()=>({phase:'ready',items:[{workspaceId:'synthetic'}]}),React:{useState:()=>[null,()=>{}]},
  h:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}),modes:[{id:'contract',title:'合同审查'}],icon:()=>null,create:async()=>{},ctx:{uiWorkspace:{openSession(){}}}
 });
 const root=render({wide:true});let entry;function walk(el){if(!el||typeof el!=='object')return;if(el.props['aria-label']==='新建合同审查对话')entry=el;for(const child of el.children||[])walk(child)}walk(root);
 assert.equal(entry.props.disabled,!initialized);
});
