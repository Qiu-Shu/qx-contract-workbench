import {createBalanceReader} from './balance.mjs';

export const name = 'qx-account-balance';
export const inject = ['connection', 'credentials'];

export function apply(ctx) {
  const readBalance = createBalanceReader({
    resolveKey: async () => (await ctx.credentials.resolve('DEEPSEEK_API_KEY'))?.value,
  });
  // Harness's /api carrier authenticates the browser session and requires owner
  // principal for registered fetch routes. Do not mount this on the public web server.
  ctx.connection.fetch.register({
    path: '/api/qx-account/balance', methods: ['GET'], requestBody: 'buffered',
    fetch: async request => Response.json(await readBalance({
      refresh: new URL(request.url).searchParams.get('refresh') === '1',
    }), {headers: {'cache-control': 'no-store'}}),
  });
}
