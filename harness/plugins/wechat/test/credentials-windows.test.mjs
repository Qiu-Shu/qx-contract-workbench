import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { WechatState } from '../state.js';

test('Windows current-user DPAPI protects new credentials, migrates legacy files, and reopens in a new process', {
  skip: process.platform !== 'win32' ? 'Requires the current Windows user DPAPI profile' : false,
}, async t => {
  const root = await mkdtemp(join(tmpdir(), 'wechat-dpapi-integration-'));
  t.after(() => rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 }));
  const state = new WechatState({ root });
  const token = 'synthetic-windows-account-token';
  const contextToken = 'synthetic-windows-context-token';
  await state.saveAccount('new', { token, userId: 'synthetic-owner', baseUrl: 'https://example.invalid' });
  await state.saveContextToken('new', 'synthetic-owner', contextToken);
  const legacy = { token, userId: 'synthetic-owner', savedAt: '2026-01-01T00:00:00.000Z' };
  const legacyContext = { 'synthetic-owner': { token: contextToken, savedAt: '2026-01-02T00:00:00.000Z' } };
  await writeFile(state.accountFile('legacy'), JSON.stringify(legacy));
  await writeFile(state.contextTokenFile('legacy'), JSON.stringify(legacyContext));
  assert.deepEqual(await state.loadAccount('legacy'), legacy);
  assert.deepEqual(await state.loadContextTokens('legacy'), legacyContext);
  for (const id of ['new', 'legacy']) {
    for (const path of [state.accountFile(id), state.contextTokenFile(id)]) {
      const text = await readFile(path, 'utf8');
      assert.equal(text.includes(token), false);
      assert.equal(text.includes(contextToken), false);
      assert.match(JSON.parse(text).ciphertext, /^dpapi:/);
    }
  }
  const script = `
    import assert from 'node:assert/strict';
    import { WechatState } from ${JSON.stringify(new URL('../state.js', import.meta.url).href)};
    const state = new WechatState({root: process.argv[1]});
    for (const id of ['new', 'legacy']) {
      assert.equal((await state.loadAccount(id)).token, 'synthetic-windows-account-token');
      assert.equal((await state.loadContextTokens(id))['synthetic-owner'].token, 'synthetic-windows-context-token');
    }
    console.log('Four synthetic credential records reopened through current-user DPAPI.');
  `;
  const restarted = spawnSync(process.execPath, ['--input-type=module', '--eval', script, root], {
    encoding: 'utf8', timeout: 30000, windowsHide: true,
  });
  assert.equal(restarted.status, 0, restarted.stderr);
  assert.match(restarted.stdout, /Four synthetic credential records reopened/);
  const path = state.accountFile('new');
  const damaged = JSON.parse(await readFile(path, 'utf8'));
  damaged.ciphertext = 'dpapi:QUJD';
  const raw = JSON.stringify(damaged);
  await writeFile(path, raw);
  await assert.rejects(() => state.loadAccount('new'), error => {
    assert.equal(error.code, 'WECHAT_CREDENTIAL_DECRYPT_FAILED');
    assert.equal(error.retryable, true);
    assert.equal(error.cause, undefined);
    assert.equal(String(error.stack).includes(token), false);
    return true;
  });
  assert.equal(await readFile(path, 'utf8'), raw);
});

test('Windows DPAPI migrates and updates context files larger than the command-line limit, then reopens them', {
  skip: process.platform !== 'win32' ? 'Requires the current Windows user DPAPI profile' : false,
}, async t => {
  const root = await mkdtemp(join(tmpdir(), 'wechat-dpapi-large-test-'));
  t.after(() => rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 }));
  const state = new WechatState({ root });
  await state.init();
  const tokens = Object.fromEntries(Array.from({ length: 100 }, (_, index) => [
    `synthetic-peer-${index}`, { token: 'synthetic-'.repeat(29) + index, savedAt: '2026-01-01T00:00:00.000Z' },
  ]));
  const raw = JSON.stringify(tokens);
  assert.ok(Buffer.byteLength(raw, 'utf8') > 32768);
  await writeFile(state.contextTokenFile('large'), raw);
  assert.deepEqual(await state.loadContextTokens('large'), tokens);
  await state.saveContextToken('large', 'additional-peer', 'synthetic-additional-context-token');
  const protectedText = await readFile(state.contextTokenFile('large'), 'utf8');
  assert.equal(protectedText.includes('synthetic-'), false);
  const script = `
    import assert from 'node:assert/strict';
    import { WechatState } from ${JSON.stringify(new URL('../state.js', import.meta.url).href)};
    const tokens = await new WechatState({root:process.argv[1]}).loadContextTokens('large');
    assert.equal(Object.keys(tokens).length, 101);
    assert.equal(tokens['synthetic-peer-99'].token, 'synthetic-'.repeat(29) + 99);
    assert.equal(tokens['additional-peer'].token, 'synthetic-additional-context-token');
  `;
  const restarted = spawnSync(process.execPath, ['--input-type=module', '--eval', script, root], {
    encoding: 'utf8', timeout: 30000, windowsHide: true,
  });
  assert.equal(restarted.status, 0, restarted.stderr);
});
