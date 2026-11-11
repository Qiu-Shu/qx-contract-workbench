import { randomUUID } from 'node:crypto';
import fs from 'node:fs/promises';
import { CIPHER_PREFIX } from './secrets.js';

const FORMAT = 'wechat-credentials-dpapi-v1';
const isCiphertext = value => typeof value === 'string' && value.length > 0 &&
  value.length % 4 === 0 && /^[A-Za-z0-9+/]+={0,2}$/.test(value);

function failure(code) {
  // Child-process errors can include the PowerShell input; never propagate them or their cause.
  return Object.assign(new Error(`微信凭据暂时无法安全读取或保存（${code}），未覆盖现有记录，请稍后重试。`), {
    code: `WECHAT_CREDENTIAL_${code}`, retryable: true,
  });
}

function requireProtector(protector) {
  if (!protector?.available) throw failure('STORAGE_UNAVAILABLE');
}

function objectFromJson(text) {
  try {
    const value = JSON.parse(text);
    if (value && typeof value === 'object' && !Array.isArray(value)) return value;
  } catch { /* Invalid data must not be treated as an empty account. */ }
  throw failure('CORRUPT');
}

async function readRaw(path) {
  try { return await fs.readFile(path, 'utf8'); }
  catch (error) {
    if (error.code === 'ENOENT') return null;
    throw failure('READ_FAILED');
  }
}

async function reveal(envelope, protector) {
  if (envelope.format !== FORMAT || typeof envelope.ciphertext !== 'string' ||
      !envelope.ciphertext.startsWith(CIPHER_PREFIX) || !isCiphertext(envelope.ciphertext.slice(CIPHER_PREFIX.length))) {
    throw failure('CORRUPT');
  }
  requireProtector(protector);
  try { return await protector.reveal(envelope.ciphertext.slice(CIPHER_PREFIX.length)); }
  catch { throw failure('DECRYPT_FAILED'); }
}

async function replaceProtected(path, value, previous, protector, cache) {
  requireProtector(protector);
  const plaintext = JSON.stringify(value);
  let ciphertext;
  try { ciphertext = await protector.protect(plaintext); }
  catch { throw failure('ENCRYPT_FAILED'); }
  if (!isCiphertext(ciphertext)) {
    throw failure('ENCRYPT_FAILED');
  }
  const envelope = { format: FORMAT, ciphertext: `${CIPHER_PREFIX}${ciphertext}` };
  const sealed = `${JSON.stringify(envelope)}\n`;
  const temporary = `${path}.${randomUUID()}.tmp`;
  let handle;
  let created = false;
  try {
    handle = await fs.open(temporary, 'wx', 0o600);
    created = true;
    await handle.writeFile(sealed, 'utf8');
    await handle.sync();
    await handle.close();
    handle = undefined;
    // Verify the staged ciphertext, not just the protector's return, before replacing the only old copy.
    const staged = objectFromJson(await fs.readFile(temporary, 'utf8'));
    if (await reveal(staged, protector) !== plaintext) throw failure('VERIFY_FAILED');
    if (await readRaw(path) !== previous) throw failure('CHANGED');
    await fs.rename(temporary, path);
    cache.set(path, { sealed, plaintext });
  } catch (error) {
    if (String(error?.code).startsWith('WECHAT_CREDENTIAL_')) throw error;
    throw failure('WRITE_FAILED');
  } finally {
    await handle?.close().catch(() => {});
    if (created) await fs.unlink(temporary).catch(() => {});
  }
}

async function readCredentialFile(path, fallback, protector, cache) {
  const raw = await readRaw(path);
  if (raw === null) { cache.delete(path); return fallback; }
  const verified = cache.get(path);
  // Reuse only a successfully verified ciphertext; changes on disk always require another reveal.
  if (verified?.sealed === raw) return objectFromJson(verified.plaintext);
  const value = objectFromJson(raw);
  if (Object.hasOwn(value, 'format') || Object.hasOwn(value, 'ciphertext')) {
    const plaintext = await reveal(value, protector);
    const opened = objectFromJson(plaintext);
    cache.set(path, { sealed: raw, plaintext });
    return opened;
  }
  // Migration never returns the plaintext until its protected replacement is verified and committed.
  await replaceProtected(path, value, raw, protector, cache);
  return value;
}

export function createCredentialFiles(protector) {
  const cache = new Map();
  return {
    read: (path, fallback) => readCredentialFile(path, fallback, protector, cache),
    write: async (path, value) => replaceProtected(path, value, await readRaw(path), protector, cache),
    forget: path => cache.delete(path),
  };
}
