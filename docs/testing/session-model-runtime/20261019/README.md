# CH-04E 会话授权与固定运行快照：实际证据

2026-10-19，基线 `4435396`，沿 `codex/contract-review-v2` 完成。新增的是受信任服务端运行接口；当前生产桌面仍使用空 runtime，尚未接通原生凭据到后端的管道、日常发送授权或真实模型。测试只使用独立合成工作区与随机本机回环端口。

## 实际改动

- 新 `assistant/providers/registry.py` 管理配置版本和 workspace/user/session 三者绑定的当前授权。每次成功配置变更都使旧授权失效；撤销后重新授予相同授权，也不能复活旧任务。相同 policy ID 改内容被拒绝，费用继续由原数据库账本累计。
- `GenerationTasks` 在已有权限事务中只解析一次运行快照；登记、claim、供应商调用和结果采纳使用同一供应商、配置与授权身份。旧 `MainModelRuntime` 可信装配入口保留兼容；新会话隔离适用于 registry 路线，不能把旧全局 runtime 的兼容入口称为已改成会话授权。
- 注册表首次解析后绑定应用事件循环，后续配置、授权及使用拒绝工作线程或另一循环。最终检查与短事务之间不跨异步等待；已有登录、案件权限、版本、取消及恢复隔离仍由数据库复核。
- 尚未 claim 的失效任务可以证明未发，记 `not_sent`；已 claim 的未知情况保留额度，收到的真实合成回执仍按旧配置记录，过期候选不进入成果。读取、保存、重放及重启不自动补发。
- 注册表独立成模块，主应用文件、数据库 schema、桌面文件及运行依赖未修改。没有新增第二套队列、公开配置/授权接口或隐式模型启用。

## 最终结果

| 验证 | 实际结果 |
|---|---|
| 关联回归 | **331 个不同用例通过**，0 失败/错误/跳过，exit 0，JUnit 164.468 秒；收集与逐项结果一致。新增 37 个注册表用例及 16 个 HTTP/回环用例已包含其中，不重复相加。 |
| 回归输入 | 472 份明确选择的源码、测试、配置输入在最终运行前后及归档时摘要一致。 |
| 独立复核 | 8 项额外服务/账本攻击探针通过，exit 0，4.120 秒，13 份审查输入前后一致；未发现本片阻断缺陷。供应商是内存合成对象。 |
| HTTP 与回环 | 真实 `build_local_app` 的 ASGI TestClient 身份、生命周期、SQLite 事务，连接真实 `127.0.0.1` 随机端口假供应商。验证会话隔离、共享额度、配置/撤权 ABA、旧费率回执、取消、恢复及不补发。应用侧不是浏览器或独立 HTTP 进程。 |
| 新 Windows 冻结后端 | 真实新 EXE 完成启动/登录/默认生成拒绝、父管道关闭退出及端口释放、schema/标记/SQLite 完整性共 3 组；0 attempts/receipts/outputs，exit 0。 |
| 构建输入 | 最终 210 份构建输入前后和回归最终源码一致。保留 4 条可选导入警告：tzdata、pysqlite2、MySQLdb、psycopg2。 |
| 开发检查 | 默认配置、来源、依赖、schema 四门 exit 0；13 来源仍未生产批准，55 运行依赖及 1 构建依赖核对通过。 |

这是受影响模块回归，不是重跑全仓验收；此前 2,350、223、35 等数量属于各自历史阶段。没有重新运行未改动的 Electron 界面、原生加密或安装器测试，不宣称本片降低包体或内存。冻结 ready 的单次 1.574 秒仅为观测，不是性能验收。

关键实测包括：另一登录会话借用旧 lease 时 0 消息/attempt；跨会话共用 policy 仍共用 calls/金额预算；费率更换为 100 倍也不改旧回执计价；撤销一会话不丢弃另一会话的候选；claim 后立即撤权即使探针供应商未调用，也保守记录 unknown 并占原额度；重建 registry 后不能通过历史同 policy ID 扩大预算。

## 修正与未采用的中间结果

- 根代理先运行两项边界探针，旧登记/claim 忽略 `snapshot_for`，均失败；接线后两项通过。首个 GREEN 将异常判断从错误文本匹配修正为固定 `ServiceError.code`，未放松“必须拒绝”的断言。
- 注册表最初缺模块为 1 个收集错误、0 项执行，不称为已执行失败测试。随后新增反例发现畸形 DTO 可能通过 Pydantic 序列化 warning 反射值；禁止该 warning 后仍强校验，最终 37 项通过且 0 warnings。
- HTTP 测试先 14 项通过；新增取消探针遗漏现有必填 request_id，导致 15 通过/1 失败。修正测试构造后 16 项通过，未因此修改产品。
- 第一轮冻结编译 exit 0，但构建中 registry 完成上述补强，输入一致性检查拒绝该轮，未执行其 smoke。`initial-*` 仅作历史证据；重新构建后摘要一致，最终 EXE 才计入通过。
- 两个新正式测试在最终 331 项回归前统一为 Git 默认 LF，只有换行变化；agent 早期报告的测试摘要描述其当时字节。最终执行以 `regression-source-*.json` 为准。

## 证据和复现边界

[汇总](summary.json)、[最终命令](regression-command.json)、[JUnit](regression.xml)、[前摘要](regression-source-before.json)/[后摘要](regression-source-after.json)、[独立审查](review-report.md)、[HTTP 验证清单](http-verification.json)、[冻结回执](frozen-backend-smoke.json)、[构建日志](frozen-build.log)均随本记录保存。

原始执行目录 `.local/session-model-runtime-20261019/` 中：

```powershell
.venv/Scripts/python.exe .local/session-model-runtime-20261019/phase_checks.py regression
.venv/Scripts/python.exe .local/session-model-runtime-20261019/phase_checks.py gates
.venv/Scripts/python.exe .local/session-model-runtime-20261019/phase_checks.py build
```

归档的验证脚本保持原始路径语义，不应在证据目录直接运行并期待生成物存在。后续复验使用新的独立目录；本轮最终回归 session 77559、最终构建 session 84801 均已完成，无活动任务需要等待或重复启动。原始合成数据库、密钥哨兵、完整构建程序不入 Git。

`git-byte-differences.json` 单独记录 20 份既有工作树 CRLF 与暂存 LF 的差别，逐字节核对只有换行不同；本片改动的产品和正式测试与暂存字节完全一致。`manifest.json` 仅证明这些证据文件的字节完整，不代替功能验证。

WorkBuddy 本轮状态为 busy/unknown，未派发新任务、未清状态或自动重试，也未把历史回执作为本轮连接。使用已获授权的子智能体完成独立实现与复核。详情见 [本轮状态](workbuddy-status.json)。

下一片接原生凭据到后端的受信任控制管道及明确发送授权：由应用循环装配新 provider，不能改旧 provider 的密钥解析器；配置保存不产生外发权限。继续使用既有设置页、当前草稿摘要、会话身份、预算账本及首页；Jev、自动档案、阿里云和未下载年份仍是后续工作。本片未修改安装版 0.4.1、真实材料或 F 盘法库，未推送、付费或部署。
