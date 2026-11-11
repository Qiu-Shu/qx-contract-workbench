import {isIP} from 'node:net';

export class LoginRequiredError extends Error {
  constructor(){super('小红书登录已失效，请重新扫码连接。');this.code='LOGIN_REQUIRED';}
}
const unavailable=()=>Object.assign(new Error('小红书连接组件暂时不可用，请检查连接或重新准备组件。'),{code:'COMPONENT_UNAVAILABLE'});
const cancelled=()=>new DOMException('已停止小红书采集。','AbortError');
const clean=(value,max=1000)=>typeof value==='string'?value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').trim().slice(0,max):'';
const loginFailure=value=>/未登录|需要登录|请先登录|登录(?:已)?(?:失效|过期)|重新(?:扫码|登录)|login[_ ]required|not[_ ]logged[_ ]in|session[_ ]expired/i.test(value);

export function localServiceUrl(value='http://127.0.0.1:18060'){
  let url;try{url=new URL(value);}catch{throw new Error('请配置有效的本机小红书组件地址。');}
  const host=url.hostname.replace(/^\[|\]$/g,'');
  if(url.protocol!=='http:'||!url.port||!(host==='localhost'||host==='::1'||(isIP(host)===4&&host.startsWith('127.')))||
    url.username||url.password||url.search||url.hash||!['','/'].includes(url.pathname))throw new Error('小红书组件仅支持本机 HTTP 地址。');
  return url.origin;
}

function metric(value){
  if(typeof value==='number')return Number.isSafeInteger(value)&&value>=0?value:null;
  if(typeof value!=='string'||!value.trim())return null;
  const match=/^(\d+(?:\.\d+)?)\s*(万|亿|千|[kKmM])?\+?$/.exec(value.trim().replace(/,/g,''));
  if(!match)return null;
  const factor={'万':10000,'亿':100000000,'千':1000,k:1000,K:1000,m:1000000,M:1000000}[match[2]]||1;
  const count=Math.round(Number(match[1])*factor);
  return Number.isSafeInteger(count)&&count>=0?count:null;
}
function published(value){
  if(value===null||value===undefined||value==='')return null;
  const ms=typeof value==='number'?(value<100000000000?value*1000:value):(/^\d{10,13}$/.test(String(value))?(Number(value)<100000000000?Number(value)*1000:Number(value)):Date.parse(value));
  const date=new Date(ms);
  return Number.isFinite(ms)&&ms>0&&!Number.isNaN(date.getTime())?date.toISOString():null;
}
function normalize(id,note,keywords){
  const info=note.interactInfo||{};
  const text=clean(note.desc,16000),title=clean(note.title||note.displayTitle,300);
  return {id,title,author:clean(note.user?.nickname||note.user?.nickName,160),publishedAt:published(note.time),
    likes:metric(info.likedCount),comments:metric(info.commentCount),collected:metric(info.collectedCount),shares:metric(info.sharedCount),
    url:'https://www.xiaohongshu.com/explore/'+encodeURIComponent(id),text:text||title,
    textCoverage:text&&note.type!=='video'?'正文':'标题简介',keywords:[...keywords]};
}
function keywordsFor({practice,targetClients}={}){
  const topics=clean(practice,300).split(/[、，,；;\n/]+/).map(value=>value.trim()).filter(Boolean).slice(0,2);
  const target=clean(targetClients,120);
  if(!topics.length||!target)throw new Error('请先填写业务方向和目标客户。');
  return [...new Set([...topics,topics[0]+' '+target].map(value=>value.slice(0,80)))].slice(0,3);
}

export function createXhsClient({baseUrl='http://127.0.0.1:18060',fetchImpl=fetch,timeoutMs=60000,authToken=''}={}){
  const origin=localServiceUrl(baseUrl);
  async function request(path,{body,signal}={}){
    if(signal?.aborted)throw cancelled();
    try{
      const token=typeof authToken==='function'?authToken():authToken;
      const response=await fetchImpl(origin+path,{method:body?'POST':'GET',redirect:'error',
        headers:{accept:'application/json',...(body?{'content-type':'application/json'}:{}),...(token?{authorization:'Bearer '+token}:{})},
        ...(body?{body:JSON.stringify(body)}:{}),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(timeoutMs)]):AbortSignal.timeout(timeoutMs)});
      const reader=response.body?.getReader();if(!reader)throw unavailable();
      let bytes=0;const chunks=[];
      try{
        while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;
          if(bytes>4*1024*1024){await reader.cancel();throw unavailable();}chunks.push(value);}
      }finally{reader.releaseLock();}
      const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if(!value||typeof value!=='object'||Array.isArray(value))throw unavailable();
      if(!response.ok||value.success!==true){
        if(response.status!==401&&loginFailure([value.code,value.error,value.message,typeof value.details==='string'?value.details:''].join(' ')))throw new LoginRequiredError();
        throw unavailable();
      }
      if(!value.data||typeof value.data!=='object'||Array.isArray(value.data))throw unavailable();
      return value.data;
    }catch(error){
      if(signal?.aborted)throw cancelled();
      if(error instanceof LoginRequiredError)throw error;
      throw unavailable();
    }
  }
  async function checkLogin({signal}={}){
    const data=await request('/api/v1/login/status',{signal});
    if(typeof data.is_logged_in!=='boolean')throw unavailable();
    return {loggedIn:data.is_logged_in,...(data.is_logged_in&&clean(data.username,160)?{username:clean(data.username,160)}:{})};
  }
  async function loginQr(){
    const data=await request('/api/v1/login/qrcode');
    if(typeof data.is_logged_in!=='boolean')throw unavailable();
    const img=typeof data.img==='string'?data.img:'';
    if(!data.is_logged_in&&(!/^data:image\/(png|jpeg|webp);base64,[a-z\d+/=\s]+$/i.test(img)||img.length>2*1024*1024))throw unavailable();
    return {img:data.is_logged_in?'':img,...(typeof data.timeout==='string'?{timeout:clean(data.timeout,40)}:{}),isLoggedIn:data.is_logged_in};
  }
  async function requireLogin(signal){if(!(await checkLogin({signal})).loggedIn)throw new LoginRequiredError();}
  async function collect(profile,{signal,seenIds=[]}={}){
    const keywords=keywordsFor(profile);await requireLogin(signal);
    const seen=new Set(seenIds);
    const records=new Map(),warnings=['本期为近期搜索结果的精选样本，不代表全平台完整榜单。'];
    for(const keyword of keywords){
      let data;
      try{data=await request('/api/v1/feeds/search',{body:{keyword,filters:{sort_by:'最多点赞',publish_time:'一周内'}},signal});}
      catch(error){if(error.code==='COMPONENT_UNAVAILABLE')await requireLogin(signal);throw error;}
      if(!Array.isArray(data.feeds))throw unavailable();
      for(const card of data.feeds.slice(0,20)){
        if(!card||typeof card!=='object')continue;
        const id=clean(card.id,128);
        if(card.modelType!=='note'||!id||seen.has(id)||!/^[a-z\d_-]+$/i.test(id)||!card.noteCard||typeof card.noteCard!=='object')continue;
        if(records.has(id)){records.get(id).keywords.add(keyword);continue;}
        records.set(id,{id,note:card.noteCard,xsecToken:typeof card.xsecToken==='string'?card.xsecToken:'',keywords:new Set([keyword])});
      }
    }
    const selected=[...records.values()].sort((a,b)=>(metric(b.note.interactInfo?.likedCount)??-1)-(metric(a.note.interactInfo?.likedCount)??-1)).slice(0,20);
    for(const record of selected.slice(0,6)){
      if(!record.xsecToken){warnings.push('部分笔记缺少详情读取凭据，仅保留标题简介。');continue;}
      try{
        const detail=await request('/api/v1/feeds/detail',{body:{feed_id:record.id,xsec_token:record.xsecToken,load_all_comments:false},signal});
        const note=detail.data?.note;
        if(!note||typeof note!=='object'||note.noteId!==record.id)throw unavailable();
        record.note={...record.note,...note};
      }catch(error){
        if(error instanceof LoginRequiredError||error.name==='AbortError')throw error;
        await requireLogin(signal);
        warnings.push('部分笔记正文未能读取，仅保留标题简介。');
      }
    }
    await requireLogin(signal);
    return {items:selected.map(record=>normalize(record.id,record.note,record.keywords)),warnings:[...new Set(warnings)]};
  }
  return {checkLogin,loginQr,collect};
}
