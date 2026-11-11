import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const tick=()=>new Promise(resolve=>setImmediate(resolve));
const ready={profile:{practice:'劳动用工',targetClients:'中小企业负责人'},enabled:true,nextRunAt:'2026-11-08T04:00:00Z',lastRunAt:null,status:'ready',message:'',sessionId:'content-session',lastReport:null,login:{loggedIn:true,username:'虚构测试账号'},connection:{provider:'local-xhs',tokenConfigured:false},scriptPending:false};
const apiReady={...ready,connection:{provider:'justone',tokenConfigured:true},login:null};
const nodes=(node)=>!node||typeof node!=='object'?[]:[node,...node.children.flatMap(nodes)];
const text=node=>typeof node==='string'?node:!node||typeof node!=='object'?'':node.children.map(text).join('');
const find=(tree,predicate)=>nodes(tree).find(predicate);
const button=(tree,label)=>find(tree,node=>node.type==='button'&&text(node)===label);

// Exercise component events and hook lifetimes without substituting a browser for a real one.
function hooks(){
  let active;
  const React={
    createElement(type,props,...children){return {type,props:props||{},children:children.flat(Infinity).filter(x=>x!==false&&x!==null&&x!==undefined)};},
    useState(initial){const i=active.cursor++,owner=active;if(!(i in owner.values))owner.values[i]=typeof initial==='function'?initial():initial;return [owner.values[i],value=>{owner.values[i]=typeof value==='function'?value(owner.values[i]):value;}];},
    useRef(initial){const i=active.cursor++;if(!(i in active.values))active.values[i]={current:initial};return active.values[i];},
    useEffect(effect,deps){const i=active.cursor++,owner=active,previous=owner.effects[i];if(!previous||deps.some((value,n)=>value!==previous.deps[n]))owner.pending.push(()=>{previous?.cleanup?.();owner.effects[i]={deps,cleanup:effect()};});},
  };
  return {React,instance(component,props={}){const owner={values:[],effects:[],pending:[],cursor:0};return {
    render(){active=owner;owner.cursor=0;const tree=component(props);active=null;for(const effect of owner.pending.splice(0))effect();return tree;},
    unmount(){for(const effect of owner.effects)effect?.cleanup?.();},
  };}};
}

async function fixture(t,{status=ready,respond}={}){
  const requests=[],timers=new Map(),links=[],opened=[],h=hooks();let entry,serial=0;
  const fetch=async(url,options={})=>{
    requests.push({url,options});
    if(options.headers?.['x-qx-content-watch']!=='1')return Response.json({error:'需要工作台访问标识。'},{status:403});
    const result=respond?await respond(url,options,requests):status;
    return result instanceof Response?result:new Response(JSON.stringify(result),{headers:{'content-type':'application/json'}});
  };
  const document={visibilityState:'visible',createElement:()=>({remove(){this.removed=true;}}),head:{append:link=>links.push(link)}};
  const window={};
  const sandbox={window,document,fetch,AbortController,console,setInterval:fn=>{const id=++serial;timers.set(id,fn);return id;},clearInterval:id=>timers.delete(id)};
  vm.runInNewContext(await readFile(new URL('./client.js',import.meta.url),'utf8'),sandbox);
  const ctx={uiWorkspace:{openSession:id=>opened.push(id)},slots:{inject(_slot,install){install();return()=>{entry=null;};},register(_details,component){entry=component;return()=>{};}}};
  const dispose=window.qxInstallContentWatch(ctx,h.React);t.after(dispose);
  const entryView=h.instance(entry,{wide:true});let tree=entryView.render();
  button(tree,'拓客内容').props.onClick();tree=entryView.render();
  const panelNode=find(tree,node=>typeof node.type==='function');assert.ok(panelNode);
  const panel=h.instance(panelNode.type,panelNode.props);tree=panel.render();await tick();tree=panel.render();
  t.after(()=>panel.unmount());
  return {requests,timers,links,opened,panel,dispose,render:()=>panel.render(),get tree(){return tree;}};
}

test('first setup requires both lawyer fields and saves one authorized request despite rapid double submit',async t=>{
  let release;
  const f=await fixture(t,{respond:async(url,options)=>options.method==='POST'?new Promise(resolve=>{release=()=>resolve(ready);}):{...ready,profile:null,enabled:false,status:'unconfigured',sessionId:null}});
  let tree=f.render(),save=button(tree,'保存并启用');assert.equal(save.props.disabled,true);
  find(tree,node=>node.props['aria-label']==='业务方向').props.onChange({target:{value:'劳动用工'}});
  tree=f.render();assert.equal(button(tree,'保存并启用').props.disabled,true);
  find(tree,node=>node.props['aria-label']==='目标客户').props.onChange({target:{value:'中小企业负责人'}});
  tree=f.render();const form=find(tree,node=>node.type==='form');
  const event={preventDefault(){}};const first=form.props.onSubmit(event);form.props.onSubmit(event);
  const posts=f.requests.filter(r=>r.options.method==='POST');assert.equal(posts.length,1);
  assert.equal(posts[0].options.headers['x-qx-content-watch'],'1');
  assert.deepEqual(JSON.parse(posts[0].options.body),{practice:'劳动用工',targetClients:'中小企业负责人',enabled:true});
  assert.match(text(tree),/每 3 天/);assert.match(text(tree),/当前模型/);release();await first;await tick();
});

test('status polling preserves unsaved lawyer input and is disposed when the panel closes',async t=>{
  const f=await fixture(t);
  let tree=f.render();find(tree,node=>node.props['aria-label']==='业务方向').props.onChange({target:{value:'新业务方向'}});
  assert.equal(f.timers.size,1);await [...f.timers.values()][0]();await tick();tree=f.render();
  assert.equal(find(tree,node=>node.props['aria-label']==='业务方向').props.value,'新业务方向');
  assert.ok(f.requests.filter(r=>r.url.endsWith('/status')).every(r=>r.options.headers['x-qx-content-watch']==='1'));
  f.panel.unmount();assert.equal(f.timers.size,0);
  assert.ok(f.requests.every(r=>r.options.signal?.aborted));
});

test('expired login offers a new QR and accepts only a bounded PNG/JPEG data source',async t=>{
  const expired={...ready,status:'login_required',login:{loggedIn:false},message:'登录已过期，请重新扫码'};
  const f=await fixture(t,{respond:async(url,options)=>options.method==='POST'?{...expired,qr:{img:'https://attacker.invalid/track',timeout:'60'}}:expired});
  let tree=f.render();assert.match(text(tree),/重新扫码/);
  await button(tree,'重新扫码').props.onClick();await tick();tree=f.render();
  assert.equal(find(tree,node=>node.type==='img'),undefined);assert.match(text(tree),/二维码暂时无法显示/);
  const post=f.requests.find(r=>r.options.method==='POST');assert.deepEqual(JSON.parse(post.options.body),{action:'login'});
});

test('a safe QR renders as an image and connection confirmation is explicit',async t=>{
  const img='data:image/png;base64,iVBORw0KGgo=';
  const expired={...ready,status:'login_required',login:{loggedIn:false}};
  const f=await fixture(t,{respond:async(url,options)=>options.method==='POST'?{...expired,qr:{img,timeout:'60'}}:expired});
  await button(f.render(),'重新扫码').props.onClick();await tick();let tree=f.render();
  assert.equal(find(tree,node=>node.type==='img').props.src,img);
  await button(tree,'我已扫码，检查连接').props.onClick();await tick();
  assert.deepEqual(JSON.parse(f.requests.at(-1).options.body),{action:'check-login'});
});

test('reports are plain text and opening the dedicated session uses the resident workspace API',async t=>{
  const malicious='<img src=x onerror=alert(1)>';
  const f=await fixture(t,{status:{...ready,lastReport:{id:'report',title:malicious,createdAt:'2026-11-05T04:00:00Z',content:malicious}}});
  let tree=f.render();assert.match(text(tree),/onerror/);
  assert.equal(nodes(tree).some(n=>n.props.dangerouslySetInnerHTML),false);
  await button(tree,'查看整理会话').props.onClick();assert.deepEqual(f.opened,['content-session']);
});

test('pause, resume and manual collection map to distinct actions and errors stay visible',async t=>{
  let state=ready;
  const f=await fixture(t,{respond:async(url,options)=>{
    if(options.method==='POST')state={...state,enabled:JSON.parse(options.body).action==='resume',status:JSON.parse(options.body).action==='pause'?'paused':'ready'};
    return state;
  }});
  await button(f.render(),'暂停整理').props.onClick();await tick();
  await button(f.render(),'恢复整理').props.onClick();await tick();
  await button(f.render(),'立即整理').props.onClick();await tick();
  assert.deepEqual(f.requests.filter(r=>r.options.method==='POST').map(r=>JSON.parse(r.options.body).action),['pause','resume','run']);
});

test('a failed user action remains visible after the next successful status poll',async t=>{
  const f=await fixture(t,{respond:async(url,options)=>options.method==='POST'?Response.json({error:'小红书登录尚未完成，请重新扫码。'},{status:409}):ready});
  await button(f.render(),'立即整理').props.onClick();await tick();
  assert.match(text(f.render()),/小红书登录尚未完成/);
  await [...f.timers.values()][0]();await tick();
  assert.match(text(f.render()),/小红书登录尚未完成/);
});

test('a stale poll failure cannot overwrite a newer successful action',async t=>{
  let gets=0,rejectPoll;
  const f=await fixture(t,{respond:async(url,options)=>{
    if(options.method==='POST')return {...ready,enabled:false,status:'paused'};
    if(++gets===1)return ready;
    return new Promise((_resolve,reject)=>{rejectPoll=reject;});
  }});
  const poll=[...f.timers.values()][0]();
  await button(f.render(),'暂停整理').props.onClick();await tick();
  rejectPoll(Error('旧请求已断开'));await poll;await tick();
  assert.doesNotMatch(text(f.render()),/旧请求已断开/);
  assert.ok(button(f.render(),'恢复整理'));
});

test('new setup defaults to JustOneAPI without QR or local component actions',async t=>{
  const f=await fixture(t,{status:{...ready,connection:undefined,profile:null,login:null,status:'token_required'}});
  const tree=f.render();
  assert.equal(find(tree,node=>node.props['aria-label']==='采集方式').props.value,'justone');
  assert.equal(find(tree,node=>node.props['aria-label']==='JustOneAPI Token').props.type,'password');
  assert.equal(button(tree,'连接小红书'),undefined);assert.equal(button(tree,'准备小红书连接'),undefined);
  assert.equal(button(tree,'立即整理').props.disabled,true);
  assert.match(text(tree),/按调用计费/);assert.match(text(tree),/72 小时/);assert.match(text(tree),/电脑开机/);
});

test('saving an API credential only saves connection and checks local presence, then clears the field',async t=>{
  let state={...apiReady,enabled:false,connection:{provider:'justone',tokenConfigured:false},status:'token_required'};
  const f=await fixture(t,{respond:async(url,options)=>{
    if(url.endsWith('/connection'))state={...state,connection:{provider:'justone',tokenConfigured:true},status:'paused'};
    return state;
  }});
  let tree=f.render();find(tree,node=>node.props['aria-label']==='JustOneAPI Token').props.onChange({target:{value:'synthetic-test-token'}});
  await button(f.render(),'保存连接设置').props.onClick();await tick();tree=f.render();
  const posts=f.requests.filter(r=>r.options.method==='POST');
  assert.deepEqual(posts.map(r=>r.url.split('/').at(-1)),['connection','action']);
  assert.deepEqual(posts.map(r=>JSON.parse(r.options.body)),[{provider:'justone',token:'synthetic-test-token'},{action:'check-login'}]);
  assert.equal(find(tree,node=>node.props['aria-label']==='JustOneAPI Token').props.value,'');
  assert.match(text(tree),/首次整理时验证服务连接/);assert.doesNotMatch(text(tree),/小红书已连接|可以开始整理/);
  assert.ok(button(tree,'恢复整理'));assert.equal(button(tree,'立即整理').props.disabled,false);
});

test('a blank API token preserves the saved credential and polling preserves unsaved connection edits',async t=>{
  const f=await fixture(t,{status:apiReady});
  let tree=f.render();assert.match(find(tree,node=>node.props['aria-label']==='JustOneAPI Token').props.placeholder,/留空保留/);
  await button(tree,'保存连接设置').props.onClick();await tick();
  assert.deepEqual(JSON.parse(f.requests.find(r=>r.url.endsWith('/connection')).options.body),{provider:'justone'});
  tree=f.render();find(tree,node=>node.props['aria-label']==='JustOneAPI Token').props.onChange({target:{value:'synthetic-unsaved-token'}});
  await [...f.timers.values()][0]();await tick();tree=f.render();
  assert.equal(find(tree,node=>node.props['aria-label']==='JustOneAPI Token').props.value,'synthetic-unsaved-token');
  assert.equal(button(tree,'立即整理').props.disabled,true);
  find(tree,node=>node.props['aria-label']==='采集方式').props.onChange({target:{value:'local-xhs'}});
  await [...f.timers.values()][0]();await tick();tree=f.render();
  assert.equal(find(tree,node=>node.props['aria-label']==='采集方式').props.value,'local-xhs');
  assert.equal(button(tree,'连接小红书').props.disabled,true);
});

test('API failures have provider-specific recovery and never ask for a QR scan',async t=>{
  const messages={token_invalid:/更新 Token/,rate_limited:/稍后重试/,quota_exceeded:/检查额度/,budget_exceeded:/余额或 Token 预算不足/,provider_unavailable:/稍后重试/};
  for(const [status,message] of Object.entries(messages)){
    const f=await fixture(t,{status:{...apiReady,status}}),tree=f.render();
    assert.match(text(tree),message);assert.equal(button(tree,'重新扫码'),undefined);assert.equal(button(tree,'连接小红书'),undefined);
    if(status==='token_invalid')assert.equal(button(tree,'立即整理').props.disabled,true);
  }
});

test('saving a local provider preserves the alternative QR flow without starting collection',async t=>{
  let state=apiReady;
  const f=await fixture(t,{respond:async(url,options)=>{
    if(url.endsWith('/connection'))state={...ready,login:{loggedIn:false},status:'login_required'};
    return state;
  }});
  find(f.render(),node=>node.props['aria-label']==='采集方式').props.onChange({target:{value:'local-xhs'}});
  await button(f.render(),'保存连接设置').props.onClick();await tick();
  assert.deepEqual(f.requests.filter(r=>r.options.method==='POST').map(r=>JSON.parse(r.options.body)),[{provider:'local-xhs'},{action:'check-login'}]);
  assert.equal(button(f.render(),'重新扫码').props.disabled,false);
  assert.equal(find(f.render(),node=>node.props['aria-label']==='JustOneAPI Token'),undefined);
});

test('a selected report topic submits only IDs once and opens the dedicated drafting session',async t=>{
  let release;
  const report={id:'report-1',title:'合成报告',createdAt:'2026-11-08T04:00:00Z',items:[{id:'note-1',title:'合成劳动用工选题',url:'https://www.xiaohongshu.com/explore/synthetic'}]};
  const f=await fixture(t,{respond:async(url,options)=>options.method==='POST'?new Promise(resolve=>{release=()=>resolve({...apiReady,lastReport:report,scriptPending:true});}):{...apiReady,lastReport:report}});
  let tree=f.render();assert.match(text(tree),/不代表已读取视频完整口播/);
  const draft=button(tree,'生成口播与拍摄稿');const first=draft.props.onClick();draft.props.onClick();
  const posts=f.requests.filter(r=>r.options.method==='POST');assert.equal(posts.length,1);
  assert.deepEqual(JSON.parse(posts[0].options.body),{action:'draft',reportId:'report-1',itemId:'note-1'});
  assert.equal(button(f.render(),'生成口播与拍摄稿').props.disabled,true);
  release();await first;await tick();assert.deepEqual(f.opened,['content-session']);
  tree=f.render();assert.equal(button(tree,'生成口播与拍摄稿').props.disabled,true);assert.match(text(tree),/正在生成口播与拍摄稿/);
});

test('credential storage describes the actual platform protection without claiming encryption elsewhere',async t=>{
  for(const [secretStorage,expected,unexpected] of [['dpapi',/Windows 系统账号保护/,/本系统未加密/],['restricted-file',/本机受限文件（本系统未加密）/,/Windows 系统账号保护/]]){
    const f=await fixture(t,{status:{...apiReady,connection:{...apiReady.connection,secretStorage}}});
    assert.match(text(f.render()),expected);assert.doesNotMatch(text(f.render()),unexpected);
  }
});

test('local component preparation reports pending work and missing report sessions cannot be opened',async t=>{
  const f=await fixture(t,{respond:async(url,options)=>({...ready,login:{loggedIn:false},status:options.method==='POST'?'running':'unavailable'})});
  assert.equal(button(f.render(),'查看整理会话').props.disabled,true);
  await button(f.render(),'准备小红书连接').props.onClick();await tick();
  assert.match(text(f.render()),/正在准备连接组件/);assert.doesNotMatch(text(f.render()),/已完成连接准备/);
});

test('an unsubmitted saved report retries by ID without API credentials or new collection setup',async t=>{
  const report={id:'saved-report',profile:apiReady.profile,pending:true,submitted:false,title:'已保存来源',items:[]};
  const state={...apiReady,status:'token_invalid',connection:{provider:'justone',tokenConfigured:false},lastReport:report};
  const f=await fixture(t,{status:state});const retry=button(f.render(),'重试整理已保存内容');
  assert.ok(retry);assert.equal(retry.props.disabled,false);
  await retry.props.onClick();await tick();
  const posts=f.requests.filter(r=>r.options.method==='POST');assert.equal(posts.length,1);
  assert.deepEqual(JSON.parse(posts[0].options.body),{action:'run',retryReportId:'saved-report'});
});

test('unsaved lawyer edits block saved-report retry and a different saved profile cannot reuse it',async t=>{
  const report={id:'saved-report',profile:apiReady.profile,pending:true,submitted:false,items:[]};
  let state={...apiReady,status:'error',connection:{provider:'justone',tokenConfigured:false},lastReport:report};
  const f=await fixture(t,{respond:async()=>state});let tree=f.render();
  find(tree,node=>node.props['aria-label']==='业务方向').props.onChange({target:{value:'婚姻家事'}});
  tree=f.render();assert.equal(button(tree,'重试整理已保存内容').props.disabled,true);assert.match(text(tree),/先保存/);
  state={...state,profile:{...apiReady.profile,practice:'婚姻家事'}};
  await [...f.timers.values()][0]();await tick();tree=f.render();
  assert.equal(button(tree,'重试整理已保存内容'),undefined);assert.equal(button(tree,'立即整理').props.disabled,true);
  assert.equal(f.requests.filter(r=>r.options.method==='POST').length,0);
});

test('submitted or legacy unknown reports never offer the unsubmitted retry shortcut',async t=>{
  for(const submitted of [true,undefined]){
    const f=await fixture(t,{status:{...apiReady,connection:{provider:'justone',tokenConfigured:false},
      lastReport:{id:'uncertain-report',profile:apiReady.profile,pending:true,submitted,items:[]}}});
    assert.equal(button(f.render(),'重试整理已保存内容'),undefined);
    assert.equal(button(f.render(),'立即整理').props.disabled,true);
  }
});

test('missing-model status gives setup guidance and leaves an explicit manual retry available',async t=>{
  const f=await fixture(t,{status:{...apiReady,status:'model_required',message:''}});
  const tree=f.render();assert.match(text(tree),/配置摘要模型/);assert.match(text(tree),/选择.*模型/);
  assert.equal(button(tree,'立即整理').props.disabled,false);
  await [...f.timers.values()][0]();await tick();assert.equal(f.requests.filter(r=>r.options.method==='POST').length,0);
});
