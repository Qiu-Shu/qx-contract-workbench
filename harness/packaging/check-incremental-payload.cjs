const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {createHash}=require('node:crypto');
const {SEVEN_ZIP}=require('./hdiffpatch-tools.cjs');
function list(exe){
  // The incremental bootstrap can put the embedded archive beyond the default scan window.
  const output=execFileSync(SEVEN_ZIP,['l','-t7z:s32m','-slt','-sccUTF-8',exe],{windowsHide:true,encoding:'utf8',maxBuffer:32*1024*1024});
  const records=new Map();
  for(const block of output.slice(output.indexOf('----------')).split(/\r?\n\r?\n/)){
    const fields=Object.fromEntries(block.split(/\r?\n/).filter(line=>line.includes(' = ')).map(line=>{const i=line.indexOf(' = ');return [line.slice(0,i),line.slice(i+3)];}));
    if(fields.Path&&fields.Size!==undefined&&!fields.Attributes?.startsWith('D'))records.set(fields.Path.replaceAll('\\','/'),{size:Number(fields.Size),crc:fields.CRC});
  }
  return records;
}
const oldExe=path.resolve(process.argv[2]),release=path.resolve(process.argv[3]);
const plan=JSON.parse(fs.readFileSync(path.join(release,'incremental/plan.json'),'utf8'));
const nextExe=path.join(release,'Qunxing-Workbench-'+plan.toVersion+'-Setup.exe');
const oldFiles=list(oldExe),newFiles=list(nextExe),changes=new Set(plan.changes.map(c=>c.path));
assert.equal(oldFiles.size,plan.stats.oldFiles);assert.equal(newFiles.size,plan.stats.newFiles);
let unchanged=0;
for(const [name,info] of oldFiles)if(!changes.has(name)){assert.deepEqual(newFiles.get(name),info,name);unchanged++;}
for(const name of newFiles.keys())assert.ok(oldFiles.has(name)||changes.has(name),name);
const out=fs.mkdtempSync(path.resolve(__dirname,'../.local/install-speed-check/payload-'));
const requested=plan.changes.filter(c=>c.newSha256);
const files=path.join(out,'members.txt');fs.writeFileSync(files,requested.map(c=>c.path).join('\n'));
execFileSync(SEVEN_ZIP,['x','-t7z:s32m',nextExe,'-o'+out,'-y','-bso0','-bsp0','-scsUTF-8','@'+files],{windowsHide:true,stdio:'pipe'});
for(const change of requested){const digest=createHash('sha256').update(fs.readFileSync(path.join(out,change.path))).digest('hex');assert.equal(digest,change.newSha256,change.path);}
const report={passed:true,oldArchiveFiles:oldFiles.size,newArchiveFiles:newFiles.size,unchangedArchiveCrcAndSizeMatches:unchanged,changedFileHashesExtractedFromFinalExe:requested.length};
fs.writeFileSync(path.join(release,'payload-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
