// Read-only live verification. No model turn, no message, no credential or amount logging.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const runtime = JSON.parse(await fs.readFile(path.join(root, '.local/runtime.json'), 'utf8'));
const launch = new URL(runtime.url);
if (!['127.0.0.1', 'localhost', '[::1]'].includes(launch.hostname)) throw Error('Expected local host');
const endpoint = new URL('/api/qx-account/balance', launch.origin);
const cookies = new Map();
const request = async url => {
  const parsed = new URL(url, launch.origin);
  if (parsed.origin !== launch.origin) throw Error('Cross-origin redirect refused');
  const response = await fetch(parsed, {redirect: 'manual', signal: AbortSignal.timeout(25_000),
    headers: {Origin: launch.origin, Cookie: [...cookies].map(([k,v]) => `${k}=${v}`).join('; ')}});
  for (const value of response.headers.getSetCookie()) {
    const pair = value.split(';', 1)[0];
    const at = pair.indexOf('=');
    cookies.set(pair.slice(0, at), pair.slice(at + 1));
  }
  return response;
};

try {
  const anonymous = await request(endpoint);
  const anonymousBody = await anonymous.text();
  cookies.clear();
  let bootstrap = await request(launch);
  for (let i = 0; i < 3 && bootstrap.status >= 300 && bootstrap.status < 400; i++) {
    const location = bootstrap.headers.get('location');
    await bootstrap.body?.cancel();
    bootstrap = await request(location || '/');
  }
  await bootstrap.body?.cancel();
  if (bootstrap.status !== 200) throw Error(`Bootstrap HTTP ${bootstrap.status}`);
  const first = await request(endpoint);
  if (first.status !== 200) throw Error(`Authenticated endpoint HTTP ${first.status}`);
  const result = await first.json();
  const second = await request(endpoint);
  const repeated = await second.json();
  const valid = row => ['CNY','USD'].includes(row.currency) &&
    ['total_balance','granted_balance','topped_up_balance'].every(k => typeof row[k] === 'string' && /^-?\d+(?:\.\d+)?$/.test(row[k]));
  const report = {
    checkedAt: new Date().toISOString(),
    anonymousStatus: anonymous.status,
    anonymousHasNoBalance: !anonymousBody.includes('total_balance'),
    authenticatedStatus: first.status,
    serviceStatus: result.status,
    provider: 'DeepSeek official user/balance',
    balanceCount: result.balances?.length ?? 0,
    currencies: (result.balances ?? []).map(row => row.currency),
    monetaryStringsValid: result.balances?.length > 0 && result.balances.every(valid),
    isAvailable: result.isAvailable,
    updatedAtPresent: typeof result.updatedAt === 'string',
    cacheControl: first.headers.get('cache-control'),
    repeatCached: repeated.cached === true,
    sameCheckedAt: repeated.checkedAt === result.checkedAt,
    noModelRequest: true,
    ...(result.reason ? {reason: result.reason} : {}),
  };
  report.passed = report.anonymousStatus === 401 && report.anonymousHasNoBalance &&
    report.serviceStatus === 'ok' && report.monetaryStringsValid && report.repeatCached && report.sameCheckedAt;
  const directory = path.join(root, 'docs/checks/account');
  await fs.mkdir(directory, {recursive: true});
  await fs.writeFile(path.join(directory, 'actual-host-check.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
  if (!report.passed) process.exitCode = 1;
} catch (error) {
  // Only our fixed HTTP messages are safe to emit; never log Fetch errors or request URLs.
  const message = /^(Bootstrap|Authenticated endpoint) HTTP \d+$/.test(error.message)
    ? error.message : 'Local live verification failed';
  console.error(message);
  process.exitCode = 1;
}
