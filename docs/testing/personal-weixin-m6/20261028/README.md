# 本人微信接入统一任务：2026-10-28

实施基线 `da1131d05950a888317be2c24b306a88cb48b4b8`，分支 `codex/contract-review-v2`。[实施计划](../../../plans/2026-10-28-personal-weixin-m6.md)复用既有收件、附件、任务、业务和模型账本。本记录随实施更新；当前尚未完成产品内真实微信业务验收。

## 已核验的阶段

| 阶段 | 固定提交 | 已核验结果 |
| --- | --- | --- |
| 真实来源与原有账本隔离 | `bf57d754f8f55baefa6926339ebfd3f3996ef497` | 新增精确来源版本；保留旧记录和哈希；同一会话可同时有桌面合成绑定及本人微信绑定；真实来源不能通过合成注入和代际授权路径写入。独立规格与质量审阅通过。 |
| 共享本人微信协议 | `1f1fef80fc10f353ba4a822b26825a61abc792b3`、`0057b352c8ad17f484f5d2eeb2dcc3d78fa2ac6e` | 复用已验证探针协议，固定本人收发、有界下载解密、内存凭据及单次发送。产品轮询保留混合批次原始字节，逐条处置交持久收件层；独立探针仍整批严格验证。首次独审发现的整批过早拒绝已修复并复审通过。 |
| 原生授权与业务服务接线 | `5f2ab36eed9df413bccf13b8b15fcf1ea5d3875c`、`c578f559706ebeda19069338ef4307174f4f6a60` | 复用真实数据库、DOCX/PDF 解析、TaskDraft、业务调度、原生材料授权及 GenerationTasks，远端传输及模型为模拟。历史取消导致连接暂停的问题修复后，独立规格与质量复审通过。 |

桌面入口尚待实施，完整产品与真实微信业务未列为完成。以上提交尚未形成本阶段远端同步回执。

后端首次独立审阅发现已回复合同的业务父运行被桌面取消后，历史重放会触发连接级暂停；重新扫码也会重遇该记录。审阅者以虚构夹具复现。`c578f55` 修复为已产生发送 claim 的完成项不再重放，单个取消只停止该次执行；权限、完整性和非取消阻断仍拒绝。定向测试与独立复审通过，保留首次失败记录。

## 实际测试证据

以下命令从仓库根目录运行，使用项目 `.venv/Scripts/python.exe`、`PYTHONUTF8=1`、独立虚构材料与短路径临时目录。不同运行存在重叠，不合计成一个通过数量。

| 验证 | 命令或范围 | 退出码与实际结果 |
| --- | --- | --- |
| 真实来源功能首次失败 | `-m pytest tests/integration/test_weixin_personal.py --basetemp D:/pt1r1 -q` | 1；19 failed。旧版本拒绝真实来源，可信服务尚不存在。 |
| 同目标刷新缺口 | 同文件，`--basetemp D:/pt1r2 -q -x` | 1；1 failed / 19 passed；随后修正按有效授权范围核对重连。 |
| 来源完整性反例 | 同文件，`-k coherent_synthetic --basetemp D:/pt1forgeR -q` | 1；2 failed / 35 deselected；伪造一致哈希的个人账号或目标通道不应取得旧合成代际权限。 |
| 最终来源专项 | `-m pytest tests/integration/test_weixin_personal.py tests/integration/test_weixin_generation_integrity.py tests/integration/test_weixin_generation_dispatch_integrity.py --basetemp D:/pt1forgeG -q` | 0；135 passed，156.36 秒；含全部 37 个本人来源用例。 |
| 来源阶段扩展回归 | 微信、TaskDraft 及模型结构相关的 1,621 项选择 | 1；1,615 passed / 6 setup errors / 1 warning，823.22 秒。运行已载入旧夹具；不能记为整组通过。 |
| 更正夹具后的精确复验 | `-m pytest tests/integration/test_weixin_inbox_schema.py -k native --basetemp D:/pt1in2 -q`；`test_weixin_dispatch_schema.py -k native --basetemp D:/pt1dn -q -x` | 均为 0；分别 19 passed / 72 deselected、20 passed / 64 deselected。 |
| 混合轮询修复前 | `-m pytest tests/unit/test_weixin_transport.py -q --basetemp=D:/pt2f1red` | 1；6 failed / 121 passed。 |
| 协议修复后 | `-m pytest tests/unit/test_weixin_probe.py tests/unit/test_weixin_transport.py -q --basetemp=D:/pt2f1green` | 0；202 passed，2.95 秒；含未改动的 75 项探针用例和 127 项协议用例。 |
| 运行时关联回归 | 下列十文件命令，`D:/pt3g14` | 0；295 passed，405.93 秒。此运行在随后两处自查小修之前，不能替代后续精确复验。 |
| 其他会话撤销隔离反例 | `-m pytest tests/integration/test_weixin_personal_runtime.py -k other_login_session -q --basetemp D:/pt3r4` | 1；1 failed / 37 deselected；修正为只停止被撤销的登录会话，模型全局停用仍关闭连接。 |
| 撤销、配置及迟到结果复验 | runtime、native_model_control、native_model_lifetime 三文件，`-k 'other_login_session or authority_changes or late_model_completion or revoke or disable or config' --basetemp D:/pt3g15 -q` | 0；29 passed / 70 deselected，38.98 秒。 |
| 共享任务来源反例 | `-m pytest tests/integration/test_weixin_personal_runtime.py -k shared_draft_link -q --basetemp D:/pt3r5` | 1；1 failed / 38 deselected；桌面事件在后时，关联曾选成合成来源。改为明确选择固定本人绑定的新来源，保留所有消息与哈希。 |
| 最后两处修正后的完整运行时文件 | `-m pytest tests/integration/test_weixin_personal_runtime.py -q --basetemp D:/pt3g16` | 0；39 passed，102.04 秒；含真实加密备份恢复、原件与模型结果链、权限和未知回执场景。 |
| 关闭后迟到扫码响应 | `-m pytest tests/unit/test_weixin_transport.py -k close_during -q --basetemp D:/pt3r2`；修复后运行 transport + probe 两文件，`--basetemp D:/pt3tfinal` | 先 1：2 failed / 127 deselected；后 0：204 passed，3.29 秒。 |
| 桌面新旧私有协议 | `node --test desktop/tests/personal-weixin-control.test.cjs desktop/tests/model-control.test.cjs desktop/tests/model-control-context.test.cjs` | 0；53 passed / 0 failed，554.154 毫秒。 |
| 既有原生授权流程 | `node --test desktop/tests/model-approval-session.test.cjs desktop/tests/material-approval.test.cjs desktop/tests/model-approval.test.cjs` | 0；53 passed / 0 failed，5,278.4864 毫秒；正常成功不执行撤销，异常或导航失效才撤销已授予权限。 |
| 历史与执行中取消首次失败 | `-m pytest tests/integration/test_weixin_personal_runtime.py -k 'cancelled_replied_history or cancelled_business_before or single_cancel_during' -q --basetemp D:/pt3f1red` | 1；5 failed / 39 deselected，16.40 秒。 |
| 取消定向修复后 | 同选择，`--basetemp D:/pt3f1green` | 0；5 passed / 39 deselected，20.98 秒。 |
| 取消、未知及权限最终复验 | runtime 与 `test_material_parent_context.py`，`-k 'cancel or unknown or reconnect or authority or integrity or replied_history' -q --basetemp D:/pt3f1reg` | 0；26 passed / 42 deselected，59.57 秒。 |
| 剩余运行时最终复验 | runtime，`-k 'not (cancel or unknown or reconnect or authority or integrity or replied_history)' -q --basetemp D:/pt3f1rest` | 0；27 passed / 20 deselected，77.34 秒。与上一组不重叠，合计覆盖47个当前运行时及6个关联父运行用例。 |
| 后端检查点四项开发门 | `-X utf8 -m cn_contract.cli schema --check`；`-X utf8 scripts/verify_defaults.py`；`-X utf8 scripts/verify_sources.py --mode development`；`-X utf8 scripts/verify_runtime_dependencies.py --mode development` | 均为0；schema/defaults一致；13来源带13条尚未生产批准警告；55运行依赖+1构建依赖通过，原生构建尚未验证，网络调用0。此处不是完整测试或生产批准。 |

运行时关联回归十文件命令：

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe -m pytest tests/integration/test_weixin_personal_runtime.py tests/integration/test_weixin_personal.py tests/integration/test_assistant_material_generation.py tests/integration/test_native_model_lifetime.py tests/integration/test_native_model_control.py tests/integration/test_task_drafts_migration.py tests/integration/test_task_drafts_bridge.py tests/integration/test_task_drafts_bridge_review.py tests/unit/test_desktop_control_protocol.py tests/integration/test_native_control_process.py -q --basetemp D:/pt3g14
```

文件先到与指令先到各用两个独立收件批次。第一批之后显式驱动空轮询对应的执行入口，断言未调用模型；第二批补齐指令或材料后才执行一次。此为实际服务入口的离线驱动，不是仅改变同一批消息的排列，也不是实际微信服务器时序验收。

来源阶段还有一次中止的 2,279 项选择，未取得完整汇总，退出 -1，不计通过。扩展回归的单条警告来自既有故意构造错误类型的 Pydantic 负例，尚待最终测试记录说明。阶段原始输出和 XML 保留在本机被忽略的 `.superpowers/sdd/2026-10-28-personal-weixin-m6/`；后续汇总不能抹去首次失败或沿用旧运行冒充新代码验证。

## 产品内实际验收清单

下表均为 **NOT_RUN**，待代码、离线业务场景与独立审阅完成后，使用新产品入口和本人重新扫码验收。先前[独立通道测试](../../personal-weixin-live/20261028/README.md)证明扫码、收件、指定虚构附件及固定回复实际收到，不能替代此表。

| 场景 | 所需可核对证据 |
| --- | --- |
| 产品扫码与连接 | 桌面当前会话的连接状态；二维码及凭据不进入可分享证据。 |
| 主合同、附件后发指令 | 两份虚构材料原件摘要、同一 TaskDraft、同一业务运行及聊天中的真实模型结果。 |
| 先发指令后发材料 | 缺材料时等待；材料齐备后执行一次，等待期间不发生空审查。 |
| 重复消息 | 来源记录复用、原件不重复、业务与模型执行不增加。 |
| 执行中补材料 | 原执行的材料快照不变，新材料进入后续执行。 |
| 明确重新审查 | 新执行保留旧结果；不覆盖历史。 |
| 结果回本人微信 | 发送 claim、接口回执与用户实际收到分别核对；unknown 保留且不自动重发。 |
| 关闭、注销、重启及恢复 | 停止外发、清除内存凭据；重启重新扫码；恢复副本不会自动收件或重放。 |

真实客户材料、第三人消息、法律质量和生产批准不在本轮合成验收结论内。当前安装版仍为此前的 0.5.1，尚未包含本阶段变更。
