# 拓客长期验证入口

`run.mjs --run <独立证据目录>` 在真实系统时间上运行 73 小时，到期自动退出。它直接使用产品 `installContentWatch`、真实 JustOne 解析、30 秒启动计时器、60 秒检查与 72 小时业务周期，并保存真实磁盘状态。仅采集、摘要接收为本机 HTTP 合成替身；不等于完整 Harness Agent、真实账号、模型质量或生产验收。

必须使用固定 Node；TEMP/TMP 指向 D 盘。独立证据目录不可复用。正常首轮之后一小时，入口销毁并重新安装服务，核对原报告和到期时间；第二期必须由自然到期触发，完成后才显式执行一次重复整理以验证去重。不会修改系统时间、电源设置、生产周期或日常安装。

```powershell
$repo='C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目'
. "$repo/harness/.local/audit-0216/build/test-env.ps1"
$env:TEMP='D:/CodexChecks/AI-Shixiong-resilience-20261113/content/temp'
$env:TMP=$env:TEMP
$env:NODE_PATH='D:/CodexBuilds/AI-Shixiong-content-merge-20261113/stage/win-unpacked/resources/workbench/node_modules'
$node='D:/CodexBuilds/AI-Shixiong-content-merge-20261113/stage/win-unpacked/resources/workbench/runtime/node.exe'
& $node "$repo/harness/tests/content-watch-endurance/run.mjs" --run 'D:/CodexChecks/AI-Shixiong-resilience-20261113/content/real-clock-73h'
```

`--self-check` 使用原来的 30 秒启动计时器和 80 秒总时长，验证启动、持久化重开、未到期不重采、结束去重；永远记录 `threeDayVerificationComplete=false`，不得当作三天通过。

`--inspect <证据目录>` 只读 `summary.json` 并检查记录中的 PID 是否仍存在，明确返回身份尚未验证。使用 Windows CIM 另核程序路径、命令行和创建时间，避免 PID 复用误认；不能仅据旧的 `running` 状态宣称仍在运行或已经完成。输出还包含启动固定截止时间、计划/实际到期、每小时心跳数、进程内存峰值和证据年龄。

`manifest.json` 保存源文件摘要与 Node 摘要；`events.jsonl` 按事件追加启动、每小时心跳、实际执行、重开、去重和结束；`state/` 保存产品报告与状态，`summary-receipts.jsonl` 保存合成摘要接收凭据。73 小时循环和完成判断都使用单调时钟；启动时的墙上时钟截止只用于显示，系统改时不能凑满持续时间。检测到超过 45 秒的采样间隙时据实标记不能称连续运行，`passed-with-host-gaps` 与无间隙 `passed` 分开。墙上时钟与单调时钟差异超过 5 秒时另记 `clockDiscontinuities`，原因可能为改时或宿主时钟行为，最终 `inconclusive-clock-discontinuity`，不称自然三天完成。单调时长到期仍未观察到第二期则失败。

长跑同时核对前两轮各四次搜索、各一份新内容与摘要、第二轮的下次到期时间，以及结束前不存在第三次计划执行或额外采集；最后明确的手动去重请求单列，避免重复采集被“摘要没有重复”掩盖。

加速专项 `node --test tests/content-watch-endurance.test.mjs` 覆盖真实持久化与重开、十周期休眠式跳跃、真实本机连接中断与明确恢复、子进程在提交前/后真实终止及保守去重。测试时钟仅通过 core 既有依赖注入，不改生产配置。完整 Harness 会话链已有另一个入口 `tests/content-watch-harness/run.mjs`，二者证据不得混称。
