import {test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import vm from 'node:vm';
test('source navigation keeps the full original path and text line and never opens another session',async()=>{
  let source;try{source=await readFile(new URL('./contract-compare-client.js',import.meta.url),'utf8');}catch{}
  assert.ok(source,'comparison client is missing');
  const calls=[],window={},document={documentElement:{dataset:{qxSessionId:'s'}},querySelectorAll:()=>[]};
  vm.runInNewContext(source,{window,document,setTimeout,clearTimeout,AbortController,URLSearchParams});
  const ctx={sidebarRight:{openResource:(...args)=>calls.push(args)}};
  const original={absolutePath:'C:/项目/原合同.txt',reference:{line:12,page:null}};
  window.qxContractPreview(ctx,'s',original);assert.equal(calls.length,1);assert.match(calls[0][0],/%E5%8E%9F%E5%90%88%E5%90%8C.txt$/);assert.equal(calls[0][1].params.line,12);
  assert.throws(()=>window.qxContractPreview(ctx,'different',original),/对话已切换/);assert.equal(calls.length,1);
});
test('PDF navigation waits for the exact resource and never scrolls a different original',async()=>{
  const source=await readFile(new URL('./contract-compare-client.js',import.meta.url),'utf8');let scrolled=0,disconnected=0,callback;
  const window={},path='C:/合同/原件.pdf',address='dsh-resource://file/session/s/'+path.split('/').map(encodeURIComponent).join('/');
  const wrong={dataset:{textpreviewUrl:address.replace('s/','other/')},querySelector:selector=>selector==='[data-pdf-page="2"]'?{scrollIntoView:()=>assert.fail('wrong original scrolled')}:null};
  const right={dataset:{textpreviewUrl:address},querySelector:selector=>selector==='[data-pdf-page="2"]'?{scrollIntoView:()=>scrolled++}:null};
  const document={documentElement:{dataset:{qxSessionId:'s'}},body:{},querySelectorAll:()=>[wrong,right]};
  vm.runInNewContext(source,{window,document,MutationObserver:class{constructor(f){callback=f}observe(){}disconnect(){disconnected++}},setTimeout:()=>1,clearTimeout(){}});
  window.qxContractPreview({sidebarRight:{openResource(){}}},'s',{absolutePath:path,reference:{page:2,line:null}});
  assert.equal(scrolled,1);assert.equal(disconnected,1);
});
test('a second PDF navigation cancels the pending observer from the previous reference',async()=>{
  const source=await readFile(new URL('./contract-compare-client.js',import.meta.url),'utf8');let stopped=0;
  const window={},document={documentElement:{dataset:{qxSessionId:'s'}},body:{},querySelectorAll:()=>[]};
  vm.runInNewContext(source,{window,document,MutationObserver:class{observe(){}disconnect(){stopped++}},setTimeout:()=>1,clearTimeout(){}});
  const ctx={sidebarRight:{openResource(){}}},original={absolutePath:'C:/合同/a.pdf',reference:{page:2}};
  window.qxContractPreview(ctx,'s',original);window.qxContractPreview(ctx,'s',{...original,absolutePath:'C:/合同/b.pdf'});assert.equal(stopped,1);
});
