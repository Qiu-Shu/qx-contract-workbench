// Preloaded before the real Harness: this test may fetch only its loopback fixtures.
import assert from 'node:assert/strict';
const original=globalThis.fetch;
globalThis.fetch=(input,options)=>{
  const url=new URL(input instanceof Request?input.url:input);
  assert.equal(url.protocol,'http:','isolated Harness must not call an external service');
  assert.equal(url.hostname,'127.0.0.1','isolated Harness must only fetch loopback fixtures');
  return original(input,options);
};
