# CH-04E 独立最终代码审查

审阅者：generation_ui_state 子代理。日期：2026-10-19。基线：`4435396`。实际工作目录：`D:\Documents\ChatGPT\律所项目`。

结论：当前审阅范围未发现需要阻断本片的产品缺陷。实现符合 `docs/plans/2026-10-19-session-model-runtime.md` 的受信任进程内接口范围；没有增加凭据/授权 HTTP 入口，也没有开启生产默认 runtime。独立攻击性探针 8 项通过，最终输入摘要在运行前后保持不变。

本代理只读产品与其他人的测试；仅新增本目录 `review-*` 探针、合成临时目录、日志和本报告。未提交、未运行真实模型或修改安装版。

## 审查范围及结论依据

| 检查点 | 当前实现与判断 |
|---|---|
| 事件循环串行 | `registry.py:50` 首次 resolve 必须在运行 loop 内并绑定它；绑定后 configure/grant/revoke/resolve/snapshot 都拒绝无 loop 或其他 loop 的调用。`GenerationTasks.submit` 同步解析并入队，claim/settle 最终检查到事务提交没有 await。工作线程和另一个 loop 的真实调用已在独立探针中拒绝，原 grant 保持有效。 |
| 配置 ABA | 每次成功 configure 都换 object 代次并清授权，即使配置值、provider 引用相同也不能复活旧 lease；校验失败在赋值前返回。snapshot 同时核对代次、固定 provider 引用与配置内容。 |
| 授权 ABA | 当前完全相同 grant 可幂等；撤销再授予、替换 policy 都产生新的 nonce；只变更目标会话键。旧 lease 不能因相同 policy 再授予而恢复。独立探针分别覆盖 claim 前、provider 等待中两种时点。 |
| actor/session/workspace | key 为三者组合；`snapshot_for` 在入队及 `_current` 中检查 actor/scope。`_current` 被 claim/settle 共用；现有 `_owned`、当前 SessionRow、案件权限和持久 run.session_id 检查保留。借用同用户另一 session 的 lease 时，消息和 attempt 均未写入。 |
| 每 attempt 固定运行快照 | `task_manager.py` 在当前 DB 权限下只 resolve 一次，同一 lease 传给 enqueue 和 coroutine。独立 resolve 计数验证 claim 前撤权/配置更新时仍只解析一次，未切换到重新授予的运行权。lease 不错误固定发送前 draft 的 input_revision；持久 prepared.scope 仍承担版本核验。 |
| 旧 runtime 兼容 | `MainModelRuntime.snapshot_for` 委托原 snapshot，已有可信运行装配语义保留；HTTP attach 仅额外接受 MainModelRegistry。默认 None 及旧入口没有变成隐式配置。 |
| 费用、回执与输出 | 未 claim 的失效任务沿原 `_abandon_unsent` 释放为 not_sent；已 claim 后 wrapper 拒绝时 runner 保守记 sent_unknown，不凭“探针供应商实际未调用”释放额度。真实旧回执使用持久 config 计价；失效 snapshot 只禁止输出采纳，回执保留。 |
| 幂等与原队列 | 原 request_id 分类仍由 BEGIN IMMEDIATE 事务和既有 enqueue 处理；只有新持久 attempt 创建 coroutine，previous 分支直接返回。未添加补发、第二队列或新的恢复路径。 |
| 预算跨进程生命周期 | registry 不计费、不清数据库账本。其 seen policy 摘要跨 configure/revoke 保留；重建 registry 后即使内存允许同 ID 的更大额度，持久 `_budget` 仍以历史 policy 摘要拒绝。独立探针确认 VERSION_CONFLICT，且不增加消息、attempt 或任务。 |
| 外部入口及默认关闭 | web 仍仅有 capability/history/explicit generation/attempt/by-request 路由；普通请求不能 configure/grant/revoke。`create_app`、`build_local_app` 默认 assistant_model_runtime=None，desktop_entry 未读取或注入本机凭据。 |

重点源码已通过 CodeGraph 定位并对照当前字节审查。补读了原 runner、provider、service、数据库事务及默认启动路径，确认该小改动没有绕开已有 claim token、恢复隔离、receipt 和权限检查。

## 独立实际执行

最终命令（仓库根目录；`PYTHONDONTWRITEBYTECODE=1`）：

```powershell
.\.venv\Scripts\python.exe -m pytest .local/session-model-runtime-20261019/review-runtime-probes.py -q -p no:cacheprovider --basetemp=.local/session-model-runtime-20261019/review-final-temp --junitxml=.local/session-model-runtime-20261019/review-final.xml
```

结果：**8 passed，0 failed/error/skipped，4.12 秒，exit 0**。`review-run.json` 保存精确命令、退出码和输入一致性；`review-final.log`、`review-final.xml` 为原始输出。初次 8 项探针结果另外保留为 `review-probes.*`，两次运行是同一组 8 项，不按 16 项累计。

8 项分别为：

1. 同用户第二个真实登录 session 借用第一 session lease 入队，拒绝并保持 0 消息/attempt。
2. 首次 task 排队后撤权再授予同 policy：只 resolve 一次，0 provider 调用，not_sent。
3. 首次 task 排队后重新 configure 同 provider/config：只 resolve 一次，0 provider 调用，not_sent。
4. provider 等待中撤权再授予：收到旧用量回执但不写候选。
5. provider 等待中换成同配置新 provider：旧 provider 只完成一次，新 provider 0 调用，不写旧候选。
6. 工作线程和另一运行 loop 尝试改配置、撤权、授予、解析或使用 lease：拒绝且原 grant 仍有效。
7. 在 claim 返回处注入立即撤权：provider 0 调用，但按已 claim 事实记录 unknown 并保留原 reservation/一次调用占用。
8. 新 registry 尝试以历史同 policy_id 提高 max_calls：持久账本拒绝，无新消息、attempt 或任务。

这些测试使用真实本地 SQLite 工作区、身份/会话记录、服务、任务管理器及 runner；供应商是内存合成对象，无 HTTP 传输、无真实 API 或费用。第 7 项是明示的测试 seam 注入，不将它描述为独立网络进程实测。

## 最终输入摘要

完整 13 项输入 SHA-256 见 `review-inputs-before.json`、`review-inputs-after.json`，本次最终运行 **全部一致**。其中包括 11 项产品/关联源文件、计划及独立探针。核心 5 文件为：

| 文件 | SHA-256 |
|---|---|
| src/cn_contract/assistant/providers/registry.py | 45c70656d49bd2e92ef700538f8b37505c7b729748d76958c95e2736f6097abc |
| src/cn_contract/assistant/providers/policy.py | 104c223bb834b6b8e6fc5a218595aecb714298616ab208ffb6201cfb0cb68184 |
| src/cn_contract/assistant/providers/attempts.py | 7c0c050167e332e0302afc68b8693396c5e81afc27474d66ba5aefe35715ee63 |
| src/cn_contract/assistant/task_manager.py | 127892431f9408e7e9202b5341e0bc294acda865d2ede55a62699db0804f76ec |
| src/cn_contract/web/assistant_generation.py | e6d2293ea2c2a8b8f845fbb216170c11911c014f03636cbe2d6f53a6e1ef6803 |

已核对 registry 最后两处补强包含在上述字节内：DTO model_dump(warnings=False)；snapshot 校验后返回固定 `_config`。registry/policy 摘要也与另一代理 `registry-report.json` 中 37 项正式测试结果一致。本代理未重跑或冒领那 37 项，也没有把尚在其他代理处完善的 HTTP/回环或冻结 EXE 结果提前标为通过。

## 范围限制与后续前提

- 这里是受信任装配接口，不是跨线程通用共享 registry；首次 resolve 后的配置/授权修改必须由所属应用 loop 调度。同步初始化不等于允许初始化期间任意线程并发写入。
- 进程重建不保留 grant；历史 policy、预算和回执由原数据库读取。以后接真实原生凭据仍需单独验证传输、登录会话认证与明确外发授权。
- 固定 provider 指固定受信任对象和校验后的配置；不承诺隔离恶意服务端 Python 代码直接改私有属性或其密钥 resolver。后续密钥接线应沿 configure 创建新 provider，不能暗改旧 provider 的活动凭据。
- 本片不证明真实供应商账号、端点、价格或模型可用；未新建授权 HTTP 路由，未启用真实联网。未重跑旧全仓库验收、安装器或本代理的桌面测试。
