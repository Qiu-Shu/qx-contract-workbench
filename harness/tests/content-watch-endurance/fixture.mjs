import assert from 'node:assert/strict';
import http from 'node:http';
import {appendFile,readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createJustOneClient} from '../../plugins/content-watch/justone.mjs';

export const profile={practice:'合成劳动争议',targetClients:'合成企业负责人',enabled:true};
export async function createFixture(directory,{clock=Date.now}={}){
  const requests=[],receipts=[];let generation=1,outage=false,fixtureError=null;
  const ledger=join(directory,'summary-receipts.jsonl');
  try{receipts.push(...(await readFile(ledger,'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse));}catch(error){if(error.code!=='ENOENT')throw error;}
  const note=id=>({id,title:'合成劳动争议 '+id,desc:'独立虚构的拓客耐久验证样本。',type:'normal',user:{nickname:'合成作者'},
    timestamp:Math.floor(clock()/1000),time:Math.floor(clock()/1000),liked_count:88,comments_count:9,collected_count:12,shared_count:1});
  const server=http.createServer(async(req,res)=>{
    try{
      const url=new URL(req.url,'http://127.0.0.1');
      if(url.pathname==='/summary'){
        assert.equal(req.method,'POST');let raw='';for await(const chunk of req){raw+=chunk;assert.ok(raw.length<200000);}
        const report=JSON.parse(raw);assert.ok(report.id);assert.ok(report.items.length);
        const receipt={id:report.id,itemIds:report.items.map(item=>item.id),at:new Date().toISOString(),content:'合成本机摘要；不提供法律结论。'};
        await appendFile(ledger,JSON.stringify(receipt)+'\n');receipts.push(receipt);
        res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({content:receipt.content}));return;
      }
      assert.equal(req.method,'GET');assert.equal(url.searchParams.get('token'),'endurance-synthetic-only');
      const kind=url.pathname.endsWith('search-note/v4')?'search':'detail';
      requests.push({kind,at:new Date().toISOString(),generation,outage});
      if(outage){req.socket.destroy();return;}
      let data;
      if(kind==='search'){
        assert.equal(url.pathname,'/api/xiaohongshu/search-note/v4');assert.equal(url.searchParams.get('timeFilter'),'ONE_WEEK');
        data={notes:Array.from({length:generation},(_,index)=>note('endurance-note-'+(index+1)))};
      }else{assert.equal(url.pathname,'/api/xiaohongshu/get-note-detail/v1');data=[{model_type:'note',note_list:[note(url.searchParams.get('noteId'))]}];}
      res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({code:0,data}));
    }catch(error){fixtureError=error.message;res.writeHead(500);res.end('synthetic fixture rejected request');}
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const origin='http://127.0.0.1:'+server.address().port;
  const client=createJustOneClient({token:'endurance-synthetic-only',clock,timeoutMs:3000,fetchImpl(url,options){
    const target=new URL(url);assert.equal(target.origin,'https://api.justoneapi.com');
    return fetch(new URL(target.pathname+target.search,origin),options);
  }});
  const deliver=async report=>{
    await report.onSubmitting({messageId:'synthetic-'+report.id});
    const response=await fetch(origin+'/summary',{method:'POST',body:JSON.stringify({id:report.id,items:report.items}),signal:AbortSignal.timeout(5000)});
    assert.equal(response.status,200);return response.json();
  };
  return {client,deliver,requests,receipts,origin,
    setGeneration(value){assert.ok(value>=1&&value<=6);generation=value;},setOutage(value){outage=value;},
    counts(){return {searches:requests.filter(row=>row.kind==='search').length,details:requests.filter(row=>row.kind==='detail').length,summaries:receipts.length};},
    assertHealthy(){assert.equal(fixtureError,null);},
    async close(){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));},
  };
}
