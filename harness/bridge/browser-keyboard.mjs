// Complete CDP keyboard payloads for the explicitly selected bb-browser tab.
import {readFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';

const [targetId,combination]=process.argv.slice(2);
let socket;
try{
  if(!/^[0-9a-f]{32}$/i.test(targetId||''))throw new Error('需要明确的完整 tabId。');
  const specials={Enter:['Enter',13,'\r'],Tab:['Tab',9,''],Escape:['Escape',27,''],Backspace:['Backspace',8,''],Delete:['Delete',46,''],Space:['Space',32,' '],ArrowLeft:['ArrowLeft',37,''],ArrowUp:['ArrowUp',38,''],ArrowRight:['ArrowRight',39,''],ArrowDown:['ArrowDown',40,''],Home:['Home',36,''],End:['End',35,''],PageUp:['PageUp',33,''],PageDown:['PageDown',34,'']};
  const pieces=(combination||'').split('+'),raw=pieces.pop();let modifiers=0;
  const masks={Alt:1,Control:2,Ctrl:2,Meta:4,Shift:8,ControlOrMeta:2};
  for(const modifier of pieces){if(!masks[modifier])throw new Error('不支持的组合键修饰符。');modifiers|=masks[modifier];}
  let key=raw,code,virtual,text='';
  if(specials[raw]){[code,virtual,text]=specials[raw];if(raw==='Space')key=' ';}
  else if(/^[a-z]$/i.test(raw)){code='Key'+raw.toUpperCase();virtual=raw.toUpperCase().charCodeAt(0);if(!modifiers&&raw===raw.toUpperCase())modifiers|=8;key=(modifiers&8)?raw.toUpperCase():raw.toLowerCase();text=key;}
  else if(/^[0-9]$/.test(raw)){code='Digit'+raw;virtual=raw.charCodeAt(0);text=raw;}
  else throw new Error('暂支持字母、数字、Enter、Tab、Escape、方向键及 Control/Alt/Shift/Meta 组合；正文请用 fill/type。');
  if(modifiers&7)text='';
  let endpoint=process.env.BB_BROWSER_CDP_URL;
  if(!endpoint){const port=(await readFile(join(homedir(),'.bb-browser/browser/cdp-port'),'utf8')).trim();if(!/^\d+$/.test(port))throw new Error('浏览器连接配置无效。');endpoint='http://127.0.0.1:'+port;}
  const url=new URL(endpoint);
  if(!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||url.username||url.password||!['http:','ws:'].includes(url.protocol))throw new Error('仅使用本机 bb-browser 连接。');
  let address=endpoint;
  if(url.protocol==='http:'){
    const response=await fetch(new URL('/json/version',url),{signal:AbortSignal.timeout(5000),redirect:'error'});
    if(!response.ok)throw new Error('浏览器连接不可用。');address=(await response.json()).webSocketDebuggerUrl;
  }
  const wsURL=new URL(address);
  if(wsURL.protocol!=='ws:'||!['127.0.0.1','localhost','[::1]'].includes(wsURL.hostname))throw new Error('浏览器返回了非本机连接。');
  socket=new WebSocket(wsURL);await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('浏览器连接超时。')),5000);socket.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});socket.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('浏览器连接失败。'));},{once:true});});
  let serial=0;const pending=new Map();
  socket.addEventListener('message',event=>{const data=JSON.parse(event.data),entry=pending.get(data.id);if(!entry)return;pending.delete(data.id);clearTimeout(entry.timer);data.error?entry.reject(new Error(data.error.message)):entry.resolve(data.result);});
  function send(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++serial;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('按键发送超时；不要自动重发。'));},8000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  await send('Page.bringToFront',{},sessionId);
  await send('Emulation.setFocusEmulationEnabled',{enabled:true},sessionId);
  try{
    const base={key,code,windowsVirtualKeyCode:virtual,nativeVirtualKeyCode:virtual,modifiers};
    await send('Input.dispatchKeyEvent',{...base,type:text?'keyDown':'rawKeyDown',text,unmodifiedText:text},sessionId);
    await send('Input.dispatchKeyEvent',{...base,type:'keyUp'},sessionId);
  }finally{
    await send('Emulation.setFocusEmulationEnabled',{enabled:false},sessionId).catch(()=>{});
    await send('Target.detachFromTarget',{sessionId}).catch(()=>{});
  }
  console.log(JSON.stringify({result:{tabId:targetId,action_dispatched:true,input:'cdp-keyboard',business_outcome:'not_checked'}}));
}catch(error){console.error(error.message);process.exitCode=1;}
finally{socket?.close();}
