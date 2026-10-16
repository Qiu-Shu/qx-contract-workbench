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
