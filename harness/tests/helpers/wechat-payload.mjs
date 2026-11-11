import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import stage from '../../packaging/stage.cjs';

// Exercise the desktop's real copy policy; this private plugin is not distributed through npm files[].
export const payloadFiles = (() => {
  const root = mkdtempSync(join(tmpdir(), 'wechat-payload-test-'));
  const payload = join(root, 'payload');
  const plugin = fileURLToPath(new URL('../../plugins/wechat/', import.meta.url));
  const harness = fileURLToPath(new URL('../../', import.meta.url));
  try {
    mkdirSync(payload);
    const manifest = [];
    stage.overlay(plugin, payload, manifest);
    for (const entry of manifest) {
      assert.deepEqual(readFileSync(join(payload, entry.target)), readFileSync(join(harness, entry.source)), entry.target);
    }
    return Object.freeze(manifest.map(entry => entry.target));
  } finally {
    rmSync(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
  }
})();
