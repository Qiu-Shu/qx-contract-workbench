# CH-04G 模型设置界面子任务

2026-10-19，工作目录 `D:\Documents\ChatGPT\律所项目`。仅修改 `desktop/setup-model.js`、`setup.js`、`setup.html`、`setup.css` 和 `desktop/tests/model-settings.test.cjs` 的 page harness / UI 用例。未改主进程、preload、会话模块、package 或原 native 测试前半；前缀与 HEAD 比较相同。未提交。

## 结果

独立模型页控制器 `createModelSettingsUI({api,document,window})` 提供 `render(state)` 与 `leave()`；主入口从原 98 行缩为 54 行。已有本机密钥管理保留，新增本次运行状态、固定模型选择、配置/切换/停用与独立错误提示。

凭据读取/保存/移除完成后才读取 runtime，复用主进程共享锁；配置仅传 `deepseek-flash` 或 `deepseek-v4-pro`，无 endpoint、价格、预算或授权参数。保存不自动配置，配置不发送；成功明确显示尚未授权发送。凭据变更开始即撤掉过时的“已配置”展示，随后读回真实状态。动作期间禁用并防重复调用；离页、故障后重开与页面关闭均使迟到结果失效，不清掉新页面输入。

模型价格、接收方和输入/输出限制置于可展开说明。沿用既有系统字体与中文设置布局；select 使用原生控件，保留 focus-visible、label、状态播报与错误 alert；按钮可换行，未加视觉库或额外网络资源。

## 测试证据

两轮先失败再实现：

- `ui-red-status.log` / `.exit`：新增串行读取能力用例 1 failed，exit 1；旧实现未读取 runtime。
- `ui-green-status.log` / `.exit`：该用例及 5 项既有 UI 用例共 6 PASS，exit 0。
- `ui-red-runtime.log` / `.exit`：配置/切换、清过时配置、异常恢复、迟到配置隔离 4 failed，exit 1；配置按钮尚无动作，以及凭据变更仍展示旧配置。
- `ui-green-runtime.log` / `.exit`：10 PASS，exit 0。
- 最终补充恢复副本/重启状态、未知模型和错误投影，`ui-final.log` / `.exit`：**12 PASS，0 fail，79.6538 ms，exit 0**；其中既有 UI 用例 5、新增 7。

最终执行：

```powershell
node --test --test-name-pattern='credential form|credential errors|credential remove|unavailable settings|late old settings|model page' desktop/tests/model-settings.test.cjs
node --check desktop/setup-model.js
node --check desktop/setup.js
git diff --check -- desktop/setup-model.js desktop/setup.js desktop/setup.html desktop/setup.css desktop/tests/model-settings.test.cjs
```

语法与 diff 检查均 exit 0；diff 仅提示 setup.css 既有 CRLF 在未来 Git 操作会规范为 LF。5 项输入完整 SHA-256 在 `ui-source-sha256.json`，主控制器 SHA `a10fcb0210062ae8b9538ab6eaf096baaabdd13f531ca02a2963bbdf57abb79d`。

本子任务未运行完整桌面回归、实际 Electron 或截图；根代理统一执行实际设置生命周期与 320 CSS px / 缩放视觉验收。VM UI 通过不代表真实 OS 密钥或真实模型已连接。用户授权/预算和发送确认仍属于 CH-04H。
