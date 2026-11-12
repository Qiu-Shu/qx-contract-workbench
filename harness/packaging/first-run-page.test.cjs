const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {inspectFirstRunPage}=require('./check-first-run.cjs');

test('first-run inspection waits for load when the page exists before its body',async()=>{
  let loaded,settled=false;
  const document={readyState:'loading',body:null,querySelector:()=>null};
  const pending=vm.runInNewContext('('+inspectFirstRunPage.toString()+')()',{document,addEventListener:(name,callback,options)=>{assert.equal(name,'load');assert.equal(options.once,true);loaded=callback;}});
  pending.then(()=>{settled=true;});await Promise.resolve();assert.equal(settled,false);
  document.readyState='complete';document.body={innerText:'Synthetic first-run setup content'};document.querySelector=()=>({});loaded();
  assert.deepEqual(JSON.parse(JSON.stringify(await pending)),{ready:'complete',password:true,body:33});
});

test('already loaded setup resolves without waiting for a past load event',async()=>{
  const result=await vm.runInNewContext('('+inspectFirstRunPage.toString()+')()',{document:{readyState:'complete',body:{innerText:'ready'},querySelector:()=>null},addEventListener:()=>{throw Error('must not wait for past load');}});
  assert.deepEqual(JSON.parse(JSON.stringify(result)),{ready:'complete',password:false,body:5});
});
