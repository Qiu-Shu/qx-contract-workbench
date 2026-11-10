import {spawn} from 'node:child_process';

export function runComponent(command,args,{signal,timeout=360000,onProgress=()=>{}}={}){
  signal?.throwIfAborted();
  return new Promise((resolve,reject)=>{
    const child=spawn(command,args,{windowsHide:true,stdio:['ignore','pipe','pipe'],signal});
    let buffer='',stdout='',failure;
    const timer=setTimeout(()=>{failure=Object.assign(Error('组件准备超时'),{code:'TIMEOUT'});child.kill()},timeout);
    const line=value=>{
      try{const event=JSON.parse(value);if(event.type==='progress')onProgress(event);else stdout=value}
      catch{failure=Error('组件进度响应无效');child.kill()}
    };
    child.stdout.setEncoding('utf8');child.stderr.resume();
    child.stdout.on('data',chunk=>{
      buffer+=chunk;if(buffer.length>65536){failure=Error('组件响应超过限制');child.kill();return}
      let end;while((end=buffer.indexOf('\n'))>=0){const value=buffer.slice(0,end).trim();buffer=buffer.slice(end+1);if(value)line(value)}
    });
    child.on('error',error=>{failure=error});
    child.on('close',code=>{
      clearTimeout(timer);if(buffer.trim())line(buffer.trim());
      if(failure||code!==0)return reject(Object.assign(failure||Error('组件准备失败'),{stdout}));
      resolve({stdout});
    });
  });
}
