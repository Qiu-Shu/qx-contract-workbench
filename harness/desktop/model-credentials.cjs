const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const MAX_CIPHERTEXT_BYTES = 65536;
const CREDENTIAL_FORMAT = 'qunxing-model-credential-v1';
const UNSAFE_PATH = Symbol('unsafe credential path');

function validSecret(secret) {
  return typeof secret === 'string' && secret.length <= 1024 && /^[\x20-\x7e]*$/.test(secret) &&
    secret.trim().length >= 16 && secret.trim().length <= 512;
}

function protectedSecret(text, provider) {
  if (typeof text !== 'string' || text.length > 2048) return null;
  let envelope;
  try { envelope = JSON.parse(text); } catch { /* Legacy DeepSeek keys are plain strings. */ }
  if (provider === 'deepseek') {
    // Never treat a copied provider-bound envelope as a legacy main-model key.
    if (envelope?.format === CREDENTIAL_FORMAT) return null;
    return validSecret(text) ? text.trim() : null;
  }
  if (!envelope || !validSecret(envelope.secret) || envelope.secret !== envelope.secret.trim()) return null;
  const expected = { format: CREDENTIAL_FORMAT, provider, secret: envelope.secret };
  // Our canonical encoding also rejects duplicate/extra keys and foreign versions.
  return JSON.stringify(expected) === text ? envelope.secret : null;
}

function createModelCredentialStore({ dataParent, safeStorage, platform = process.platform, provider = 'deepseek' }) {
  if (provider !== 'deepseek' && provider !== 'typesafe') throw new TypeError('CREDENTIAL_PROVIDER_INVALID');
  const absolute = typeof dataParent === 'string' && path.isAbsolute(dataParent);
  const parts = absolute ? dataParent.slice(path.parse(dataParent).root.length).split(/[\\/]/).filter(Boolean) : [];
  const validParent = absolute && !/^[\\/]{2}/.test(dataParent) && parts.every(part =>
    !/[<>:"|?*\x00-\x1f]/.test(part) && !/[. ]$/.test(part) &&
    !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part));
  const directory = validParent ? path.join(dataParent, 'model-credentials') : null;
  const file = validParent ? path.join(directory, provider === 'deepseek' ? 'deepseek.bin' : 'typesafe.bin') : null;
  let pending = Promise.resolve();
  const unavailable = () => ({ status: 'unavailable', code: 'CREDENTIAL_STORAGE_UNAVAILABLE' });
  const failed = () => ({ status: 'unavailable', code: 'CREDENTIAL_STORAGE_FAILED' });
  const corrupt = () => ({ status: 'invalid', code: 'CREDENTIAL_CORRUPT' });
  const serial = (operation) => {
    const result = pending.then(operation).catch(error => error === UNSAFE_PATH
      ? { status: 'invalid', code: 'CREDENTIAL_PATH_UNSAFE' }
      : failed());
    pending = result.then(() => undefined);
    return result;
  };
  async function available() {
    try {
      return platform === 'win32' && safeStorage &&
        typeof safeStorage.isAsyncEncryptionAvailable === 'function' &&
        typeof safeStorage.encryptStringAsync === 'function' &&
        typeof safeStorage.decryptStringAsync === 'function' &&
        await safeStorage.isAsyncEncryptionAvailable() === true;
    } catch { return false; }
  }
  function statOrMissing(target) {
    try { return fs.lstatSync(target); }
    catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  }
  function checkDirectories(create = false) {
    if (!validParent) throw UNSAFE_PATH;
    const ancestors = [];
    for (let current = directory; ; current = path.dirname(current)) {
      ancestors.unshift(current);
      if (path.dirname(current) === current) break;
    }
    for (const current of ancestors) {
      let stat = statOrMissing(current);
      if (!stat && create) {
        fs.mkdirSync(current, { mode: 0o700 });
        stat = fs.lstatSync(current);
      }
      if (stat && (stat.isSymbolicLink() || !stat.isDirectory())) throw UNSAFE_PATH;
    }
  }
  function regular(stat) {
    if (stat && (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1)) throw UNSAFE_PATH;
    return stat;
  }
  function inspectFile() {
    checkDirectories();
    return regular(statOrMissing(file));
  }
  function sameFile(left, right) {
    return left === right || Boolean(left && right && left.dev === right.dev && left.ino === right.ino &&
      left.size === right.size && left.mtimeMs === right.mtimeMs && left.ctimeMs === right.ctimeMs);
  }
  function unchanged(before) {
    if (!sameFile(before, inspectFile())) throw UNSAFE_PATH;
  }
  function readCiphertext(before) {
    const fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
    try {
      const opened = regular(fs.fstatSync(fd));
      if (!sameFile(before, opened)) throw UNSAFE_PATH;
      if (opened.size === 0 || opened.size > MAX_CIPHERTEXT_BYTES) return null;
      const bytes = Buffer.alloc(opened.size);
      let offset = 0;
      while (offset < bytes.length) {
        const read = fs.readSync(fd, bytes, offset, bytes.length - offset, offset);
        if (!read) return null;
        offset += read;
      }
      if (!sameFile(opened, regular(fs.fstatSync(fd)))) throw UNSAFE_PATH;
      unchanged(before);
      return bytes;
    } finally { fs.closeSync(fd); }
  }
  function replaceCiphertext(bytes, before) {
    checkDirectories(true);
    unchanged(before);
    const temporary = path.join(directory, `${randomUUID()}.tmp`);
    let created;
    let fd;
    try {
      fd = fs.openSync(temporary, 'wx', 0o600);
      created = regular(fs.fstatSync(fd));
      fs.writeFileSync(fd, bytes);
      fs.fsyncSync(fd);
      created = regular(fs.fstatSync(fd));
      fs.closeSync(fd);
      fd = undefined;
      unchanged(before);
      if (!sameFile(created, regular(statOrMissing(temporary)))) throw UNSAFE_PATH;
      fs.renameSync(temporary, file);
    } finally {
      if (fd !== undefined) fs.closeSync(fd);
      // Cleanup only our own temporary file; a changed path must never be followed.
      if (created) {
        try {
          checkDirectories();
          const remaining = regular(statOrMissing(temporary));
          if (remaining && remaining.dev === created.dev && remaining.ino === created.ino) fs.unlinkSync(temporary);
        } catch { /* An unsafe replacement is left untouched. */ }
      }
    }
  }
  async function readProtected(consumer) {
    if (platform !== 'win32') return unavailable();
    inspectFile();
    if (!await available()) return unavailable();
    const before = inspectFile();
    if (!before) return { status: 'empty' };
    const bytes = readCiphertext(before);
    if (!bytes) return corrupt();
    let decrypted;
    try {
      decrypted = await safeStorage.decryptStringAsync(bytes);
    } catch (error) {
      return error?.isTemporarilyUnavailable === true ? unavailable() : corrupt();
    }
    unchanged(before);
    if (!decrypted || typeof decrypted.shouldReEncrypt !== 'boolean') return corrupt();
    const secret = protectedSecret(decrypted.result, provider);
    if (secret === null) return corrupt();
    if (decrypted.shouldReEncrypt) return { status: 'unavailable', code: 'CREDENTIAL_ROTATION_REQUIRED' };
    if (consumer) await consumer(secret);
    return { status: 'saved' };
  }
  return Object.freeze({
    status: () => serial(() => readProtected()),
    // Trusted main-process consumption only; callback results never cross this boundary.
    withSecret: consumer => serial(() => typeof consumer === 'function' ? readProtected(consumer)
      : { status: 'invalid', code: 'CREDENTIAL_INPUT_INVALID' }),
    save: (secret) => serial(async () => {
      if (platform !== 'win32') return unavailable();
      if (!validSecret(secret) || (provider === 'deepseek' && protectedSecret(secret, provider) === null)) {
        return { status: 'invalid', code: 'CREDENTIAL_INPUT_INVALID' };
      }
      inspectFile();
      if (!await available()) return unavailable();
      const before = inspectFile();
      let bytes;
      const plaintext = provider === 'deepseek' ? secret.trim()
        : JSON.stringify({ format: CREDENTIAL_FORMAT, provider, secret: secret.trim() });
      try { bytes = await safeStorage.encryptStringAsync(plaintext); }
      catch (error) { return error?.isTemporarilyUnavailable === true ? unavailable() : failed(); }
      unchanged(before);
      if (!Buffer.isBuffer(bytes) || bytes.length === 0 || bytes.length > MAX_CIPHERTEXT_BYTES) return failed();
      replaceCiphertext(bytes, before);
      return { status: 'saved' };
    }),
    remove: () => serial(async () => {
      if (platform !== 'win32') return unavailable();
      if (inspectFile()) fs.unlinkSync(file);
      return { status: 'empty' };
    }),
    drain: () => pending
  });
}

module.exports = { createModelCredentialStore };
