const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { createModelCredentialStore } = require('../model-credentials.cjs');

const SECRET = 'synthetic-credential-alpha-20261019';
const REPLACEMENT = 'synthetic-credential-beta-20261019';
function fixture(t, safeStorage = protector()) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'qx-model-credentials-'));
  const dataParent = path.join(root, 'desktop-data');
  const directory = path.join(dataParent, 'model-credentials');
  const file = path.join(directory, 'deepseek.bin');
  t.after(() => {
    assert.equal(path.dirname(root), path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith('qx-model-credentials-'));
    fs.rmSync(root, { recursive: true, force: true });
  });
  const create = (options = {}) => createModelCredentialStore({ dataParent, safeStorage, platform: 'win32', ...options });
  return { root, dataParent, directory, file, safeStorage, create, store: create() };
}
function protector() {
  const key = crypto.randomBytes(32);
  return {
    async isAsyncEncryptionAvailable() { return true; },
    async encryptStringAsync(value) {
      const iv = crypto.randomBytes(12);
      const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
      const encrypted = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()]);
      return Buffer.concat([iv, cipher.getAuthTag(), encrypted]);
    },
    async decryptStringAsync(bytes) {
      const decipher = crypto.createDecipheriv('aes-256-gcm', key, bytes.subarray(0, 12));
      decipher.setAuthTag(bytes.subarray(12, 28));
      return { result: Buffer.concat([decipher.update(bytes.subarray(28)), decipher.final()]).toString('utf8'), shouldReEncrypt: false };
    }
  };
}

test('empty, save, restart, replace and remove expose only status and persist only ciphertext', async (t) => {
  const f = fixture(t);
  assert.deepEqual(await f.store.status(), { status: 'empty' });
  assert.equal(fs.existsSync(f.dataParent), false);
  assert.deepEqual(await f.store.save(`  ${SECRET}  `), { status: 'saved' });
  const first = fs.readFileSync(f.file);
  assert.equal(first.includes(Buffer.from(SECRET)), false);
  assert.deepEqual(await f.create().status(), { status: 'saved' });
  assert.deepEqual(await f.store.save(REPLACEMENT), { status: 'saved' });
  const replaced = fs.readFileSync(f.file);
  assert.notDeepEqual(replaced, first);
  assert.equal(replaced.includes(Buffer.from(REPLACEMENT)), false);
  assert.equal((await f.safeStorage.decryptStringAsync(replaced)).result, REPLACEMENT);
  assert.deepEqual(fs.readdirSync(f.directory), ['deepseek.bin']);
  assert.deepEqual(await f.store.remove(), { status: 'empty' });
  assert.deepEqual(await f.store.remove(), { status: 'empty' });
  assert.deepEqual(await f.create().status(), { status: 'empty' });
  assert.deepEqual(Object.keys(f.store).sort(), ['drain', 'remove', 'save', 'status']);
  assert.equal(await f.store.drain(), undefined);
});

test('save accepts bounded printable ASCII without a required prefix and rejects malformed input without changing old ciphertext', async (t) => {
  const f = fixture(t);
  for (const secret of ['a'.repeat(16), 'Z'.repeat(512), '  valid key with spaces  ']) {
    assert.deepEqual(await f.store.save(secret), { status: 'saved' });
    assert.equal((await f.safeStorage.decryptStringAsync(fs.readFileSync(f.file))).result, secret.trim());
  }
  const before = fs.readFileSync(f.file);
  for (const secret of [undefined, null, 42, {}, [], Buffer.from(SECRET), '', ' '.repeat(20), 'x'.repeat(15), 'x'.repeat(513), `${' '.repeat(1024)}${SECRET}`, `${SECRET}\n`, `\r${SECRET}`, `\t${SECRET}`, `${SECRET}\0`, `${SECRET}\x7f`, `${SECRET}密`, `\u00a0${SECRET}`]) {
    assert.deepEqual(await f.store.save(secret), { status: 'invalid', code: 'CREDENTIAL_INPUT_INVALID' });
    assert.deepEqual(fs.readFileSync(f.file), before);
  }
});

test('only Windows and all available asynchronous protection methods permit status and save', async (t) => {
  const f = fixture(t);
  for (const options of [
    { platform: 'linux' }, { platform: 'darwin' }, { safeStorage: undefined },
    { safeStorage: { isEncryptionAvailable: () => true } },
    { safeStorage: { ...protector(), isAsyncEncryptionAvailable: async () => false } },
    { safeStorage: { ...protector(), isAsyncEncryptionAvailable: async () => { throw new Error(SECRET); } } }
  ]) {
    const store = f.create(options);
    assert.deepEqual(await store.status(), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_UNAVAILABLE' });
    assert.deepEqual(await store.save(SECRET), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_UNAVAILABLE' });
    assert.equal(fs.existsSync(f.directory), false);
  }
  assert.deepEqual(await f.create({ platform: 'linux' }).remove(), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_UNAVAILABLE' });
});

test('status distinguishes corrupt ciphertext from empty and temporary system unavailability without leaking errors', async (t) => {
  const f = fixture(t);
  fs.mkdirSync(f.directory, { recursive: true });
  for (const bytes of [Buffer.alloc(0), Buffer.from('synthetic corrupt ciphertext'), Buffer.alloc(65537)]) {
    fs.writeFileSync(f.file, bytes);
    assert.deepEqual(await f.store.status(), { status: 'invalid', code: 'CREDENTIAL_CORRUPT' });
  }
  await f.store.save(SECRET);
  const before = fs.readFileSync(f.file);
  f.safeStorage.decryptStringAsync = async () => { throw Object.assign(new Error(SECRET), { isTemporarilyUnavailable: true }); };
  assert.deepEqual(await f.store.status(), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_UNAVAILABLE' });
  assert.deepEqual(fs.readFileSync(f.file), before);
  f.safeStorage.decryptStringAsync = async () => { throw new Error(SECRET); };
  assert.deepEqual(await f.store.status(), { status: 'invalid', code: 'CREDENTIAL_CORRUPT' });
});

test('status validates actual decrypted data and reports rotation without rewriting stored bytes', async (t) => {
  const f = fixture(t);
  await f.store.save(SECRET);
  const before = fs.readFileSync(f.file);
  for (const result of [undefined, SECRET, { result: '' }, { result: 'short', shouldReEncrypt: false }, { result: SECRET + '\n', shouldReEncrypt: false }, { result: SECRET, shouldReEncrypt: 'false' }]) {
    f.safeStorage.decryptStringAsync = async () => result;
    assert.deepEqual(await f.store.status(), { status: 'invalid', code: 'CREDENTIAL_CORRUPT' });
  }
  f.safeStorage.decryptStringAsync = async () => ({ result: SECRET, shouldReEncrypt: true });
  assert.deepEqual(await f.store.status(), { status: 'unavailable', code: 'CREDENTIAL_ROTATION_REQUIRED' });
  assert.deepEqual(fs.readFileSync(f.file), before);
});

test('remove can safely clear corrupt or oversized ciphertext even when system protection is unavailable', async (t) => {
  const f = fixture(t);
  fs.mkdirSync(f.directory, { recursive: true });
  f.safeStorage.isAsyncEncryptionAvailable = async () => false;
  for (const bytes of [Buffer.from('synthetic corrupt ciphertext'), Buffer.alloc(65537)]) {
    fs.writeFileSync(f.file, bytes);
    assert.deepEqual(await f.store.remove(), { status: 'empty' });
    assert.equal(fs.existsSync(f.file), false);
  }
});

test('invalid parent paths return a fixed result rather than throwing or creating files', async (t) => {
  const f = fixture(t);
  for (const dataParent of [undefined, '', 3, 'relative-data', '//synthetic-server/share', '\\\\synthetic-server\\share', path.join(f.root, 'bad:stream'), path.join(f.root, 'trailing.'), path.join(f.root, 'NUL'), `${f.root}${path.sep}..${path.sep}escape`]) {
    const store = f.create({ dataParent });
    assert.deepEqual(await store.status(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
    assert.deepEqual(await store.save(SECRET), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
    assert.deepEqual(await store.remove(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
  }
});

test('a junction ancestor is rejected for every operation and the linked directory remains untouched', async (t) => {
  const f = fixture(t);
  const outside = path.join(f.root, 'outside');
  fs.mkdirSync(outside);
  fs.symlinkSync(outside, f.dataParent, 'junction');
  for (const operation of [() => f.store.status(), () => f.store.save(SECRET), () => f.store.remove()]) {
    assert.deepEqual(await operation(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
  }
  assert.deepEqual(fs.readdirSync(outside), []);
});

test('the credential directory cannot be a junction, dangling junction or ordinary file', async (t) => {
  const f = fixture(t);
  fs.mkdirSync(f.dataParent);
  for (const dangling of [false, true]) {
    const outside = path.join(f.root, `outside-${dangling}`);
    if (!dangling) fs.mkdirSync(outside);
    fs.symlinkSync(outside, f.directory, 'junction');
    for (const operation of [() => f.store.status(), () => f.store.save(SECRET), () => f.store.remove()]) {
      assert.deepEqual(await operation(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
    }
    fs.unlinkSync(f.directory);
  }
  fs.writeFileSync(f.directory, 'ordinary file');
  assert.deepEqual(await f.store.save(SECRET), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
  assert.equal(fs.readFileSync(f.directory, 'utf8'), 'ordinary file');
});

test('credential symbolic links including dangling links are never read, replaced or removed', async (t) => {
  const f = fixture(t);
  fs.mkdirSync(f.directory, { recursive: true });
  const outside = path.join(f.root, 'outside.bin');
  for (const dangling of [false, true]) {
    if (!dangling) fs.writeFileSync(outside, 'keep outside');
    fs.symlinkSync(outside, f.file, 'file');
    for (const operation of [() => f.store.status(), () => f.store.save(SECRET), () => f.store.remove()]) {
      assert.deepEqual(await operation(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
    }
    assert.equal(fs.lstatSync(f.file).isSymbolicLink(), true);
    fs.unlinkSync(f.file);
    if (!dangling) {
      assert.equal(fs.readFileSync(outside, 'utf8'), 'keep outside');
      fs.unlinkSync(outside);
    }
  }
});

test('credential hard links and directories are rejected without touching either target', async (t) => {
  const f = fixture(t);
  fs.mkdirSync(f.directory, { recursive: true });
  const outside = path.join(f.root, 'outside.bin');
  fs.writeFileSync(outside, 'keep outside');
  fs.linkSync(outside, f.file);
  for (const operation of [() => f.store.status(), () => f.store.save(SECRET), () => f.store.remove()]) {
    assert.deepEqual(await operation(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
  }
  assert.equal(fs.readFileSync(outside, 'utf8'), 'keep outside');
  fs.unlinkSync(f.file);
  fs.mkdirSync(f.file);
  assert.deepEqual(await f.store.remove(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
  assert.equal(fs.statSync(f.file).isDirectory(), true);
});

test('a directory replaced by a junction during asynchronous encryption cannot redirect the write', async (t) => {
  const f = fixture(t);
  await f.store.save(SECRET);
  const before = fs.readFileSync(f.file);
  const renamed = path.join(f.root, 'original-directory');
  const outside = path.join(f.root, 'outside');
  fs.mkdirSync(outside);
  const encrypt = f.safeStorage.encryptStringAsync;
  f.safeStorage.encryptStringAsync = async (secret) => {
    fs.renameSync(f.directory, renamed);
    fs.symlinkSync(outside, f.directory, 'junction');
    return encrypt(secret);
  };
  assert.deepEqual(await f.store.save(REPLACEMENT), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
  assert.deepEqual(fs.readdirSync(outside), []);
  assert.deepEqual(fs.readFileSync(path.join(renamed, 'deepseek.bin')), before);
});

test('malformed encryption results and rejected encryption preserve old ciphertext and return a fixed error', async (t) => {
  const f = fixture(t);
  await f.store.save(SECRET);
  const before = fs.readFileSync(f.file);
  for (const bytes of [undefined, SECRET, Buffer.alloc(0), Buffer.alloc(65537)]) {
    f.safeStorage.encryptStringAsync = async () => bytes;
    assert.deepEqual(await f.store.save(REPLACEMENT), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_FAILED' });
    assert.deepEqual(fs.readFileSync(f.file), before);
  }
  f.safeStorage.encryptStringAsync = async () => { throw new Error(SECRET); };
  assert.deepEqual(await f.store.save(REPLACEMENT), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_FAILED' });
  assert.deepEqual(fs.readFileSync(f.file), before);
  f.safeStorage.encryptStringAsync = async () => { throw Object.assign(new Error(SECRET), { isTemporarilyUnavailable: true }); };
  assert.deepEqual(await f.store.save(REPLACEMENT), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_UNAVAILABLE' });
  assert.deepEqual(fs.readFileSync(f.file), before);
  assert.deepEqual(fs.readdirSync(f.directory), ['deepseek.bin']);
});

test('flush or atomic replacement failures preserve old ciphertext and remove only the temporary ciphertext', async (t) => {
  const f = fixture(t);
  await f.store.save(SECRET);
  const before = fs.readFileSync(f.file);
  const unrelated = path.join(f.directory, 'unrelated.tmp');
  fs.writeFileSync(unrelated, 'keep unrelated file');
  for (const method of ['fsyncSync', 'renameSync']) {
    t.mock.method(fs, method, () => { throw new Error(SECRET); });
    assert.deepEqual(await f.store.save(REPLACEMENT), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_FAILED' });
    t.mock.restoreAll();
    assert.deepEqual(fs.readFileSync(f.file), before);
    assert.deepEqual(fs.readdirSync(f.directory).sort(), ['deepseek.bin', 'unrelated.tmp']);
    assert.equal(fs.readFileSync(unrelated, 'utf8'), 'keep unrelated file');
    assert.deepEqual(await f.store.status(), { status: 'saved' });
  }
});

test('status, save and remove share a serial queue and drain waits for already accepted operations', async (t) => {
  const f = fixture(t);
  const encrypt = f.safeStorage.encryptStringAsync;
  let enter;
  let release;
  const entered = new Promise(resolve => { enter = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  f.safeStorage.encryptStringAsync = async (secret) => { enter(); await gate; return encrypt(secret); };
  t.after(() => release());
  const first = f.store.save(SECRET);
  const reading = f.store.status();
  const removing = f.store.remove();
  const replacing = f.store.save(REPLACEMENT);
  const finalStatus = f.store.status();
  let drained = false;
  const drain = f.store.drain().then(() => { drained = true; });
  await entered;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(drained, false);
  assert.equal(fs.existsSync(f.file), false);
  release();
  assert.deepEqual(await Promise.all([first, reading, removing, replacing, finalStatus]), [
    { status: 'saved' }, { status: 'saved' }, { status: 'empty' }, { status: 'saved' }, { status: 'saved' }
  ]);
  await drain;
  assert.equal(drained, true);
  assert.equal((await f.safeStorage.decryptStringAsync(fs.readFileSync(f.file))).result, REPLACEMENT);
});

test('a failed operation does not poison the queue or prevent a later safe removal', async (t) => {
  const f = fixture(t);
  await f.store.save(SECRET);
  f.safeStorage.encryptStringAsync = async () => { throw new Error(SECRET); };
  const failed = f.store.save(REPLACEMENT);
  const reading = f.store.status();
  const removing = f.store.remove();
  assert.deepEqual(await failed, { status: 'unavailable', code: 'CREDENTIAL_STORAGE_FAILED' });
  assert.deepEqual(await reading, { status: 'saved' });
  assert.deepEqual(await removing, { status: 'empty' });
  await f.store.drain();
});

test('status checks current file identity again after decrypting', async (t) => {
  const f = fixture(t);
  await f.store.save(SECRET);
  const decrypt = f.safeStorage.decryptStringAsync;
  f.safeStorage.decryptStringAsync = async (bytes) => {
    fs.unlinkSync(f.file);
    return decrypt(bytes);
  };
  assert.deepEqual(await f.store.status(), { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' });
  assert.deepEqual(await f.store.status(), { status: 'empty' });
});

test('oversized ciphertext is rejected before reading or decrypting it', async (t) => {
  const f = fixture(t);
  fs.mkdirSync(f.directory, { recursive: true });
  fs.writeFileSync(f.file, Buffer.alloc(65537));
  let calls = 0;
  f.safeStorage.decryptStringAsync = async () => { calls++; throw new Error('must not decrypt'); };
  assert.deepEqual(await f.store.status(), { status: 'invalid', code: 'CREDENTIAL_CORRUPT' });
  assert.equal(calls, 0);
});

test('filesystem failures are fixed results and never expose file paths or raw exception messages', async (t) => {
  const f = fixture(t);
  await f.store.save(SECRET);
  t.mock.method(fs, 'openSync', () => { throw new Error(SECRET + f.file); });
  assert.deepEqual(await f.store.status(), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_FAILED' });
  t.mock.restoreAll();
  t.mock.method(fs, 'unlinkSync', () => { throw new Error(SECRET + f.file); });
  assert.deepEqual(await f.store.remove(), { status: 'unavailable', code: 'CREDENTIAL_STORAGE_FAILED' });
  t.mock.restoreAll();
  assert.deepEqual(await f.store.status(), { status: 'saved' });
});
