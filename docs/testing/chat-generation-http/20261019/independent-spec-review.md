# CH-04B 独立 Spec / Security 审阅

日期：2026-10-19。固定基线 `ffe1897`，对照已批准 v2.1、`docs/plans/2026-10-17-main-model-http-readiness.md`、`docs/plans/2026-10-19-generation-http-execution.md`。阅读新 `assistant/task_manager.py`、`web/assistant_generation.py` 及 domain/app/demo_server/local_server/recovery 差异，追踪既有 service/attempts/runner/current-auth/fence 实现。只写本证据目录，未修改产品/正式测试，无外部模型、真实凭据、真实材料或 WorkBuddy。

## Standards

新 DTO 集中在 domain；应用工厂只装配，模型网络任务与 HTTP 分离。沿用原预算、claim、授权和账本，没有第二套费用引擎。维护栅栏仍优先于后台关停回写；后台异常仅以固定码观察。恢复白名单严格 fullmatch，新的三个只读入口均重新验证当前身份和归属。未发现独立 Standards 残余问题。

## Spec / Security

三处计划时序已逐项核对：worker 外层/generation 内层，关停先 drain 再停止 worker/释放数据库；同一 BEGIN IMMEDIATE 事务识别并提交新 attempt，历史及重复请求无调度；首次 runner 执行前取消通过自有任务回调释放确定未发的预占。capability 在生命周期事件循环读取 task 状态。模型/未接通技能/附件/旧 queued 的边界保持。

**P2 已独立关闭：模型请求字节上限错误未转换为固定客户端错误。当前 Standards / Spec 残余均为 0。**

- 位置：`src/cn_contract/web/assistant_generation.py:103`、`src/cn_contract/assistant/task_manager.py:75`；底层 `main.build_request` 的 `ValueError('main request byte limit')` 直接上冒。
- 最小反例：受信合成政策登记 20,000 个非 BMP 字符正文摘要，其他配置保持默认。正文合法通过 AssistantMessageInput 和 HTTP 256 KiB 上限，但 UTF-8 正文已 80,000 字节，超过默认 65,536 字节完整 wire 上限。POST /generations 返回 `500 Internal Server Error`，没有项目固定错误 DTO。
- 无越权发送或残留行：反例已先断言消息/attempt 都为 0、provider 调用为 0。问题是可预期输入拒绝落入服务器异常链；应窄转换相关验证失败为固定非重试 4xx，保持事务回滚，不捕获所有异常掩盖持久层故障。
- 独立反例：`test_independent_spec_probes.py::test_approved_text_over_wire_byte_cap_returns_fixed_client_error`。`independent-wire-cap-red.xml` / `.log`：退出码 1，1 failed / 7 deselected，1.58 秒。
- 修复后只复跑原反例，未修改反例断言：`independent-wire-cap-green.xml` / `.log`，退出码 0，1 passed / 7 deselected，1.38 秒。实际返回固定客户端错误且消息/attempt/provider 仍为 0。源码独立检查确认仅在 HTTP `tasks.submit` 边界捕获 `ValueError`，转换 `STATE_CONFLICT 422`，事务由原 manager 上下文回滚；没有吞并数据库等全部异常。修后文件摘要见 `independent-wire-cap-fixed-source.json`。本项关闭。

## 独立证据与范围

`independent-spec-probes.xml` / `.log`：退出码 0，7 passed，3.42 秒。实际覆盖：两线程/两事件循环同时同键只有一次发送；发送前和发送中插入新栅栏，关停保留原 reserved/sending、不穿透写账；收正文期间撤销案件权限拒绝登记；在途撤权后三个新 GET 均拒绝且不保存候选；恢复白名单拒绝非精确路径；启动失败停止真实 worker 并释放目录锁。

三次命令均为 `.venv/Scripts/python.exe -m pytest .local/chat-generation-http-20261019/test_independent_spec_probes.py`，独立 basetemp/JUnit 路径；字节上限 RED 和修后 GREEN 追加 `-k over_wire`。七项初始 GREEN 与一项修后 GREEN 分开记录，不声称修后重跑全部八项。未重跑正式目标集或全套，没有安装/冻结/真实网络验收结论。本片后端审核不等于首页发送、Jev、动态真实政策、自动档案或生产可用。
