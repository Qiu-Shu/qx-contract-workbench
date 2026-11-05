const fs=require('node:fs'),path=require('node:path');
// Electron can outlive its launching shell; progress must not depend on its pipe.
function createProgressLog(file){
 fs.mkdirSync(path.dirname(file),{recursive:true});
 return value=>fs.appendFileSync(file,JSON.stringify({time:new Date().toISOString(),...value})+'\n');
}
module.exports={createProgressLog};
