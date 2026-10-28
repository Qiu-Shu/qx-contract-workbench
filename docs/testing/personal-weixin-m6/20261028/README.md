# 本人微信接入统一任务：2026-10-28

实施基线 `da1131d05950a888317be2c24b306a88cb48b4b8`，分支 `codex/contract-review-v2`。[实施计划](../../../plans/2026-10-28-personal-weixin-m6.md)复用既有收件、附件、任务、业务和模型账本。本记录随实施更新；当前尚未完成产品内真实微信业务验收。

## 已核验的阶段

| 阶段 | 固定提交 | 已核验结果 |
| --- | --- | --- |
| 真实来源与原有账本隔离 | `bf57d754f8f55baefa6926339ebfd3f3996ef497` | 新增精确来源版本；保留旧记录和哈希；同一会话可同时有桌面合成绑定及本人微信绑定；真实来源不能通过合成注入和代际授权路径写入。独立规格与质量审阅通过。 |
| 共享本人微信协议 | `1f1fef80fc10f353ba4a822b26825a61abc792b3`、`0057b352c8ad17f484f5d2eeb2dcc3d78fa2ac6e` | 复用已验证探针协议，固定本人收发、有界下载解密、内存凭据及单次发送。产品轮询保留混合批次原始字节，逐条处置交持久收件层；独立探针仍整批严格验证。首次独审发现的整批过早拒绝已修复并复审通过。 |
| 原生授权与业务服务接线 | `5f2ab36eed9df413bccf13b8b15fcf1ea5d3875c`、`c578f559706ebeda19069338ef4307174f4f6a60` | 复用真实数据库、DOCX/PDF 解析、TaskDraft、业务调度、原生材料授权及 GenerationTasks，远端传输及模型为模拟。历史取消导致连接暂停的问题修复后，独立规格与质量复审通过。 |
| 桌面入口与本机二维码 | `8c0c0257e6cdf2125e54399eaecc61be28413d30`、`89ed744171883069e91342a341e9fcb37e6c0709`、`02cfa5f4dc22005b6c3a0f3765ed29dce4e15817` | 原生固定当前会话、只读状态、本机二维码、验证码、断开、真实来源标记和保留本地编辑的刷新已实现。两轮独审发现的主合同选择问题已修复并复审通过；最终收尾见下节。尚未打包或进行产品内真实扫码。 |

后端检查点已正常同步至 `38815af` 并核对远端 SHA；桌面入口及接续收尾的提交和远端核对也记录在[同步回执](github-sync.md)。完整产品与真实微信业务未列为完成。

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

## 桌面入口专项证据

Task4 只提交29个相关路径；混合修改的模板和桌面包清单按本次片段暂存。原有包版本、样式与其他任务 WIP 保留，并从索引单独导出检查，避免只在混合工作区通过。

| 验证 | 退出码与实际结果 |
| --- | --- |
| 真实来源投影、本机二维码首次验证 | Python 2 failed，退出1；补齐后2 passed，退出0。 |
| 真实任务不得显示模拟操作 | Node 1 failed → 1 passed；分别退出1、0。 |
| Python 四文件相关回归 | 80 passed / 3 failed，退出1，169.98秒；失败为旧标题、旧依赖数量及按末位定位构建依赖的断言。修正后两个相关文件34 passed，退出0；最终来源/QR文件3 passed，退出0。四文件最新相关运行覆盖84个不同用例，未宣称一次84项全绿。 |
| 独立导出的索引版本 | 相关桌面/前端139 passed，既有草稿控制器28 checks，均退出0。 |
| 切聊天期间的迟到状态查询 | 自查有效1 RED；修正后原生与UI23 passed；刷新索引后的原生13 passed，退出0。状态读取过期只丢弃结果，过期的开启/验证码操作仍断开捕获的连接。 |
| 本机二维码依赖 | 固定 qrcode8.2 官方 wheel、哈希及许可证；开发门56运行依赖+1构建依赖通过，网络0，原生构建仍未验证。 |
| 有界界面检测 | 退出1，一项隐藏二维码img没有预设src的提示；仅在原生同会话状态就绪后设置本机地址，未全局关闭检测。 |
| 组件浏览器 | 默认Playwright浏览器不存在的首次启动退出1，未下载；复用项目既有Chromium后，工作区与索引版本均退出0，1280/640/360宽度无横向溢出，二维码加载、001234验证码键盘操作与草稿保留通过，页面错误0、外部请求0。 |

二维码 wheel SHA256 `16e64e0716c14960108e85d853062c9e8bba5ca8252c0b4d0231b9df4060ff4f`，许可SHA256 `40dfb903c94ee3f789500131311186548ecba5cefd3557623d7700e2522ab994`。组件报告及图片为 `D:/m6t4visual/work`、`D:/m6t4visual/index`；根代理已查看索引版本宽屏和窄屏图片。这是组件验证，未代替实际Electron、安装包或微信服务器验收。详细命令、首次失败、修正和精确提交边界留在本机 Task4 报告。

首次独审发现后台刷新会覆盖未保存的主合同选择。`89ed744` 修复选择保留、待保存状态及迟到读取保护；有效2项RED后，任务/本人微信/材料选择三文件96 passed、旧草稿控制器28 checks均退出0。复审发现任务变为不可编辑后，保留的选择可能失去恢复入口；`02cfa5f` 增加本地冻结保护和远程不可编辑后的明确放弃入口，5项新反例通过后，原审阅者关闭该问题。验证码说明和二维码失败后手动刷新恢复由后续收尾完成。

## 2026-10-28 接续收尾

WorkBuddy 从原 Codex 线程 `01a177fe-3dbb-7171-91d5-ea4db3a14677` 接续。原线程最后全仓桌面运行曾为409项中408通过、1失败；失败是旧测试仍把 `desktopAssistant` 限定为6个操作，未纳入本阶段已经实现的4个固定本人微信操作。本轮更新精确白名单，没有放宽 IPC 参数或新增权限。

- 验证码文案改为“验证码用于本次微信连接，不会显示在聊天中”，不再暗示验证码只留在本机。
- 二维码加载失败后清除失效图片地址；后台轮询不反复重载，用户明确点击“重新读取状态”后才重新加载，不启动第二个连接。
- 新增2项定向反例，先复现二维码不重载和误导文案，再修复；最终本人微信界面12/12通过。
- 完整桌面409/409、完整助手前端416/416通过，均退出0。
- schema、defaults、development sources、development runtime dependencies 四开发门均退出0；13个来源仍保留未生产批准警告，56个运行依赖及1个构建依赖通过，网络调用0，原生构建未验证。
- 发布门旧断言未计入新增二维码依赖：实际 runtime 60、total 78，旧值59/77。修正后 `test_live_guards.py` 25/25通过。
- 首次全仓使用 WorkBuddy 默认 `PYTHONPATH`，宿主安全组件拦截 pytest 临时目录的批量清理及长路径清理，产生级联异常；该轮已停止且不计为有效结果。改用 `env -u PYTHONPATH` 的独立项目 Python 后拦截消失，产品自身安全检查未改。另有长路径测试把恢复目录写成242字符却断言超过260字符，现将重复段由30调至45以真正覆盖长路径；相关16/16通过。
- 一次中止全仓中 `current_native_restore...[awaiting_input]` 失败1次；同用例独立复跑1/1、所在完整文件10/10通过，未修改该产品代码。保留这次非稳定失败记录，最终全仓另行判断，不按单次失败或单次通过掩盖时序风险。
- 全仓定点复验还发现静态文件白名单漏掉 `assistant-weixin-personal.mjs/.css`，生产入口会404；已补齐并新增样式表路由反例。资料库升级精确差集同步纳入 `weixin_personal_runs`、`weixin_personal_outbox` 两张既有新表。前端与资料库两个完整测试文件54/54通过。
- 证据和跟进事项的历史库夹具原依赖版本位置，且降级时漏删后来新增的个人微信运行表及触发器；现改为按版本名定位，并在两个 synthetic-only 降级入口补齐对象移除。`test_evidence_schema.py`、`test_followup_schema.py`、`test_followup_worksheet.py` 三个完整文件最终140/140通过，未改产品迁移或完整性拒绝逻辑。
- 第一轮完整全仓退出1：7,322 passed / 1 failed / 58 errors / 3 skipped / 1 warning，6,195.62秒。58个错误来自 `test_workspace_upgrade.py` 的 pre-intake 夹具同样漏删两张运行表；1个失败为双附件用例的 `FILE_DIGEST_MISMATCH`。后一根因是模拟 Wire 只保存一个下载体，而两次 DOCX 生成跨秒会产生不同字节，第二次覆盖下载体后与第一次摘要不一致。夹具现固定复用同一份虚构文件字节，不为产品增加重试或放宽摘要校验；运行时和升级两个完整文件复验105/105通过。
- 修正后的最终完整全仓退出0：**7,381 passed / 3 skipped / 1 warning**，6,573.77秒。唯一警告仍是 `test_weixin_accounts.py` 故意向字符串字段传入布尔值的 Pydantic 负例；没有排除失败用例，没有将定向105项叠加进全仓数量。
- 本机 Chromium 组件验收通过：1280/640/360宽度无横向溢出，本机二维码加载、001234验证码键盘输入、未发送草稿保留均通过；页面错误0、外部请求0。未调用真实微信或模型。
- 三次尝试启动额外独立复核均因平台429未启动，不记为已审阅。原线程的分阶段独立审阅结论保留，本轮最终复核以实际测试和本地差异检查为限。

## 产品内实际验收清单

升级前基线已建立：在未改动的实际安装版 0.5.1 上执行 `node desktop/tests/acceptance.cjs .local/personal-weixin-m6/20261028-old-051 <已安装程序>`，退出0，15项通过。使用新建独立虚构账号/目录，含 DOCX 原件、锚点、意见工作稿、Word 下载与重启保留；未调用模型或微信。安装包 `app.asar` SHA256仍为 `ac91453a2548aeed801bab7a9375b81f94d70f6e2078fb4d93eb74cd5e1a6de9`。日志 `old-051.log` 和目录内 `report.json` 留本机。本项只用于之后比较升级保留情况，不是 M6 入口验收。

下表均为 **NOT_RUN**，待代码、离线业务场景与独立审阅完成后，使用新产品入口和本人重新扫码验收。先前[独立通道测试](../../personal-weixin-live/20261028/README.md)证明扫码、收件、指定虚构附件及固定回复实际收到，不能替代此表。

| 场景 | 所需可核对证据 |
| --- | --- |
| 产品扫码与连接 | 桌面当前会话的连接状态；二维码及凭据不进入可分享证据。 |
| 主合同、附件后发指令 | 两份虚构材料原件摘要、同一 TaskDraft、同一业务运行及聊天中的真实模型结果。 |
| 先发指令后发材料 | 缺材料时等待；材料齐备后执行一次，等待期间不发生空审查。 |
| 明确表示还有附件 | 已有主合同与审查意图时说“还有附件，稍等”，继续收集；后续明确继续后才执行，不仅依赖固定静默时间。 |
| 重复消息 | 来源记录复用、原件不重复、业务与模型执行不增加。 |
| 执行中补材料 | 原执行的材料快照不变，新材料进入后续执行。 |
| 明确重新审查 | 新执行保留旧结果；不覆盖历史。 |
| 结果回本人微信 | 发送 claim、接口回执与用户实际收到分别核对；unknown 保留且不自动重发。 |
| 关闭、注销、重启及恢复 | 停止外发、清除内存凭据；重启重新扫码；恢复副本不会自动收件或重放。 |

真实客户材料、第三人消息、法律质量和生产批准不在本轮合成验收结论内。当前安装版仍为此前的 0.5.1，尚未包含本阶段变更。
