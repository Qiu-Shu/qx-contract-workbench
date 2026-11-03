// Synthetic background used only to test NSIS process cleanup and data retention.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {randomBytes}=require('node:crypto');
const data=process.env.QX_INSTALL_DATA;
if(!data||!data.includes('installer-check-'))process.exit(1);
const token=randomBytes(32).toString('hex');
fs.mkdirSync(path.join(data,'.local'),{recursive:true});
const server=http.createServer((req,res)=>{
  if(req.method!=='POST'||req.url!=='/stop'||req.headers.authorization!==`Bearer ${token}`){res.writeHead(403).end();return;}
  fs.writeFileSync(path.join(data,'background-stopped.txt'),'authenticated stop');
  res.writeHead(200).end();setTimeout(()=>process.exit(0),100);
});
server.listen(0,'127.0.0.1',()=>fs.writeFileSync(path.join(data,'.local/runtime.json'),JSON.stringify({launcherPid:process.pid,hostPid:process.pid,controlUrl:`http://127.0.0.1:${server.address().port}/stop`,controlToken:token})));
