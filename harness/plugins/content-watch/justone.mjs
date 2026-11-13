const ORIGIN='https://api.justoneapi.com';
const SEARCH='/api/xiaohongshu/search-note/v4';
const DETAIL='/api/xiaohongshu/get-note-detail/v1';
const WEEK=7*24*60*60*1000;
const MAX_BYTES=4*1024*1024;
const messages={
  TOKEN_REQUIRED:'请先保存 JustOneAPI Token。',
  TOKEN_INVALID:'JustOneAPI Token 无效或尚未启用，请检查后重试。',
  RATE_LIMIT:'JustOneAPI 暂时限流，本轮已停止，请稍后手动重试。',
  QUOTA_EXCEEDED:'JustOneAPI 今日调用额度已用完，本轮已停止。',
  API_PERMISSION:'当前 JustOneAPI Token 没有此接口权限。',
  BUDGET_EXCEEDED:'JustOneAPI 账户余额或 Token 预算不足，本轮已停止。',
  PROVIDER_UNAVAILABLE:'JustOneAPI 采集暂不可用，本轮已停止，请稍后手动重试。',
};
const errorFor=(code='PROVIDER_UNAVAILABLE')=>Object.assign(new Error(messages[code]),{code});
const providerCodes={100:'TOKEN_INVALID',302:'RATE_LIMIT',303:'QUOTA_EXCEEDED',600:'API_PERMISSION',601:'BUDGET_EXCEEDED',602:'BUDGET_EXCEEDED'};
const cancelled=()=>new DOMException('已停止小红书采集。','AbortError');
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const clean=(value,max=1000)=>typeof value==='string'?value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').trim().slice(0,max):'';

function keywordsFor({practice,targetClients}={}){
  const topics=clean(practice,300).split(/[、，,；;\n/]+/).map(value=>value.trim().slice(0,35)).filter(Boolean).slice(0,2);
  const target=clean(targetClients,120).split(/[、，,；;\n/]+/).find(value=>value.trim())?.trim().slice(0,35);
  if(!topics.length||!target)throw new Error('请先填写业务方向和目标客户。');
  return [...new Set(topics.length>1?topics.map(topic=>topic+' '+target):[topics[0],topics[0]+' '+target])];
}

export function createJustOneClient({token='',fetchImpl=fetch,clock=Date.now,timeoutMs=90000}={}){
  async function readToken(signal){
    if(signal?.aborted)throw cancelled();
    let value;
    try{value=typeof token==='function'?await token():token;}catch{throw signal?.aborted?cancelled():errorFor('TOKEN_REQUIRED');}
    if(signal?.aborted)throw cancelled();
    if(typeof value!=='string'||!value.trim()||value.length>4096||/[\u0000-\u001f\u007f]/.test(value))throw errorFor('TOKEN_REQUIRED');
    return value.trim();
  }
  async function request(path,params,accessToken,signal){
    if(signal?.aborted)throw cancelled();
    try{
      const url=new URL(path,ORIGIN);
      url.search=new URLSearchParams({...params,token:accessToken}).toString();
      const response=await fetchImpl(url.href,{method:'GET',redirect:'error',headers:{accept:'application/json'},
        signal:signal?AbortSignal.any([signal,AbortSignal.timeout(timeoutMs)]):AbortSignal.timeout(timeoutMs)});
      if(response.redirected)throw errorFor();
      const reader=response.body?.getReader();if(!reader)throw errorFor();
      let bytes=0;const chunks=[];
      try{
        while(true){
          if(signal?.aborted){await reader.cancel();throw cancelled();}
          const {done,value}=await reader.read();if(done)break;
          bytes+=value.byteLength;if(bytes>MAX_BYTES){await reader.cancel();throw errorFor();}
          chunks.push(value);
        }
      }finally{reader.releaseLock();}
      if(signal?.aborted)throw cancelled();
      const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if(!object(value))throw errorFor();
      if(value.code!==0)throw errorFor(providerCodes[value.code]||'PROVIDER_UNAVAILABLE');
      if(!response.ok||(!object(value.data)&&!Array.isArray(value.data)))throw errorFor();
      return value.data;
    }catch(error){
      if(signal?.aborted)throw cancelled();
      if(Object.hasOwn(messages,error?.code))throw errorFor(error.code);
      throw errorFor();
    }
  }
  async function checkLogin({signal}={}){await readToken(signal);return {loggedIn:true,verified:false};}
  async function collect(profile,{signal,seenIds=[]}={}){
    const accessToken=await readToken(signal),keywords=keywordsFor(profile);
    const now=clock(),seen=new Set(seenIds),records=new Map(),streams=[];
    const warnings=['本期为近一周关键词搜索的精选样本，不代表全平台完整榜单；互动指标为采集时快照。'];
    for(const keyword of keywords){
      for(const sortType of ['popularity_descending','time_descending']){
        const stream=[];streams.push(stream);
        const data=await request(SEARCH,{keyword,page:'1',sortType,timeFilter:'ONE_WEEK',noteType:'ALL'},accessToken,signal);
        if(!Array.isArray(data.notes))throw errorFor();
        let recognized=data.notes.length===0;
        for(const card of data.notes.slice(0,100)){
          const record=searchRecord(card,keyword,now);
          if(record||['live','live_v2'].includes(card?.type))recognized=true;
          if(!record||seen.has(record.id)||old(record,now))continue;
          if(records.has(record.id))records.get(record.id).keywords.add(keyword);
          else records.set(record.id,record);
          if(!stream.includes(record.id))stream.push(record.id);
        }
        if(!recognized)throw errorFor();
      }
    }
    // Give each keyword and sort order a turn, including target-client searches, within the sample limit.
    const selected=[],ids=new Set();
    while(selected.length<20&&streams.some(stream=>stream.length)){
      for(const stream of streams){
        while(stream.length&&ids.has(stream[0]))stream.shift();
        const id=stream.shift();
        if(id){ids.add(id);selected.push(records.get(id));}
        if(selected.length===20)break;
      }
    }
    for(const record of selected.slice(0,6)){
      const data=await request(DETAIL,{noteId:record.id},accessToken,signal);
      const note=detailNote(data,record.id);
      if(note){record.note={...record.note,...note};record.fullText=Boolean(clean(note.desc,16000));}
      else warnings.push('部分笔记正文未能读取，仅保留标题简介。');
    }
    const items=selected.map(record=>normalize(record,now)).filter(item=>!old(item,now));
    if(items.some(item=>!item.publishedAt))warnings.push('部分笔记未取得可核验的发布时间，近一周范围仅依据上游搜索筛选，时间待核实。');
    if(items.some(item=>item.textCoverage!=='正文'))warnings.push('部分内容仅读取标题简介；视频未进行语音转写。');
    return {items,warnings:[...new Set(warnings)]};
  }
  return {checkLogin,collect};
}

function metric(value){
  if(typeof value==='number')return Number.isSafeInteger(value)&&value>=0?value:null;
  if(typeof value!=='string')return null;
  const match=/^(\d+(?:\.\d+)?)\s*(万|亿|千|[kKmM])?\+?$/.exec(value.trim().replace(/,/g,''));
  if(!match)return null;
  const count=Math.round(Number(match[1])*({'万':10000,'亿':100000000,'千':1000,k:1000,K:1000,m:1000000,M:1000000}[match[2]]||1));
  return Number.isSafeInteger(count)&&count>=0?count:null;
}
function published(value,now){
  if(value===null||value===undefined||value==='')return null;
  let ms;
  if(typeof value==='number'||/^\d{10,13}$/.test(String(value)))ms=Number(value)<100000000000?Number(value)*1000:Number(value);
  else if(typeof value==='string'&&/^\d{4}-\d{2}-\d{2}(?:T|\s|$)/.test(value))ms=Date.parse(value);
  if(!Number.isFinite(ms)||ms<=0||ms>now+24*60*60*1000)return null;
  return new Date(ms).toISOString();
}
const old=(record,now)=>record.publishedAt!==null&&Date.parse(record.publishedAt)<now-WEEK;

// Public examples checked 2026-11-08: docs.justoneapi.com/en/api/xiaohongshu-rednote/note-search-v4
// and note-details-v1. OpenAPI leaves data untyped; unknown search shapes must not look like zero results.
function searchRecord(card,keyword,now){
  if(!object(card)||!['normal','video'].includes(card.type)||(typeof card.title!=='string'&&typeof card.desc!=='string'))return null;
  const id=clean(card.id,128);if(!/^[a-z\d_-]+$/i.test(id))return null;
  return {id,note:card,publishedAt:published(card.timestamp,now),fullText:false,keywords:new Set([keyword])};
}
function detailNote(data,id){
  if(!Array.isArray(data))return null;
  for(const group of data.slice(0,20)){
    if(group?.model_type!=='note'||!Array.isArray(group.note_list))continue;
    const note=group.note_list.slice(0,100).find(item=>object(item)&&item.id===id);
    if(note)return {...note,...(note.time!==undefined?{timestamp:note.time}:{})};
  }
  return null;
}
function normalize({id,note,keywords,fullText},now){
  const title=clean(note.title,300),text=clean(note.desc,16000);
  return {id,title,text:text||title,url:'https://www.xiaohongshu.com/explore/'+encodeURIComponent(id),
    author:clean(note.user?.nickname,160),publishedAt:published(note.timestamp,now),likes:metric(note.liked_count),comments:metric(note.comments_count),
    collected:metric(note.collected_count),shares:metric(note.shared_count),textCoverage:fullText&&text&&note.type!=='video'?'正文':'标题简介',keywords:[...keywords]};
}
