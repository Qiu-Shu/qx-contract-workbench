const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
test('owned backend validates readiness, stops on EOF and rejects forged nonce', async () => {
  assert.ok(fs.existsSync(path.join(__dirname, '../backend.cjs')), 'backend owner missing');
  const { Backend } = require('../backend.cjs');
  const fixture = path.join(__dirname, 'fixture-child.cjs');
  const child = new Backend(process.execPath, [fixture]);
  const ready = await child.start({data_parent:'test'});
  assert.equal(ready.port, 19022);
  const pid = child.child.pid;
  await child.stop();
  assert.throws(() => process.kill(pid, 0));
  const bad = new Backend(process.execPath, [fixture]);
  await assert.rejects(bad.start({bad:true}), /BACKEND_PROTOCOL/);
  await bad.stop();
});
