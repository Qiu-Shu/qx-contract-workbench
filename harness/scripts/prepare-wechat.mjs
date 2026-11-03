// Register this workspace and materialize its shared empty session; no turn is submitted.
const origin = new URL(process.argv[2] || 'http://127.0.0.1:3080');
if (!['127.0.0.1', '[::1]'].includes(origin.hostname) || origin.protocol !== 'http:' || origin.pathname !== '/' || origin.username || origin.password) {
  throw new Error('只接受本机 Harness 的 HTTP 根地址');
}
const panel = await fetch(new URL('/qx-wechat', origin), {signal:AbortSignal.timeout(15000)});
if (!panel.ok) throw new Error(`微信设置页不可用：HTTP ${panel.status}`);
const token = (await panel.text()).match(/'x-qx-token':'([^']+)'/)?.[1];
if (!token) throw new Error('微信设置页缺少本机操作令牌');
const response = await fetch(new URL('/qx-wechat/action', origin), {
  method:'POST', headers:{'content-type':'application/json','x-qx-token':token},
  body:JSON.stringify({action:'prepare'}),signal:AbortSignal.timeout(30000),
});
const result = await response.json();
if (!response.ok || !result.ok) throw new Error(result.error || `会话初始化失败：HTTP ${response.status}`);
const status = await fetch(new URL('/qx-wechat/state',origin), {signal:AbortSignal.timeout(15000)}).then(response=>response.json());
console.log(JSON.stringify({sessionId:status.sessionId,workspace:status.workspace,connected:status.connected,turnsForwarded:status.forwarded,prepared:true}));
