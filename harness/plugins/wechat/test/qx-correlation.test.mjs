import test from 'node:test';
import assert from 'node:assert/strict';
import {ReplyCollector} from '../qx-reply.js';
test('a desktop message claimed before the queued WeChat message cannot steal its reply',async()=>{
  const callbacks=new Map();const scope={on(name,fn){callbacks.set(name,fn);}};
  const collector=new ReplyCollector(scope), agent={session:{id:'shared'}};
  const waiting=collector.wait('shared','wechat-message',1000);
  callbacks.get('agent/inbox/claimed')({agent,message:{id:'desktop-message'},turn:1});
  callbacks.get('session/event')({id:'shared'},{type:'assistant/message',data:{turn:1,message:{content:[{type:'text',text:'desktop-only'}]}}});
  callbacks.get('session/event')({id:'shared'},{type:'turn/end',data:{turn:1,reason:{kind:'end_turn'}}});
  const wasStillWaiting=collector.isWaiting('shared');
  callbacks.get('agent/inbox/claimed')({agent,message:{id:'wechat-message'},turn:2});
  callbacks.get('session/event')({id:'shared'},{type:'assistant/message',data:{turn:2,message:{content:[{type:'text',text:'wechat-answer'}]}}});
  callbacks.get('session/event')({id:'shared'},{type:'turn/end',data:{turn:2,reason:{kind:'end_turn'}}});
  const answer=await waiting;
  assert.equal(wasStillWaiting,true);
  assert.equal(answer.text,'wechat-answer');
});
