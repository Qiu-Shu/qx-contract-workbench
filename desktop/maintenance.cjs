const {spawn}=require('node:child_process');
const {randomBytes}=require('node:crypto');

class Maintenance {
  constructor(executable,args){this.executable=executable;this.args=args;}
  run(config){
    const nonce=randomBytes(16).toString('hex');
    return new Promise((resolve,reject)=>{
      let buffer='',result=null,settled=false;
      const finish=(error)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(result);};
      const timer=setTimeout(()=>{finish(new Error('MAINTENANCE_TIMEOUT'));void this.stop();},10*60*1000);
      this.child=spawn(this.executable,this.args,{windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8'}});
      this.exited=new Promise(done=>this.child.once('close',code=>{done();finish(code===0&&result?null:new Error('MAINTENANCE_FAILED'));}));
      this.child.once('error',()=>finish(new Error('MAINTENANCE_FAILED')));
      this.child.stdin.on('error',()=>finish(new Error('MAINTENANCE_FAILED')));
      this.child.stderr.resume();this.child.stdout.setEncoding('utf8');
      this.child.stdout.on('data',chunk=>{
        buffer+=chunk;
        if(buffer.length>16384){finish(new Error('MAINTENANCE_FAILED'));void this.stop();return;}
        const end=buffer.indexOf('\n');if(end<0)return;
        try{
          const message=JSON.parse(buffer.slice(0,end));buffer=buffer.slice(end+1);
          if(message.event==='error')throw new Error(message.code);
          if(message.event!=='complete'||message.nonce!==nonce||!message.report)throw new Error('MAINTENANCE_FAILED');
          result=message.report;
        }catch(error){finish(error);void this.stop();}
      });
      this.child.stdin.write(JSON.stringify({...config,nonce})+'\n');
    });
  }
  async stop(){
    if(!this.child)return;
    this.child.stdin.end();
    const timer=setTimeout(()=>this.child.kill(),17000);
    await this.exited;clearTimeout(timer);
  }
}
module.exports={Maintenance};
