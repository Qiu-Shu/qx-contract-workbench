const ENDPOINT = 'https://api.deepseek.com/user/balance';
const MONEY = /^-?\d+(?:\.\d+)?$/;
const ERRORS = {
  not_configured: '尚未配置 DeepSeek API 密钥',
  credentials_unavailable: '暂时无法读取账户配置',
  credentials_changed: '账户配置已更新，请刷新余额',
  authentication: '余额查询认证失败，请检查 API 密钥',
  rate_limited: '余额查询过于频繁，请稍后刷新',
  upstream_unavailable: '余额服务暂时不可用',
  invalid_response: '余额服务返回的数据不完整',
  network: '暂时无法连接余额服务',
};

function failure(reason, now, status = 'error') {
  return {
    status, balances: [], isAvailable: null, updatedAt: null,
    checkedAt: new Date(now).toISOString(), cached: false,
    reason, error: ERRORS[reason],
  };
}

function parseBalances(value) {
  if (!value || typeof value.is_available !== 'boolean' ||
      !Array.isArray(value.balance_infos) || !value.balance_infos.length) return null;
  const seen = new Set();
  const balances = [];
  for (const item of value.balance_infos) {
    if (!item || !['CNY', 'USD'].includes(item.currency) || seen.has(item.currency)) return null;
    const row = {currency: item.currency};
    for (const name of ['total_balance', 'granted_balance', 'topped_up_balance']) {
      if (typeof item[name] !== 'string' || !MONEY.test(item[name])) return null;
      row[name] = item[name];
    }
    seen.add(item.currency);
    balances.push(row);
  }
  return {balances, isAvailable: value.is_available};
}

/** In-memory cache only. Never return credentials, upstream errors, or response headers. */
export function createBalanceReader({
  resolveKey, fetchImpl = fetch, clock = Date.now,
  ttlMs = 120_000, manualCooldownMs = 15_000,
}) {
  let activeKey;
  let generation = 0;
  let cached;
  let checkedAt = -Infinity;
  let flight;
  const keyNow = async () => {
    const value = await resolveKey();
    return typeof value === 'string' && value.trim() ? value.trim() : undefined;
  };

  return async function readBalance({refresh = false} = {}) {
    let key;
    try { key = await keyNow(); }
    catch { return failure('credentials_unavailable', clock(), 'unavailable'); }
    if (key !== activeKey) {
      activeKey = key;
      generation++;
      cached = undefined;
      checkedAt = -Infinity;
      flight = undefined;
    }
    if (!key) return failure('not_configured', clock(), 'unavailable');
    if (flight) return flight.promise;
    const now = clock();
    const age = now - checkedAt;
    if (cached && age >= 0 && age < ttlMs && (!refresh || age < manualCooldownMs)) {
      return {...cached, cached: true};
    }

    const requestGeneration = generation;
    const request = {};
    checkedAt = now;
    request.promise = (async () => {
      let result;
      try {
        const response = await fetchImpl(ENDPOINT, {
          method: 'GET', redirect: 'error', signal: AbortSignal.timeout(15_000),
          headers: {Authorization: `Bearer ${key}`, Accept: 'application/json'},
        });
        if (!response.ok) {
          const reason = [401, 403].includes(response.status) ? 'authentication'
            : response.status === 429 ? 'rate_limited' : 'upstream_unavailable';
          // Discard response bodies: upstream errors can contain sensitive material.
          await response.body?.cancel();
          result = failure(reason, clock());
        } else {
          let parsed;
          try { parsed = parseBalances(await response.json()); } catch { parsed = null; }
          result = parsed ? {
            status: 'ok', ...parsed, updatedAt: new Date(clock()).toISOString(),
            checkedAt: new Date(clock()).toISOString(), cached: false,
          } : failure('invalid_response', clock());
        }
      } catch { result = failure('network', clock()); }

      // Do not publish an old account's balance if credentials changed during the request.
      let latestKey;
      try { latestKey = await keyNow(); }
      catch { return failure('credentials_unavailable', clock(), 'unavailable'); }
      if (requestGeneration !== generation || latestKey !== key) {
        return failure('credentials_changed', clock(), 'unavailable');
      }
      cached = result;
      return result;
    })().finally(() => { if (flight === request) flight = undefined; });
    flight = request;
    return request.promise;
  };
}
