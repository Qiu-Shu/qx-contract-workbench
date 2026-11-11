# R03：个人微信凭据与关联回归验证

日期：2026-11-11。隔离目录：`C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目/harness`。基线：`b802e214`，分支：`codex/audit-0216-fixes`。运行环境：Windows、Node `v24.20.0`。仅使用独立虚构 token、临时目录和本机当前用户 DPAPI；未读取或修改真实账号资料，未登录微信、发送外部消息、调用模型、推送或安装。

## 实现

- `state.js` 中的账号及 context 文件由 `credential-files.js` 统一读写；API 仍返回原来的账号/peer 对象。磁盘文件为 `wechat-credentials-dpapi-v1` 封装，只有 DPAPI 密文，无 token 明文。
- 复用 `secrets.js` 的 Windows `CurrentUser` DPAPI。保护器不可用、新文件加密失败均拒绝保存，无明文降级。
- 旧明文先在内存加密，只把密文写入随机且独占创建的临时文件，flush 后回读并解密比对；核对原文件未改变后才原子替换。加密、验证、替换失败或替换前进程中断保留旧文件，可再次迁移。
- 除真正缺失外，损坏 JSON/密文及读取失败均抛出固定的 `WECHAT_CREDENTIAL_*` 错误，`retryable=true`，不附带系统错误 cause、命令输入或凭据。
- 串行化同一 store 实例的凭据读写/移除；缓存成功验证过的内容，但每次读取仍核对磁盘密文，修改过的文件必须重新解密。返回独立对象，调用方改动不能污染缓存。
- 独立审阅补充发现：整体 context 文件超过 Windows 命令行限制时，旧 DPAPI 传参方式必然失败。已改为通过 stdin 传 base64，命令行脚本恒定，仍使用原 DPAPI。新增真实 Windows 36,181 字节/100 个虚构 peer 的迁移、更新至 101 个 peer、独立进程重启读取。
- `session.js` 另有一行关联修复：命名错误对象的描述保留 `name`，避免 `[object Object]`；会话恢复、创建及保护历史的逻辑未改。

## RED 与初次关联失败

以下命令在上述 harness 工作目录执行。原始日志位于忽略目录 `.local/audit-0216/wechat/`。

| 命令 | 实际结果 | 原始日志 |
| --- | --- | --- |
| `node --test plugins/wechat/test/credentials.test.mjs`（实现前） | exit 1；0/20 通过，20 失败 | `credentials-red.log` |
| `node --test --test-name-pattern='temporary protector outage' plugins/wechat/test/credentials.test.mjs` | exit 1；0/1 通过，1 失败 | `credential-cache-red.log` |
| `node --test --test-name-pattern='PowerShell protection boundary' plugins/wechat/test/credentials.test.mjs` | exit 1；0/1 通过，1 失败 | `cipher-boundary-red.log` |
| `node --test --test-name-pattern='command-line limit' plugins/wechat/test/credentials-windows.test.mjs` | exit 1；0/1 通过，1 失败，迁移返回 ENCRYPT_FAILED | `large-dpapi-red.log` |
| `node plugins/wechat/test/secrets.test.mjs`（stdin 实现前） | exit 1；10 通过、2 失败 | `dpapi-stdin-red.log` |
| `node plugins/wechat/test/session.test.mjs`（修正历史策略测试后、name fallback 修复前） | exit 1；16 通过、1 失败，仍保留原 WeirdError 期望 | `session-description-red.log` |

初次执行 `node --test plugins/wechat/test/login.test.mjs plugins/wechat/test/qx-plugin.test.mjs plugins/wechat/test/qx-settings.test.mjs plugins/wechat/test/secrets.test.mjs plugins/wechat/test/tokens.test.mjs` 返回 exit 1，Node 顶层 11 通过/3 失败，详见 `related-regression.log`。三项失败均为 qx-plugin 的消息处理场景：原固定 1–1.5 秒循环不足以等待真实 PowerShell DPAPI 持久化。后续采用已验证内容缓存，并把相同业务断言的等待改为条件达到即结束、最长 30 秒；未跳过业务处理、改用明文或替换凭据 store。

## 最终专项结果

执行：

```text
node --test plugins/wechat/test/credentials.test.mjs plugins/wechat/test/credentials-windows.test.mjs plugins/wechat/test/secrets.test.mjs plugins/wechat/test/qx-stable.test.mjs
```

exit 0；Node 顶层 27/27 通过，0 失败/取消/跳过。具体为 22 项真实文件 store/可控 OS 边界测试、2 项实际 Windows DPAPI 集成、2 项持久会话保护测试，以及 `secrets.test.mjs` 的文件包装；该包装内部 12/12 场景通过，不将包装与内部数量重复相加。原始日志：`final-credentials.log`。`secrets.test.mjs` 的旧自定义 runner 已改为真正 await 异步测试后计数。

此前 7 文件关联专项 `final-focused.log` 为 exit 0、Node 顶层 36/36；其中 login、secrets、tokens 为自定义文件包装，内部各为 15、11、16 项。当时尚未加入 stdin 的第 12 项 secrets 测试，因此该日志只作为阶段证据。

stdin 修改后另执行：

```text
node --test plugins/wechat/test/login.test.mjs plugins/wechat/test/qx-plugin.test.mjs plugins/wechat/test/qx-settings.test.mjs plugins/wechat/test/feishu-inbound.test.mjs
```

exit 0；Node 顶层 13/13 通过，0 失败/取消/跳过。其中 qx-plugin 为 7 项、qx-settings 为 4 项，login/feishu 各为一个文件包装，其内部各为 15/17 个场景且全部通过。原始日志 `final-callers.log`。

`node --check` 对 `credential-files.js`、`secrets.js`、`state.js` 均为 exit 0；`git diff --check -- plugins/wechat tests/helpers/wechat-payload.mjs` 为 exit 0。

## R05 微信旧测试的核对与修正

全量初跑日志 `.local/audit-0216/build/offline-01.log` 显示以下旧断言不符合当前产品。没有靠删除文件或跳过测试处理：

- dialogs/email/flow/maps/qq-bot/scrapling/vscode/wiring/package 仍把上游 npm `files[]` 当作打包来源。现在由 `tests/helpers/wechat-payload.mjs` 执行真实 `stage.overlay`，核对复制文件的字节后提供实际 payload 集合；原必需模块、资源和入口依赖断言保留，新 DPAPI helper 也被显式检查。
- package 的旧包名、client export、patch id 改为当前私有 `@qunxing/personal-wechat`、`qx-plugin.js`、`qx-personal-wechat`。保留模块解析、导出、文档、资源及无凭据 patch 的检查。
- 保留的上游 deploy 脚本版本与 `sources/wechat-sources.json` 的 `1.24.13` 核对，不再与本地私有包 `0.1.0` 比较。未执行该部署脚本。
- Feishu 的版本时间测试按无 npm files[] 时的实际目录文件集合核对，保留修改文件时间后再次读取的验证。
- session 的旧“恢复失败就生成新会话”断言与现行历史保护规则冲突，改为只有被分类为缺失才能创建相同 ID，损坏/歧义/占用拒绝创建或另起 ID；元数据与 setup 传递断言保留。真实 name 描述退化单独先 RED 再修。

执行：

```text
node --test plugins/wechat/test/dialogs.test.mjs plugins/wechat/test/email.test.mjs plugins/wechat/test/feishu-inbound.test.mjs plugins/wechat/test/flow.test.mjs plugins/wechat/test/maps.test.mjs plugins/wechat/test/package.test.mjs plugins/wechat/test/qq-bot.test.mjs plugins/wechat/test/scrapling.test.mjs plugins/wechat/test/session.test.mjs plugins/wechat/test/smoke.test.mjs plugins/wechat/test/vscode.test.mjs plugins/wechat/test/wiring.test.mjs
```

exit 0；12/12 文件包装通过。自定义 runner 内部分别为 9、22、17、13、5、12、10、8、17、4、7、94 个场景（合计 218），均通过；原始日志 `legacy-regression-green.log`。这些测试包含保留上游模块的检查，不能据此宣称其所有集成渠道都已成为当前支持产品。

## R05 收尾：Office 自定义 runner 漏等待

`office.test.mjs` 前 9 个静态/注入边界场景调用异步 `test()` 后未等待，默认没有工具链时会先 `process.exit(0)`，导致 `0 passed, 0 failed, 1 skipped` 的假空跑。仅给这 9 处调用补 `await`，产品 `office.js`、实时场景与跳过条件均未修改。

未设置 `DSH_OFFICE_PYTHON`，执行 `node plugins/wechat/test/office.test.mjs`：修改前脚本 exit 0，但“必须实际完成 9 项”审计断言 exit 1（`office-await-before.log`）；修改后 exit 0，明确 **9 passed, 0 failed, 1 skipped**，同一审计断言 exit 0（`office-await-after.log`）。跳过的是缺少 bundled Python 的 live roundtrip，不是静态场景。`git diff --check -- plugins/wechat/test/office.test.mjs` 为 exit 0。

构建代理额外使用现有业务 Python 的结果保留在 `.local/audit-0216/build/office-live.log`：10 passed、1 failed、1 skipped；DOCX 真实往返通过，XLSX 因缺少 `openpyxl` 失败，后续 PPTX 没有执行到，PDF 因缺 LibreOffice Kit 跳过。没有安装新依赖，也不据默认离线通过宣称完整 Office 往返通过。

## R05 最后四个尾部场景

独立复核又定位 `plain-text`、`qq-bot`、`feishu`、`retry` 的末尾 `test()` 未 await。只给四处调用补 await，并在 QQ 最后回调补其原先缺失的局部 `node:fs` 导入；产品与业务断言均未修改。

失败注入在忽略目录 `.local/audit-0216/wechat/await-probes/` 的临时测试副本进行，源码没有留下注入。各副本只把末尾回调设为异步，在一次 Promise 让出后抛出 `SYNTHETIC_LATE_ASYNC_FAILURE`。修改前四个副本均错误地 exit 0（分别 15/10/28/5 passed、0 failed），审计断言因此 exit 1；修改后四个副本都记录该错误并 exit 1（分别 15/10/28/5 passed、1 failed），审计断言 exit 0。原始输出为该目录各名称的 `*-before.log`、`*-after.log`。

正常执行 `node --test plugins/wechat/test/plain-text.test.mjs plugins/wechat/test/qq-bot.test.mjs plugins/wechat/test/feishu.test.mjs plugins/wechat/test/retry.test.mjs` 为 exit 0：四个文件包装全部通过，内部场景分别 **16、11、29、6**（合计 62），0 failed/skip。日志：`final-tail-await.log`。前述阶段日志中的 QQ 10 项计数应按该阶段实际输出保留，不能据旧计数声称当时最后一项已经执行。四文件 `git diff --check` 为 exit 0。

## 验证边界

真实 DPAPI 仅验证当前 Windows 用户；没有跨用户/跨机器凭据恢复、真实微信扫码与收发、真实客户数据、NSIS 安装或生产发布验收。中断测试为子进程在密文已暂存、原件尚未替换时退出，OS 边界使用虚构保护器；真实 DPAPI 集成另测。迁移失败保留的旧文件依然是旧明文，成功迁移前不会被当作已保护。未删除历史备份、做安全擦除，也未扩展偏好文件/企业微信凭据的既有保护政策。同实例并发已经测试；没有宣称跨多个应用进程同时写同一目录的事务保证。全产品最终测试入口及独立审阅由主任务汇总。
