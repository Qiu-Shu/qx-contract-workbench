# 群兴余额接口

此插件使用 DeepSeek 官方只读 `GET https://api.deepseek.com/user/balance`，不发送模型请求。官方接口说明：<https://api-docs.deepseek.com/zh-cn/api/get-user-balance/>。

Harness 自带的账户余额控制器依赖平台登录授权；本机使用 API 密钥，因此这里复用 `credentials.resolve('DEEPSEEK_API_KEY')` 和 `connection.fetch.register`。路由在官方 `/api` 通道内，先执行浏览器登录、Host/Origin 和 owner 权限检查，不另开公开 HTTP 入口。

## 挂载

由主配置维护者追加插件入口，保留现有插件和用户配置：

```yaml
- id: qx-account-balance
  name: D:/qx-harness-workbench-20261102/plugins/account/index.mjs
```

接口为 `GET /api/qx-account/balance`；手动刷新使用 `?refresh=1`。正常缓存 120 秒，手动刷新最短间隔 15 秒，并发请求合并。缓存仅存内存，密钥变化会清除缓存；请求途中密钥变化时不返回旧账户余额。接口响应设置 `Cache-Control: no-store`。

```json
{
  "status": "ok",
  "balances": [{"currency": "CNY", "total_balance": "0.00", "granted_balance": "0.00", "topped_up_balance": "0.00"}],
  "isAvailable": false,
  "updatedAt": "2026-11-03T00:00:00.000Z",
  "checkedAt": "2026-11-03T00:00:00.000Z",
  "cached": false
}
```

金额保留官方字符串；零余额仍为 `status: ok`。未配置返回 `unavailable`，查询失败返回 `error`，并附闭集 `reason` 与中文 `error`，两者都返回空 `balances`、`isAvailable: null`、`updatedAt: null`。密钥、来源、原始错误或上游正文不会返回给界面或写日志。

验证：`node --test plugins/account/test/*.test.mjs`。真实接口核验由本机已登录会话读取一次，不能将测试桩结果当作真实余额。
