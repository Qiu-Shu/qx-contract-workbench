import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const source=await readFile(new URL('./contract-compare-client.js',import.meta.url),'utf8');
function factory(){const window={};vm.runInNewContext(source,{window,AbortController,setTimeout,clearTimeout});return window.qxCreateComparisonState;}
test('returning to a comparison preserves references and result without executing again',async()=>{
 const make=factory();assert.equal(typeof make,'function');
 let calls=0;const store=make(async()=>{calls++;return {equal:false,changes:[]}});
 const key='sessionA:caseA:revision1';store.choose(key,'before','original.txt');store.choose(key,'after','revised.txt');
 await store.run(key,{sessionId:'A'});store.open(key,false);store.open(key,true);
 assert.equal(calls,1);assert.equal(store.get(key).before,'original.txt');assert.equal(store.get(key).result.equal,false);
 assert.equal(store.get('sessionA:caseB:revision2').result,null);
 assert.equal(store.get('sessionB:caseA:revision1').before,'');
});
test('double click coalesces; failure and timeout never retry automatically',async()=>{
 let reject,calls=0;const store=factory()(()=>{calls++;return new Promise((_,r)=>reject=r)});
 store.choose('k','before','a');store.choose('k','after','b');const first=store.run('k',{sessionId:'s'});
 const second=store.run('k',{sessionId:'s'});assert.equal(calls,1);reject(Error('请求超时'));await Promise.all([first,second]);
 assert.equal(store.get('k').busy,false);assert.equal(store.get('k').error,'请求超时');
 store.open('k',false);store.open('k',true);assert.equal(calls,1);
});
test('changed file invalidates result; late response cannot enter another selection',async()=>{
 let done;const store=factory()(()=>new Promise(r=>done=r));
 store.choose('k','before','a');store.choose('k','after','b');const pending=store.run('k',{});
 store.choose('k','before','c');done({equal:true});await pending;
 assert.equal(store.get('k').result,null);assert.equal(store.get('k').before,'c');assert.equal(store.get('k').busy,false);
});
test('comparison registers a preview action and exposes its reusable business component, not a general dock',()=>{
 const registrations=[],window={},document={createElement:()=>({remove(){}}),head:{append(){}}};
 const ctx={slots:{inject:(_n,fn)=>fn(),register:(spec,component)=>{registrations.push({spec,component});return()=>{}}}};
 window.dispatchEvent=()=>{};vm.runInNewContext(source,{window,document,AbortController,Event});
 const dispose=window.qxInstallContractComparison(ctx,{createElement(){}});
 assert.equal(registrations.some(r=>r.spec.name==='conversation.input.dock'),false);
 assert.ok(registrations.some(r=>r.spec.name==='sidebar.right.tab.document.actions'));
 assert.equal(typeof window.qxComparisonPanel,'function');dispose();
});

test('business and preview share one comparison surface without extra workspaces',()=>{
 const store=factory()(()=>assert.fail('must not run'));
 store.open('scope',true,'business');assert.equal(store.get('scope').surface,'business');
 store.open('scope',true,'preview');assert.equal(store.get('scope').surface,'preview');
 store.open('scope',false,'preview');assert.equal(store.get('scope').open,false);
 store.dispose();
});

test('switching originals clears the prior comparison partner and prefills only the new original',async()=>{
 const window={dispatchEvent(){}},document={createElement:()=>({remove(){}}),head:{append(){}}};
 let entry,phase='outer',current,calls=0;
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),
   useState:initial=>[phase==='outer'&&initial===null?{scopeKey:'same-scope'}:initial,()=>{}],
   useEffect(){},useRef:()=>({current:0}),
   useSyncExternalStore:(_subscribe,get)=>{current=get();return current;}};
 const ctx={slots:{inject:(_n,fn)=>fn(),register:(_spec,component)=>{entry=component;return()=>{}}}};
 vm.runInNewContext(source,{window,document,AbortController,AbortSignal,Event,fetch:async()=>{calls++;return {ok:true,json:async()=>({status:'complete',warnings:[],before:{},after:{},changes:[]})}}});
 const dispose=window.qxInstallContractComparison(ctx,React);
 function render(path){
   const panel=entry({ownerSessionId:'s',absolutePath:path});phase='outer';
   const body=panel.type(panel.props);phase='inner';return body.type(body.props);
 }
 render('/a.txt').children[0].props.onClick();
 assert.equal(render('/a.txt').children[0].props['aria-expanded'],true);
 function find(tree){if(!tree||typeof tree!=='object')return;if(tree.props?.label==='新版本')return tree;for(const child of [tree.children||[]].flat(Infinity)){const hit=find(child);if(hit)return hit;}}
 await find(render('/a.txt')).props.onChange('/a2.txt');assert.equal(calls,1);
 const b=render('/b.txt');assert.equal(b.children[0].props['aria-expanded'],false);
 b.children[0].props.onClick();assert.equal(render('/b.txt').children[0].props['aria-expanded'],true);
 assert.equal(current.before,'/b.txt');assert.equal(current.after,'');assert.equal(calls,1);dispose();
});

test('late locate cannot replace a preview selected on the other comparison surface',async()=>{
 const window={dispatchEvent(){}},document={createElement:()=>({remove(){}}),head:{append(){}}};
 let entry,phase='outer',finishLocate,opened=0;
 const result={status:'complete',equal:false,warnings:[],before:{},after:{},changes:[{before:{reference:{line:1}},after:null,parts:[{value:'old',removed:true}],characterDetail:true}]};
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),
   useState:initial=>[phase==='outer'&&initial===null?{scopeKey:'same-scope'}:initial,()=>{}],
   useEffect(){},useRef:()=>({current:0}),useSyncExternalStore:(_subscribe,get)=>get()};
 const ctx={slots:{inject:(_n,fn)=>fn(),register:(_spec,component)=>{entry=component;return()=>{}}}};
 const fetch=async url=>({ok:true,json:()=>url.endsWith('/locate')?new Promise(resolve=>finishLocate=resolve):result});
 vm.runInNewContext(source,{window,document,AbortController,AbortSignal,Event,fetch,setTimeout});
 const dispose=window.qxInstallContractComparison(ctx,React);window.qxContractPreview=()=>opened++;
 function render(preview){phase='outer';const outer=preview?entry({ownerSessionId:'s',absolutePath:'/b.txt'}):{type:window.qxComparisonPanel,props:{session:{id:'s'}}};const body=outer.type(outer.props);phase='inner';return body.type(body.props);}
 function find(tree,predicate){if(!tree||typeof tree!=='object')return; if(predicate(tree))return tree;for(const child of [tree.children||[]].flat(Infinity)){const hit=find(child,predicate);if(hit)return hit;}}
 render(false).children[0].props.onClick();
 find(render(false),e=>e.props.label==='原版本').props.onChange('/a.txt');
 await find(render(false),e=>e.props.label==='新版本').props.onChange('/a2.txt');
 const pending=find(render(false),e=>e.props['aria-label']==='回看原版本 第1行').props.onClick();
 await new Promise(setImmediate);render(true).children[0].props.onClick();
 finishLocate({absolutePath:'/a.txt',reference:{line:1}});await pending;
 assert.equal(opened,0);dispose();
});

for(const action of ['return','change-file'])test('late legal preparation does not write after '+action,async()=>{
 const window={dispatchEvent(){}},document={createElement:()=>({remove(){}}),head:{append(){}}};
 let phase='outer',finish,writes=0;
 const result={status:'complete',equal:false,warnings:[],before:{path:'a.txt',sha256:'a'.repeat(64)},after:{path:'b.txt',sha256:'b'.repeat(64)},changes:[],rows:[]};
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),useState:initial=>[phase==='outer'&&initial===null?{scopeKey:'scope'}:initial,()=>{}],useEffect(){},useRef:()=>({current:0}),useSyncExternalStore:(_subscribe,get)=>get()};
 const ctx={slots:{inject:(_n,fn)=>fn(),register:()=>()=>{}}};
 const fetch=async url=>({ok:true,json:()=>url.endsWith('/analysis-draft')?new Promise(resolve=>finish=resolve):result});
 vm.runInNewContext(source,{window,document,AbortController,AbortSignal,Event,fetch,setTimeout:()=>0});
 const dispose=window.qxInstallContractComparison(ctx,React);window.qxAnalyzeComparison=async(_id,prepare)=>{await prepare('甲方');writes++;};
 function render(){phase='outer';const body=window.qxComparisonPanel({session:{id:'s'},party:'甲方'});phase='inner';return body.type(body.props);}
 function find(tree,predicate){if(!tree||typeof tree!=='object')return;if(predicate(tree))return tree;for(const child of [tree.children||[]].flat(Infinity)){const hit=find(child,predicate);if(hit)return hit;}}
 const button=(tree,text)=>find(tree,e=>e.type==='button'&&e.children[0]===text);
 render().children[0].props.onClick();
 find(render(),e=>e.props.label==='原版本').props.onChange('a.txt');await find(render(),e=>e.props.label==='新版本').props.onChange('b.txt');
 const pending=button(render(),'AI分析修改影响').props.onClick();await new Promise(setImmediate);
 if(action==='return')button(render(),'返回原对话').props.onClick();else await find(render(),e=>e.props.label==='原版本').props.onChange('other.txt');
 finish({text:'must not enter composer'});await pending;assert.equal(writes,0);dispose();
});

test('one other-file selection compares automatically in the existing preview, reopening and unchanged selection do not compare',async()=>{
 const window={dispatchEvent(){}},document={createElement:()=>({remove(){}}),head:{append(){}}};let phase='outer',entry,calls=0;
 const result={status:'complete',equal:true,warnings:[],before:{path:'a.txt'},after:{path:'b.txt'},changes:[],rows:[]};
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),useState:initial=>[phase==='outer'&&initial===null?{scopeKey:'scope',initialPath:'a.txt'}:initial,()=>{}],useEffect(){},useRef:()=>({current:0}),useSyncExternalStore:(_subscribe,get)=>get()};
 const ctx={slots:{inject:(_n,fn)=>fn(),register:(_spec,component)=>{entry=component;return()=>{}}}};
 vm.runInNewContext(source,{window,document,AbortController,AbortSignal,Event,fetch:async()=>{calls++;return {ok:true,json:async()=>result}},setTimeout:()=>0});
 const dispose=window.qxInstallContractComparison(ctx,React);
 function render(){phase='outer';const outer=entry({ownerSessionId:'s',absolutePath:'a.txt'}),body=outer.type(outer.props);phase='inner';return body.type(body.props);}
 function find(tree,predicate){if(!tree||typeof tree!=='object')return;if(predicate(tree))return tree;for(const child of [tree.children||[]].flat(Infinity)){const hit=find(child,predicate);if(hit)return hit;}}
 render().children[0].props.onClick();assert.equal(calls,0);
 assert.equal(find(render(),e=>e.props.label==='原版本'),undefined);
 await find(render(),e=>e.props.label==='新版本').props.onChange('b.txt');assert.equal(calls,1);
 assert.equal(find(render(),e=>e.type==='dialog'||e.type==='input'),undefined);
 assert.ok(find(render(),e=>e.type==='button'&&e.children[0]==='AI分析修改影响'));
 render().children[0].props.onClick();render().children[0].props.onClick();assert.equal(calls,1);
 await find(render(),e=>e.props.label==='新版本').props.onChange('b.txt');assert.equal(calls,1);dispose();
});
