import './network-guard.mjs';
import {appendFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createContentWatch} from '../../plugins/content-watch/core.mjs';
import {profile} from './fixture.mjs';

const [stateDir,phase]=process.argv.slice(2);
const service=await createContentWatch({stateDir,client:{checkLogin:async()=>({loggedIn:true}),collect:async()=>({items:[{id:'crash-note',title:'合成中断样本',text:'虚构内容'}]})},
  deliver:async report=>{
    if(phase==='submitted'){
      await report.onSubmitting({messageId:'uncertain-synthetic-message'});
      await appendFile(join(stateDir,'accepted.jsonl'),JSON.stringify({id:report.id})+'\n');
    }
    console.log('CRASH_BOUNDARY_READY');await new Promise(()=>{});
  }});
await service.saveProfile(profile);
setInterval(()=>{},1000);
await service.run();
