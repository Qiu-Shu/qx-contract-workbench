const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createProgressLog}=require('./skill-eval-log.cjs');
test('evaluation progress survives closed console pipes and remains readable',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qx-eval-log-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const file=path.join(dir,'run/progress.jsonl'),log=createProgressLog(file);
 const stdout=process.stdout.write,stderr=process.stderr.write;
 const closed=()=>{throw Object.assign(Error('broken pipe, write'),{code:'EPIPE'});};
 try {process.stdout.write=closed;process.stderr.write=closed;log({status:'completed',id:'synthetic'});log({status:'failed',error:'synthetic failure'});}
 finally{process.stdout.write=stdout;process.stderr.write=stderr;}
 const rows=fs.readFileSync(file,'utf8').trim().split('\n').map(JSON.parse);
 assert.deepEqual(rows.map(r=>r.status),['completed','failed']);assert.equal(rows[0].id,'synthetic');
});
