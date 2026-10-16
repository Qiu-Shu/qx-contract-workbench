const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
test('library selection recognizes existing catalog without creating or repairing files', () => {
  const { validLibraryRoot } = require('../policy.cjs');
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'qx-library-picker-'));
  try {
    assert.equal(typeof validLibraryRoot, 'function');
    assert.equal(validLibraryRoot(root), false);
    assert.deepEqual(fs.readdirSync(root), []);
    fs.writeFileSync(path.join(root,'catalog.sqlite'), 'fixture');
    fs.writeFileSync(path.join(root,'current.json'), '{}');
    assert.equal(validLibraryRoot(root), true);
  } finally { fs.rmSync(root,{recursive:true}); }
});
test('only owned loopback origin and exact setup document are allowed', () => {
  assert.ok(fs.existsSync(require('node:path').join(__dirname, '../policy.cjs')), 'policy missing');
  const { navigationAllowed, setupSenderAllowed } = require('../policy.cjs');
  const own = 'http://127.0.0.1:18922';
  const setup = 'file:///D:/App/setup.html';
  assert.equal(navigationAllowed(own + '/login', own, setup), true);
  for (const url of ['https://example.com', 'http://localhost:18922/', own+'@example.com/', 'file:///C:/secret', 'javascript:alert(1)', 'http://127.0.0.1:18923/']) {
    assert.equal(navigationAllowed(url, own, setup), false, url);
  }
  assert.equal(setupSenderAllowed(setup, setup, true), true);
  assert.equal(setupSenderAllowed(own, setup, true), false);
  assert.equal(setupSenderAllowed(setup, setup, false), false);
  assert.equal(setupSenderAllowed(setup + '?redirect=1', setup, true), false);
});
test('clipboard permits writing only from the owned main frame, never reading', () => {
  const { clipboardWriteAllowed } = require('../policy.cjs');
  const own='http://127.0.0.1:18922';
  assert.equal(typeof clipboardWriteAllowed,'function');
  assert.equal(clipboardWriteAllowed('clipboard-sanitized-write',own+'/intakes/123',own,true),true);
  for(const permission of ['clipboard-read','deprecated-sync-clipboard-read','media','notifications'])
    assert.equal(clipboardWriteAllowed(permission,own+'/',own,true),false);
  assert.equal(clipboardWriteAllowed('clipboard-sanitized-write',own+'/',own,false),false);
  assert.equal(clipboardWriteAllowed('clipboard-sanitized-write','file:///setup',own,true),false);
  assert.equal(clipboardWriteAllowed('clipboard-sanitized-write','https://example.com',own,true),false);
});
