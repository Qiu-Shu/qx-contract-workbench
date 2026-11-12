// Read-only admission probe for the already installed, pinned Promptfoo 0.125.1.
// No upstream module is imported and no real network function is provided.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');

const root = path.resolve(__dirname, '../..');
const relative = 'evals/quality-baseline/node_modules/promptfoo/dist/src/telemetry-CIqy4fSC.js';
const bytes = fs.readFileSync(path.join(root, relative));
const sha256 = createHash('sha256').update(bytes).digest('hex');
assert.equal(sha256, '36250d9ae7dfb037e357d0c1b0cbde8922b91d5225292743fadf4596a4a9a24d',
  'The distribution changed; inspect and pin its source before repeating this probe.');
const version = JSON.parse(fs.readFileSync(path.join(root, 'evals/quality-baseline/node_modules/promptfoo/package.json'), 'utf8')).version;
assert.equal(version, '0.125.1');
const source = bytes.toString('utf8');
const start = source.indexOf('var Telemetry = class {');
const end = source.indexOf('const telemetry = new Telemetry(false);');
assert(start > 0 && end > start);
const requests = [];
const context = {
  getEnvBool: key => key === 'PROMPTFOO_DISABLE_TELEMETRY',
  getEnvString: (_key, fallback) => fallback,
  getUserId: () => 'synthetic-probe-id',
  getUserAuthInfo: () => ({}),
  getPostHogClient: () => null,
  isCI: () => false,
  getRuntimeMetadata: () => ({ nodeVersion: process.version }),
  VERSION: version, AbortController, setTimeout, clearTimeout,
  TELEMETRY_TIMEOUT_MS: 1000,
  R_ENDPOINT: 'https://r.promptfoo.app/',
  logger: { debug() {} },
  fetchWithProxy: (url, options) => {
    requests.push({ url, method: options.method, body: JSON.parse(options.body) });
    return Promise.resolve({ body: { cancel() {} } });
  },
};
vm.runInNewContext(source.slice(start, end) + '\nconst p = new Telemetry(false); p.record("eval_ran", {}); p.record("eval_ran", {});', context, { timeout: 1000 });
assert.equal(requests.length, 1);
assert.equal(requests[0].body.meta.feature, 'telemetry disabled');
assert.equal(requests[0].url, 'https://r.promptfoo.app/');
console.log(JSON.stringify({
  probe: 'installed telemetry class; network function replaced by in-memory recorder',
  executedAt: new Date().toISOString(), installedVersion: version, source: relative, sha256,
  disabledTelemetryStillAttemptsRequest: true, realNetworkCalls: 0, requests,
  interpretation: 'Exit 0 confirms reproduction, not offline admission. Historical successful transmission is not established.',
}, null, 2));
