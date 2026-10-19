# CH-04B 独立 Standards 审阅

日期：2026-10-19（Asia/Shanghai）。工作区：`D:\Documents\ChatGPT\律所项目`。审阅角色：独立 Standards 子代理。基线：`ffe1897`；分支：`codex/contract-review-v2`。本报告仅覆盖当前未提交的受控生成 HTTP 与应用任务生命周期切片。

## 结论

本次范围内 **0 项可复现的实质 Standards 问题，0 项待修复发现**。这是受限工程审阅结论，不是生产、真实模型、法律技能、首页发送或安装验收结论。

未修改产品源码、正式测试、规格或公开状态文件，未提交或推送。独立探针、日志和报告仅写入 `.local/chat-generation-http-20261019/`；合成测试数据库使用该目录下独立 basetemp。真实材料、真实凭据、外部模型和外部网络调用均为零。

## 依据与范围

- 读取项目 `AGENTS.md`、`docs/TASK_STATUS.md` 当前状态、`sources/specification-v2.0.md` 的相关数据、权限、费用、事务、恢复与演示边界，以及 `sources/upstream.lock.json` 来源登记。
- 执行依据为 `docs/plans/2026-10-19-generation-http-execution.md` 与 `docs/plans/2026-10-17-main-model-http-readiness.md`。依当前执行记录，本片先验收后端生命周期，未要求本轮交付首页消费。
- 应用 Ponytail 的最小充分改动与信任边界原则；Fowler smell 清单仅作辅助，不把格式、短命名或工具可检查的差异虚构成问题。
- 已以实际 workspace 检索 Obsidian 和 TencentDB；检索成功，返回历史资料及项目快照。历史资料只作定位，本结论以源码和本轮规格为准，未把记忆声称的旧测试数量作为本轮证据。
- 复用已存在 `.codegraph`，原生 `codegraph_explore` 检索 `GenerationTasks`、`execute_attempt`、`enqueue_generation`、`claim`、`settle`、`_owned`、`MainModelRuntime`、`build_local_app`、`require_active`、`Database.session` 等关系。返回当前源码，无过期警告；图查询用于定位，不当成正确性证明。
- 检查 `git diff ffe1897` 中的 `domain.py`、`web/app.py`、`web/demo_server.py`、`web/local_server.py`、`web/recovery.py`，以及新增 `assistant/task_manager.py`、`web/assistant_generation.py` 和两份新增集成测试。关联阅读现有 provider/ledger、认证、存储、恢复与对话服务。审阅文件 SHA-256 见 `standards-reviewed-files.json`。

## 关键核对

|约束|核对结果与位置|
|---|---|
|业务 DTO 唯一，金额/时间精确|新增能力 DTO 位于 `src/cn_contract/domain.py:2931`；无另建业务 DTO、费用引擎或时间转换。费用继续复用既有 Decimal 计算及明确 USD 单位。|
|应用工厂只装配|`web/app.py:601` 仅装配独立模块；路由与生命周期在 `web/assistant_generation.py:60`；后台任务归属集中于 `assistant/task_manager.py:17`。|
|认证、同源、CSRF 和当前权限|`assistant_generation.py:92` 先检查身份、CSRF、归属与恢复 fence，再读取正文；正文后再次认证。能力、attempt 与 request-id 查询均经当前会话/角色/归属检查。|
|原请求和版本由后端核验|`task_manager.py:60` 重验输入；复用 `enqueue_generation`/`save_message`/`claim` 的范围、版本、政策摘要及幂等检查。历史 `/messages` 不调度，旧 queued 无 attempt 时不能升级成生成。|
|短事务与唯一调度|`task_manager.py:62` 至 `:76` 的登记事务成功退出后才创建任务；复用 `runner.py:8`，模型 await 不持有数据库 session。仅本进程新登记的 attempt 获得调度，重复请求不再次调度。|
|后台异常与费用未知|`task_manager.py:80`、`:103` 观察并收敛异常，只有固定错误码；取消复用 runner 的 `sent_unknown`，未发取消复用现有释放函数。持久化失败保留原标记，不擅自重试。|
|生命周期、worker.lock 与释放顺序|`assistant_generation.py:70`、`demo_server.py:46`、`local_server.py:215` 组合生命周期；本机锁内恢复旧任务，生成收尾先于原工作器停止和 engine dispose。独立探针覆盖此前生命周期启动及退出异常。|
|恢复 fence 优先|启动时恢复副本不启动 manager；提交与 claim/settle/释放均继续检查 fence。恢复只放行精确生成只读路径。独立探针覆盖运行时新 fence 的三个时点。|
|默认关闭与可信配置|`create_app` 和 `build_local_app` 默认 runtime 为 `None`；renderer 输入模型拒绝 policy/config/key 等额外字段。能力查询只检查受信配置和本地账目，不调用 provider 或 secret resolver。|
|材料、技能与候选边界|本机材料仍阻止外发；非空 requested_skill 拒绝普通生成替代业务技能；成果沿用内部、待核和原消息引用，不进入正式签发或覆盖原件。|
|可维护性|未新增依赖、表、进程或第二套预算/幂等机制。HTTP 模块的能力状态组合复用既有策略函数；没有发现达到实质风险程度的重复引擎、跨模块散改或职责冲突。|

## 独立实测

探针：`test_standards_probe.py`。最终实际命令：

```powershell
.\.venv\Scripts\python.exe -m pytest .local/chat-generation-http-20261019/test_standards_probe.py -q --basetemp=.local/chat-generation-http-20261019/standards-tmp-final --junitxml=.local/chat-generation-http-20261019/standards-probe-junit.xml
```

最终退出码 **0**，**6 passed**，pytest 报告 **3.13 秒**，0 失败/错误/跳过；日志 `standards-probe.log`，JUnit `standards-probe-junit.xml`。

1. 既有 lifespan 在 startup 抛错：新 manager 不准入，工作器终止后释放数据库，没有调用 provider。
2. 既有 lifespan 在 teardown 抛错：已发任务仍记录 `sent_unknown` 和回执，生成任务与工作器均结束。
3. manager 启动后、提交前新增 fence：登记被拒，没有新增 attempt 或 provider 调用。
4. 新 attempt 已提交、runner 尚未执行时新增 fence：关闭不改写恢复副本，保留 `reserved`，没有 provider 调用。
5. provider 已进入 await 后新增 fence：关闭保留原 `sending` 标记，不向恢复副本写回执/候选，不重发，并记录固定内部失败码。
6. 用真实 `DeepSeekProvider` 类但凭据解析器为禁止调用的合成探针，连续三次读取能力：状态可计算，凭据解析器调用数 0，attempt 0，无网络。

初次探针实际为 **2 failed / 4 passed，exit 1，3.21 秒**。两个失败均因独立 harness 直接组装 FastAPI/worker 时遗漏显式 `initialize_storage(database)`，未到达待测生命周期；仅修正探针初始化，未改产品。原日志和 JUnit 保留为 `standards-probe-initial-harness-failure.log` 与 `standards-probe-initial-harness-failure-junit.xml`。不得将此 harness 修正计作产品缺陷或产品 RED→GREEN。

作者报告的目标/关联测试只作背景；未将其计入本独立 6 项，也未把已阅读测试当成独立执行通过。

## 未验范围与剩余限制

本次按委派范围未运行全套、冻结构建、真实浏览器或 Electron 发送路径，未启动回环 HTTP 服务，未安装/替换应用；这些由主流程另行验证。未测试真实供应商、真实凭据、真实材料、法律质量、生产许可或动态日常授权界面；默认关闭状态继续成立。源码若在本报告后变化，应根据 `standards-reviewed-files.json` 判断哪些结论需重验。
