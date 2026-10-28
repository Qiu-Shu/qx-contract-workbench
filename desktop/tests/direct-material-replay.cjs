// Read saved fictional results with the actual packaged app; never send a model request.
const {_electron}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const executable=path.resolve(process.argv[2]||''),fixture=path.resolve(process.argv[3]||''),output=path.resolve(process.argv[4]||'');
assert.ok(fs.statSync(executable).isFile());
const prior=JSON.parse(fs.readFileSync(path.join(fixture,'report.json'),'utf8'));
assert.equal(prior.synthetic_only,true);assert.equal(prior.status,'PASS');
const data=path.join(fixture,'synthetic-data');
assert.equal(fs.existsSync(path.join(data,'model-credentials','deepseek.bin')),false,'Replay requires no model credential.');
assert.equal(fs.existsSync(output),false,'Use a fresh output folder.');fs.mkdirSync(output,{recursive:true});
const report={started:new Date().toISOString(),status:'RUNNING',mode:'packaged-replay',checks:[],model_posts:0,external_requests:0};
let app,page;const errors=[];
(async()=>{try{
  app=await _electron.launch({executablePath:executable,args:[],env:{...process.env,QX_DESKTOP_DATA_PARENT:data},timeout:90000});
  page=await app.firstWindow();page.setDefaultTimeout(30000);
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    if(request.method()==='POST'&&request.url().endsWith('/material-generations'))report.model_posts++;
    if(/^https?:/.test(request.url())&&!/^http:\/\/127\.0\.0\.1:\d+\//.test(request.url()))report.external_requests++;
  });
  await page.waitForURL(/\/login$/,{timeout:90000});
  await page.locator('[name=username]').fill('虚构模型验收律师');await page.locator('[name=password]').fill('fiction123');
  await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL(/\/assistant$/);
  report.checks.push('packaged-login-existing-fictional-data');
  const records=prior.attempts.filter(item=>item.has_output);
  for(const record of records){
    const cid=record.conversation_id;
    await page.locator('[data-conversation-id="'+cid+'"]').click();await page.waitForURL('**/assistant/'+cid);
    const result=page.locator('.generation-result[data-attempt-id="'+record.id+'"] .generation-text').first();await result.waitFor();
    assert.ok((await result.textContent()).length>100);
    const document=await page.evaluate(async ({cid,id})=>{
      const reply=await fetch('/api/assistant/conversations/'+cid+'/material-generations/'+id+'/document');
      return {status:reply.status,type:reply.headers.get('Content-Type'),bytes:reply.ok?(await reply.arrayBuffer()).byteLength:0};
    },{cid,id:record.id});
    assert.equal(document.status,200);assert.ok(document.type.includes('wordprocessingml'));assert.ok(document.bytes>1000);
    report.checks.push(record.workflow+'-saved-result-and-docx');
  }
  await page.screenshot({path:path.join(output,'saved-result.png'),fullPage:true});
  assert.equal(report.model_posts,0);assert.equal(report.external_requests,0);assert.deepEqual(errors,[]);
  report.checks.push('zero-model-posts-and-page-errors');report.status='PASS';
}catch(error){report.status='FAIL';report.error=String(error.message);process.exitCode=1;
  if(page)await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
}finally{
  if(app)await app.close().catch(()=>{});report.finished=new Date().toISOString();
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}})();
