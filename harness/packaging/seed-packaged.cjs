// QA only: save a newly invented credential inside the actual executable's
// encryption context. No existing credential is read or copied.
(async()=>{
  const port=Number(process.argv[2]);
  if(!Number.isInteger(port)||port<1024||port>65535)throw Error('Invalid test inspector');
  const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const socket=new WebSocket(targets[0].webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});
  const expression=`(async()=>{
    if(!process.env.QX_INSTALL_DATA?.includes('installer-check-'))throw Error('Isolated test directory required');
    const req=process.mainModule.require.bind(process.mainModule);
    const {app,safeStorage}=req('electron');
    const {createModelCredentialStore}=req(process.resourcesPath+'/app.asar/model-credentials.cjs');
    return await createModelCredentialStore({dataParent:app.getPath('userData'),safeStorage}).save('sk-synthetic-packaged-installer-check-key');
  })()`;
  const response=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Test credential timeout')),20000);
    socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id===1){clearTimeout(timer);resolve(message)}});
    socket.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression,awaitPromise:true,returnByValue:true}}));
  });
  socket.close();
  if(response.result?.result?.value?.status!=='saved')throw Error(JSON.stringify(response.result?.exceptionDetails||response));
  console.log('Synthetic credential saved by packaged executable.');
})().catch(error=>{console.error(error.message);process.exitCode=1});
