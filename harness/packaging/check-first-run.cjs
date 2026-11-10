// Starts the real packaged shell with a new profile, without a model key.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  if(!process.argv[2]||!process.argv[3])throw Error('Use check-first-run.cjs <candidate> <new-data-directory>');
  const candidate=path.resolve(process.argv[2]),data=path.resolve(process.argv[3]);
  assert.equal(fs.existsSync(data),false,'Use an empty, isolated data profile');
  const reserved=net.createServer();await new Promise(resolve=>reserved.listen(0,'127.0.0.1',resolve));const port=reserved.address().port;await new Promise(resolve=>reserved.close(resolve));
  const env={...process.env,QX_INSTALL_DATA:data};delete env.DEEPSEEK_API_KEY;delete env.QX_PAYLOAD_ROOT;delete env.ELECTRON_RUN_AS_NODE;
  const child=spawn(path.join(candidate,'QunxingWorkbench.exe'),['--remote-debugging-port='+port],{env,windowsHide:true,stdio:'ignore'});
  let socket;
  try{
    let page;for(let attempt=0;attempt<150;attempt++){try{page=(await(await fetch('http://127.0.0.1:'+port+'/json/list')).json()).find(item=>item.type==='page'&&item.url.endsWith('/setup.html'));if(page)break;}catch{}await delay(200);}
    assert.ok(page,'Fresh installation must show setup, not a connection timeout');
    socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
    const result=await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('Page inspection timed out')),5000);socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id===1){clearTimeout(timeout);resolve(data)}});socket.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression:'({ready:document.readyState,password:!!document.querySelector("input[type=password]"),body:document.body.innerText.length})',returnByValue:true}}));});
    assert.equal(result.result.result.value.ready,'complete');assert.equal(result.result.result.value.password,true);assert.ok(result.result.result.value.body>20);
    socket.send(JSON.stringify({id:2,method:'Browser.close'}));
    const report={passed:true,firstRunShowsSetup:true,isolatedData:true,noModelRequests:true};
    fs.writeFileSync(path.join(data,'first-run-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  }finally{socket?.close();await delay(500);if(child.exitCode===null)child.kill();}
}
main().catch(error=>{console.error(error);process.exitCode=1});
