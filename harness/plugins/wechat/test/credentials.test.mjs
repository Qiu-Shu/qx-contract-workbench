import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { mkdtemp, readFile, readdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { WechatState } from '../state.js';

// Only the OS encryption boundary is substituted. The store and filesystem are real.
function syntheticProtector() {
  const contents = new Map();
  return {
    available: true,
    async protect(value) {
      const ciphertext = Buffer.from(`opaque-ciphertext-${contents.size}`).toString('base64');
      contents.set(ciphertext, value);
      return ciphertext;
    },
    async reveal(ciphertext) {
      if (!contents.has(ciphertext)) throw Error('synthetic invalid ciphertext');
      return contents.get(ciphertext);
    },
  };
}

async function fixture(t, credentialProtector = syntheticProtector()) {
  const root = await mkdtemp(join(tmpdir(), 'wechat-credential-test-'));
  t.after(() => rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 }));
  const state = new WechatState({ root, credentialProtector });
  await state.init();
  return { root, state, credentialProtector };
}

const account = { token: 'synthetic-account-token', userId: 'synthetic-owner', baseUrl: 'https://example.invalid' };
const legacyAccount = { ...account, savedAt: '2026-01-01T00:00:00.000Z' };
const legacyContexts = {
  'synthetic-owner': { token: 'synthetic-context-token', savedAt: '2026-01-02T00:00:00.000Z' },
  'synthetic-peer': { token: 'synthetic-peer-token', savedAt: '2026-01-03T00:00:00.000Z' },
};

async function credentialError(operation) {
  await assert.rejects(operation, error => {
    assert.match(error.code ?? '', /^WECHAT_CREDENTIAL_/);
    assert.equal(error.retryable, true);
    assert.doesNotMatch(String(error.stack), /synthetic-account-token|synthetic-context-token|sensitive-provider-detail/);
    assert.equal(error.cause, undefined, 'provider errors must not escape through a cause');
    return true;
  });
}

async function assertSealedFiles(root) {
  for (const name of await readdir(join(root, 'accounts'))) {
    const text = await readFile(join(root, 'accounts', name), 'utf8');
    assert.doesNotMatch(text, /synthetic-(?:account|context|peer)-token/);
  }
}

test('first account and context writes contain no plaintext and reopen with their original values', async t => {
  const { root, state, credentialProtector } = await fixture(t);
  const saved = await state.saveAccount('bot@im.bot', account);
  await state.saveContextToken('bot@im.bot', 'synthetic-owner', 'synthetic-context-token');
  await assertSealedFiles(root);
  const restarted = new WechatState({ root, credentialProtector });
  assert.deepEqual(await restarted.loadAccount('bot-im-bot'), saved);
  assert.equal((await restarted.loadContextTokens('bot-im-bot'))['synthetic-owner'].token, 'synthetic-context-token');
  assert.equal((await restarted.loadAccounts())[0].accountId, 'bot-im-bot');
  await restarted.saveAccount('bot-im-bot', { baseUrl: 'https://changed.example.invalid' });
  assert.equal((await restarted.loadAccount('bot-im-bot')).token, account.token);
  await assertSealedFiles(root);
});

for (const kind of ['account', 'context']) {
  const legacy = kind === 'account' ? legacyAccount : legacyContexts;
  const pathFor = state => kind === 'account' ? state.accountFile('bot') : state.contextTokenFile('bot');
  const load = state => kind === 'account' ? state.loadAccount('bot') : state.loadContextTokens('bot');
  const save = state => kind === 'account' ? state.saveAccount('bot', account)
    : state.saveContextToken('bot', 'synthetic-owner', 'synthetic-context-token');

  test(`${kind}: legacy plaintext migrates before returning, preserving metadata and restart behavior`, async t => {
    const { root, state, credentialProtector } = await fixture(t);
    await writeFile(pathFor(state), JSON.stringify(legacy));
    assert.deepEqual(await load(state), legacy);
    await assertSealedFiles(root);
    assert.deepEqual(await load(new WechatState({ root, credentialProtector })), legacy);
    assert.equal((await readdir(join(root, 'accounts'))).filter(name => name.endsWith('.tmp')).length, 0);
  });

  test(`${kind}: unavailable protection rejects first writes without leaving credentials`, async t => {
    const { root, state } = await fixture(t, { available: false });
    await credentialError(() => save(state));
    assert.deepEqual(await readdir(join(root, 'accounts')), []);
    assert.deepEqual(await state.listAccounts(), []);
  });

  for (const failure of ['unavailable', 'encrypt', 'verify', 'replace']) {
    test(`${kind}: ${failure} failure preserves old plaintext and permits a safe retry`, async t => {
      const good = syntheticProtector();
      const broken = failure === 'unavailable' ? { available: false } : {
        ...good,
        ...(failure === 'encrypt' ? { protect: async () => { throw Error('sensitive-provider-detail'); } } : {}),
        ...(failure === 'verify' ? { reveal: async () => 'incorrect plaintext' } : {}),
      };
      const { root, state } = await fixture(t, broken);
      const raw = JSON.stringify(legacy, null, 2);
      await writeFile(pathFor(state), raw);
      if (failure === 'replace') t.mock.method(fs, 'rename', async () => { throw Error('sensitive-provider-detail'); });
      await credentialError(() => load(state));
      assert.equal(await readFile(pathFor(state), 'utf8'), raw);
      assert.equal((await readdir(join(root, 'accounts'))).length, 1, 'failed migration leaves no extra plaintext copy');
      t.mock.restoreAll();
      const retried = new WechatState({ root, credentialProtector: good });
      assert.deepEqual(await load(retried), legacy);
      await assertSealedFiles(root);
    });
  }

  test(`${kind}: interrupted migration keeps the original and any staged file is already opaque`, async t => {
    const { root, state, credentialProtector } = await fixture(t);
    const raw = JSON.stringify(legacy);
    await writeFile(pathFor(state), raw);
    const script = `
      import { WechatState } from ${JSON.stringify(new URL('../state.js', import.meta.url).href)};
      const state = new WechatState({root: process.argv[1], credentialProtector: {
        available:true, protect:async()=> 'b3BhcXVlLXN5bnRoZXRpYy1jaXBoZXI=',
        reveal:async()=> process.exit(23)
      }});
      await state.${kind === 'account' ? 'loadAccount' : 'loadContextTokens'}('bot');
    `;
    const child = spawnSync(process.execPath, ['--input-type=module', '--eval', script, root], { encoding: 'utf8', windowsHide: true, timeout: 15000 });
    assert.equal(child.status, 23, child.stderr);
    assert.equal(await readFile(pathFor(state), 'utf8'), raw);
    for (const name of (await readdir(join(root, 'accounts'))).filter(name => name.endsWith('.tmp'))) {
      assert.doesNotMatch(await readFile(join(root, 'accounts', name), 'utf8'), /synthetic-(?:account|context|peer)-token/);
    }
    assert.deepEqual(await load(new WechatState({ root, credentialProtector })), legacy);
  });

  test(`${kind}: corrupt ciphertext is preserved and never treated as an absent credential`, async t => {
    const { state } = await fixture(t);
    await save(state);
    const sealed = JSON.parse(await readFile(pathFor(state), 'utf8'));
    sealed.ciphertext = 'dpapi:invalid-ciphertext';
    const corrupt = JSON.stringify(sealed);
    await writeFile(pathFor(state), corrupt);
    await credentialError(() => load(state));
    assert.equal(await readFile(pathFor(state), 'utf8'), corrupt);
  });

  test(`${kind}: malformed JSON is reported and cannot be overwritten by a save`, async t => {
    const { state } = await fixture(t);
    const corrupt = '{"token":"synthetic-account-token"';
    await writeFile(pathFor(state), corrupt);
    await credentialError(() => load(state));
    await credentialError(() => save(state));
    assert.equal(await readFile(pathFor(state), 'utf8'), corrupt);
  });
}

test('concurrent context updates preserve every peer and concurrent accounts preserve the index', async t => {
  const { root, state, credentialProtector } = await fixture(t);
  await Promise.all(['one', 'two', 'three'].map(peer => state.saveContextToken('bot', peer, 'synthetic-context-token')));
  assert.deepEqual(Object.keys(await state.loadContextTokens('bot')).sort(), ['one', 'three', 'two']);
  await Promise.all(['one', 'two', 'three'].map(id => state.saveAccount(id, account)));
  assert.deepEqual((await state.listAccounts()).sort(), ['one', 'three', 'two']);
  const restarted = new WechatState({ root, credentialProtector });
  await restarted.removeAccount('one');
  assert.equal(await restarted.loadAccount('one'), null);
  assert.deepEqual(await restarted.loadContextTokens('missing'), {});
  await assertSealedFiles(root);
});

test('verified credentials survive a temporary protector outage in memory, but changed disk data is not trusted', async t => {
  const { state, credentialProtector } = await fixture(t);
  await state.saveAccount('bot', account);
  await state.saveContextToken('bot', 'synthetic-owner', 'synthetic-context-token');
  credentialProtector.reveal = async () => { throw Error('sensitive-provider-detail'); };
  const loaded = await state.loadAccount('bot');
  assert.equal(loaded.token, account.token);
  loaded.token = 'caller-mutated-value';
  assert.equal((await state.loadAccount('bot')).token, account.token);
  assert.equal((await state.loadContextTokens('bot'))['synthetic-owner'].token, 'synthetic-context-token');
  const raw = await readFile(state.accountFile('bot'), 'utf8');
  await writeFile(state.accountFile('bot'), raw.replace('dpapi:', 'dpapi:damaged'));
  await credentialError(() => state.loadAccount('bot'));
});

test('malformed ciphertext is rejected before it can reach the PowerShell protection boundary', async t => {
  const { state, credentialProtector } = await fixture(t);
  await state.saveAccount('bot', account);
  const envelope = JSON.parse(await readFile(state.accountFile('bot'), 'utf8'));
  envelope.ciphertext = "dpapi:QUJD'; invalid PowerShell input";
  const raw = JSON.stringify(envelope);
  await writeFile(state.accountFile('bot'), raw);
  credentialProtector.reveal = async () => JSON.stringify(account);
  await credentialError(() => state.loadAccount('bot'));
  assert.equal(await readFile(state.accountFile('bot'), 'utf8'), raw);
});
