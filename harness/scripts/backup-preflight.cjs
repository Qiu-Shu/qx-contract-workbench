const {prepareBackup}=require('../desktop/backup-preparation.cjs');
async function main(args=process.argv.slice(2)){
  if(args.length!==2||args[0]!=='--data')throw Object.assign(Error('Use --data <absolute installed data directory>'),{code:'BACKUP_USAGE'});
  const report=await prepareBackup(args[1]);
  // Filenames, contents and credentials never go to the command log.
  console.log(JSON.stringify({mode:report.mode,backupComplete:false,scopeReviewRequired:report.scopeReviewRequired,
    fileCount:report.fileCount,bytes:report.bytes,scopeCounts:report.scopes.reduce((counts,s)=>{
      counts[s.policy]=(counts[s.policy]||0)+1;return counts;
    },{})}));
}
if(require.main===module)main().catch(error=>{
  console.error(/^BACKUP_[A-Z_]+$/.test(error.code||'')?error.code:'BACKUP_PREPARATION_FAILED');process.exitCode=1;
});
module.exports={main};
