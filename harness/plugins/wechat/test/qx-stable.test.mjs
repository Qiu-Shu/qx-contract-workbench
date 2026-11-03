import test from 'node:test';
import assert from 'node:assert/strict';
import {openSessionAgent} from '../session.js';
test('a failed existing-session restore never creates an empty conversation', async () => {
  let creates=0;
  const agents={resume: async()=>{throw new Error('corrupt session log');}, create: async()=>{creates++;return {agent:{}};}};
  await assert.rejects(openSessionAgent({agents,sessionId:'owner'}), /corrupt session log/);
  assert.equal(creates,0);
});
test('a genuinely absent session creates only the exact requested identity', async () => {
  class Missing extends Error {}
  const calls=[];
  const agents={resume: async()=>{throw new Missing('absent');}, create: async(args)=>{calls.push(args.sessionId);return {agent:{}};}};
  const result=await openSessionAgent({agents,sessionId:'owner',isMissingSession: e=>e instanceof Missing});
  assert.equal(result.sessionId,'owner'); assert.deepEqual(calls,['owner']);
});
