const fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const {pathToFileURL}=require('node:url'),{registerHooks}=require('node:module');
require('./network-policy.cjs').install({log:process.env.QX_EVAL_NETWORK_LOG,python:process.env.QX_TEST_PYTHON});
// MIT Promptfoo 0.125.1: scoped, hash-checked adaptations in memory; node_modules stays unchanged.
const patches=[
 {file:'telemetry-CIqy4fSC.js',sha:'36250d9ae7dfb037e357d0c1b0cbde8922b91d5225292743fadf4596a4a9a24d',event:'telemetry_patch',
  before:'if (this.disabled) this.recordTelemetryDisabled();',after:'if (this.disabled) return;'},
 // Do not start tsx/its parent IPC client while probing a nonexistent optional TypeScript config.
 {file:'main.js',sha:'df6d75a365d37d01d948afc48434bcd18e28f466f82552c00dfeb3878a60e4bd',event:'config_probe_patch',
  before:'await ensureTypescriptLoader(configPath);\n\t\tif (!await pathExists$1(configPath)) return;',
  after:'if (!await pathExists$1(configPath)) return;\n\t\tawait ensureTypescriptLoader(configPath);'}
];
for(const patch of patches){
 const file=path.join(__dirname,'node_modules/promptfoo/dist/src',patch.file);
 if(createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==patch.sha)throw Error('Promptfoo source changed; review the pinned patch before evaluation: '+patch.file);
 patch.url=pathToFileURL(file).href;
}
registerHooks({load(url,context,nextLoad){
 const result=nextLoad(url,context);
 const patch=patches.find(p=>p.url===url);if(!patch)return result;
 const source=Buffer.from(result.source).toString('utf8');
 if(createHash('sha256').update(source).digest('hex')!==patch.sha||source.split(patch.before).length!==2)throw Error('Promptfoo patch site changed');
 fs.appendFileSync(process.env.QX_EVAL_NETWORK_LOG,JSON.stringify({event:patch.event,pid:process.pid,sourceSha256:patch.sha})+'\n');
 return {...result,source:source.replace(patch.before,patch.after)};
}});
