import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {createRenderer} from '../src/cn_contract/web/static/assistant-render.mjs';

// Exercise only render operations; browser layout, focus and scrolling need a real browser.
class Element {
  constructor(tag='div') {
    this.tagName=tag;this.children=[];this.dataset={};this.attributes={};this.parentNode=null;
    this.hidden=false;this.disabled=false;this.value='';this._text='';
    const classes=new Set();
    this.classList={toggle:(name,on)=>on?classes.add(name):classes.delete(name)};
  }
  set textContent(value){this._text=String(value);this.replaceChildren();}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  get firstChild(){return this.children[0]||null;}
  get nextSibling(){return this.parentNode?.children[this.parentNode.children.indexOf(this)+1]||null;}
  setAttribute(name,value){this.attributes[name]=String(value);}
  removeAttribute(name){delete this.attributes[name];}
  addEventListener(){}
  append(...children){for(const child of children){child.remove();child.parentNode=this;this.children.push(child);}}
  replaceChildren(...children){for(const child of this.children)child.parentNode=null;this.children=[];this.append(...children);}
  insertBefore(child,before){child.remove();child.parentNode=this;const index=before?this.children.indexOf(before):this.children.length;this.children.splice(index,0,child);}
  remove(){if(this.parentNode){const parent=this.parentNode;parent.children.splice(parent.children.indexOf(this),1);this.parentNode=null;}}
  querySelectorAll(selector){return walk(this).slice(1).filter(element=>selector==='p'?element.tagName==='p':element.className?.split(' ').includes(selector.slice(1)));}
}
const walk=element=>[element,...element.children.flatMap(walk)];
const cid='11111111-1111-4111-8111-111111111111';
const mid='22222222-2222-4222-8222-222222222222';
const mid2='33333333-3333-4333-8333-333333333333';
function fixture(t) {
  const elements=new Map(),skills=[new Element('button')];skills[0].dataset.skill='client_reply';
  const root={body:new Element('body'),createElement:tag=>new Element(tag),querySelectorAll:()=>skills,
    getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}};
  const original=globalThis.document;globalThis.document=root;t.after(()=>globalThis.document=original);
  return {root,render:createRenderer(root),at:id=>root.getElementById(id)};
}
function state(overrides={}) {
  return {id:cid,text:'合成咨询',skill:null,status:'saved',loading:false,dirty:false,error:null,conflict:null,
    view:{scope:{conversation_id:cid,scope_kind:'conversation'},messages:[],display_title:'合成对话'},
    generation:{phase:'idle',capability:{state:'ready'},canSend:true,items:[],error:null},...overrides};
}
function item(messageId=mid,overrides={}) {
  return {message_id:messageId,attempt:{id:`attempt-${messageId}`,scope:{conversation_id:cid},state:'received',
    reserved_usd:'0.012345',unit:'USD',receipt:{state:'received',cost_status:'estimated',estimated_cost_usd:'0.001234',error_code:null},
    output:{audience:'internal',review_status:'unverified',candidate:{text:`内部合成草稿 ${messageId}`,citations:[{message_id:messageId,quote_sha256:'a'.repeat(64)}]}},...overrides}};
}
const messages=()=>[{id:mid,role:'user',content:'第一段原文\n第二行'},{id:mid2,role:'user',content:'第二次输入'}];
const withResults=(items=[item(),item(mid2)])=>state({view:{scope:{conversation_id:cid,scope_kind:'conversation'},messages:messages()},
  generation:{phase:'idle',capability:{state:'ready'},canSend:true,items,error:null}});

test('send follows the generation gate and existing draft/readonly guards',t=>{
  const f=fixture(t);f.render.state(state());assert.equal(f.at('send').disabled,false);
  for(const overrides of [{loading:true},{status:'saving'},{status:'conflict'},{status:'revoked'},{status:'readonly'},{skill:'client_reply'}]) {
    f.render.state(state(overrides));assert.equal(f.at('send').disabled,true,JSON.stringify(overrides));
  }
  f.render.state(state(),true);assert.equal(f.at('send').disabled,true);
  const s=state();s.generation.canSend=false;f.render.state(s);assert.equal(f.at('send').disabled,true);
  delete s.generation;f.render.state(s);assert.equal(f.at('send').disabled,true);
});

test('generation uncertainty has its own status and lookup action, without relabeling a saved draft',t=>{
  const f=fixture(t),s=state();s.generation={...s.generation,phase:'unknown',canSend:false,error:{code:'NETWORK_UNKNOWN'}};
  f.render.state(s);assert.match(f.at('generation-status').textContent,/结果.*不确定/);
  assert.equal(f.at('recover-generation').hidden,false);assert.equal(f.at('recover-generation').disabled,false);
  assert.equal(f.at('save-status').textContent,'草稿已保存到本机');
  assert.doesNotMatch(f.at('generation-status').textContent,/重试保存/);
  s.generation.phase='checking';f.render.state(s);assert.equal(f.at('recover-generation').hidden,true);
});

test('capability states give distinct truthful explanations',t=>{
  const f=fixture(t),s=state();
  const expected={unconfigured:/未配置|未启用/,unapproved:/授权|获准/,empty:/输入/,unsupported:/材料|输入范围/,
    busy:/正在|处理中/,budget_exhausted:/预算/,restored_read_only:/只读/,ready:/内部|核对/};
  for(const [value,pattern] of Object.entries(expected)) {
    s.generation.capability={state:value};f.render.state(s);assert.match(f.at('generation-note').textContent,pattern,value);
  }
  s.skill='client_reply';f.render.state(s);assert.match(f.at('generation-note').textContent,/能力.*尚未接入|技能.*尚未接入/);
});

test('results stay with their matching input in chronological history and have source anchors',t=>{
  const f=fixture(t);f.render.state(withResults([item(mid2),item()]));
  const history=f.at('history');assert.equal(history.children.length,2);
  assert.equal(history.children[0].id,`message-${mid}`);assert.equal(history.children[1].id,`message-${mid2}`);
  for(const [index,id] of [mid,mid2].entries()) {
    const entry=history.children[index];assert.match(entry.textContent,new RegExp(`内部合成草稿 ${id}`));
    assert.doesNotMatch(entry.textContent,new RegExp(`内部合成草稿 ${index?mid:mid2}`));
    assert.match(entry.textContent,/内部.*待核对|内部.*未经.*审核/);
    assert.equal(walk(entry).find(element=>element.tagName==='a').href,`#message-${id}`);
  }
});

test('model text remains literal with whitespace and source links only target loaded messages',t=>{
  const f=fixture(t),result=item();const text='<img src=x onerror=alert(1)>\n  合成文字\nhttps://example.invalid/'+ '长'.repeat(500);
  result.attempt.output.candidate.text=text;f.render.state(withResults([result]));
  const body=walk(f.at('history')).find(element=>element.className==='generation-text');
  assert.equal(body.textContent,text);assert.equal(body.children.length,0);
  result.attempt.output.candidate.citations=[{message_id:'not-loaded',quote_sha256:'b'.repeat(64)}];
  f.render.state(withResults([result]));assert.equal(walk(f.at('history')).filter(element=>element.tagName==='a').length,0);
});

test('unrelated items and prior conversation content are cleared on switching or revocation',t=>{
  const f=fixture(t);f.render.state(withResults([item(),item('unmatched')]));
  assert.doesNotMatch(f.at('history').textContent,/unmatched/);
  const next=state({id:'new-conversation',loading:true});next.generation.items=[item()];f.render.state(next);
  assert.equal(f.at('history').children.length,0);
  f.render.state(withResults());const revoked=withResults();revoked.status='revoked';f.render.state(revoked);
  assert.equal(f.at('history').children.length,0);assert.equal(f.at('send').disabled,true);
  assert.equal(f.at('recover-generation').hidden,true);
});

test('an updated attempt replaces its former state, and draft edits retain unchanged history nodes',t=>{
  const f=fixture(t),result=item(mid,{state:'sending',receipt:null,output:null}),s=withResults([result]);
  f.render.state(s);assert.match(f.at('history').textContent,/正在生成|正在发送/);
  const before=f.at('history').children[0];s.text='继续编辑';f.render.state(s);assert.equal(f.at('history').children[0],before);
  s.generation.items=[item()];f.render.state(s);assert.match(f.at('history').textContent,/内部合成草稿/);
  assert.doesNotMatch(f.at('history').textContent,/正在生成|正在发送/);
});

test('unknown, estimated and proven unsent cost remain distinct without rounding decimal values',t=>{
  const f=fixture(t),result=item();
  result.attempt.receipt={cost_status:'unknown',estimated_cost_usd:null,error_code:'PROVIDER_ERROR'};
  f.render.state(withResults([result]));assert.match(f.at('history').textContent,/费用未知/);
  assert.match(f.at('history').textContent,/0\.012345 USD/);assert.doesNotMatch(f.at('history').textContent,/费用 0 USD/);
  result.attempt.receipt={cost_status:'estimated',estimated_cost_usd:'0.000000000123',error_code:null};
  f.render.state(withResults([result]));assert.match(f.at('history').textContent,/估算费用 0\.000000000123 USD/);
  assert.match(f.at('history').textContent,/实际扣费.*核对/);
  result.attempt={...result.attempt,state:'failed_before_send',output:null,receipt:{cost_status:'not_sent',estimated_cost_usd:'0',error_code:'BLOCKED_LIVE'}};
  f.render.state(withResults([result]));assert.match(f.at('history').textContent,/未发送.*费用 0 USD/);
});

test('generation errors expose a fixed recovery explanation rather than raw diagnostics',t=>{
  const f=fixture(t),s=state();s.generation={...s.generation,phase:'error',canSend:false,error:{code:'NOT_SUPPORTED',message:'PRIVATE RAW DIAGNOSTIC'}};
  f.render.state(s);assert.match(f.at('generation-status').textContent,/不支持|尚未接入/);
  assert.doesNotMatch(f.at('generation-status').textContent,/PRIVATE/);
});

test('failed capability reads can be retried before any task exists',t=>{
  const f=fixture(t),s=state();s.generation={...s.generation,phase:'error',canSend:false,error:{code:'REQUEST_FAILED'}};
  f.render.state(s);assert.match(f.at('generation-status').textContent,/刷新/);
  assert.equal(f.at('refresh-run').hidden,false);assert.equal(f.at('refresh-run').disabled,false);
  s.generation.phase='idle';f.render.state(s);assert.equal(f.at('refresh-run').hidden,true);
});

test('initial template keeps send disabled, recovery hidden and describes controlled generation',()=>{
  const html=readFileSync(new URL('../src/cn_contract/web/templates/assistant.html',import.meta.url),'utf8');
  assert.match(html,/<button\b[^>]*id="send"[^>]*\bdisabled/);
  assert.match(html,/<button\b[^>]*id="recover-generation"[^>]*\bhidden/);
  assert.match(html,/id="generation-status"[^>]*role="status"/);
  assert.match(html,/id="generation-note"/);assert.match(html,/未经律师审核|待核对/);
  assert.doesNotMatch(html,/生成尚未接通|发送尚未开放|当前不会生成回复/);
});

test('generated paragraphs keep wrapping and preserve whitespace in the stylesheet',()=>{
  const css=readFileSync(new URL('../src/cn_contract/web/static/assistant.css',import.meta.url),'utf8');
  assert.match(css,/\.generation-text[^}]*white-space:\s*pre-wrap/s);
  assert.match(css,/\.generation-text[^}]*overflow-wrap:\s*anywhere/s);
});
