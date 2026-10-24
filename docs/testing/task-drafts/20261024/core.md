# A 持久草稿核心实测

工作目录：`D:\Documents\ChatGPT\律所项目`。仅独立虚构测试数据库、合成附件和已有 Mock 路径，无真实微信、模型、合同或对外发送。本记录只覆盖列明命令；未运行完整 Python 全套，不代表生产验收。

| 顺序 | 实际命令（均在工作目录运行） | 退出码 | 实际结果 |
|---|---|---:|---|
| 1 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k module_is_available` | 1 | 1 failed / 14 deselected；模块尚未实现的断言失败 |
| 2 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q` | 0 | 15 passed，10.61 秒 |
| 3 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k 'repeated_resolution or rebinding or exact_control or cancellation'` | 1 | 4 failed / 17 deselected，4.85 秒；重复 resolution 复制冲突、重绑定后补未拒绝、文字控制未实现、取消接口缺失 |
| 4 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py tests/integration/test_task_drafts_bridge.py -q` | 1 | 31 passed / 1 failed，29.00 秒；失败为 bridge 测试撤权夹具参数错误，已交 root 修正 |
| 5 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k cannot_claim` | 1 | 1 failed / 22 deselected，1.92 秒；执行可在没有案件/版本证据时错误进入 awaiting_facts |
| 6 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py tests/integration/test_task_drafts_bridge.py -q` | 0 | 34 passed，32.54 秒；含 23 核心和 11 bridge 项 |
| 7 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k full_draft` | 1 | 1 failed / 23 deselected，1.98 秒；第 101 个事件错误自动附入草稿 |
| 8 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q` | 未取得 | 执行期间会话中断，原进程标识失效；不计为通过 |
| 9 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k list_omits` | 1 | 1 failed / 24 deselected，2.01 秒；一个重绑定旧执行阻断整个列表 |
| 10 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py tests/integration/test_task_drafts_bridge.py -q` | 0 | 36 passed，36.90 秒；含 25 核心和 11 bridge 项 |
| 11 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k instruction_at_limit` | 1 | 1 failed / 25 deselected，2.92 秒；边界处多算换行，导致合法 20k 首条或纯文件后补不能关联 |
| 12 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k reply` | 1 | 4 failed / 26 deselected，4.16 秒；reply 字段尚不存在 |
| 13 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k reply` | 1 | 4 failed / 26 deselected，4.54 秒；加入字段后有效关联、未知不回退、跨绑定及冻后引用的行为仍失败 |
| 14 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k absent_reply` | 0 | 1 passed / 30 deselected，0.99 秒；None reply 不改变旧事件 canonical 字节和摘要依据 |
| 15 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py tests/integration/test_task_drafts_bridge_review.py -q` | 0 | 40 passed，52.89 秒；30 核心行为和 10 bridge 独立探针（在后补字节兼容测试前启动，不包含第 14 行单测） |
| 16 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q -k explicit_full_target` | 1 | 1 failed / 31 deselected，2.31 秒；WorkBuddy Kimi-K3 提出的显式满额目标触发 413、回滚完整收件批次得到复现 |
| 17 | `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts.py -q` | 0 | 32 passed，33.03 秒；修复后整批持久、媒体完整、游标推进、重复批次幂等和手工超量 assign 仍拒绝均通过 |

最终列明检查覆盖完整批次持久化后游标更新、失败回滚、去重/冲突、明确归属/待分配、身份与附件归属、指令先/材料先、暂停/取消/继续、显式媒体解决/排除、冻结 CAS、不可变执行和后补新草稿、并发重复、scope 重新绑定拒绝、原件摘要重核、执行证据要求及单条不可读记录的列表隔离。100 事件、20 个不同附件和 3 MiB 原始事件累计上限为草稿收集边界；超限收件（包括显式 task_id 指向满额目标）保留完整原始事件及媒体描述为待分配，同批其他有效事件正常处理，游标正常推进。手工 `update_draft(action='assign')` 超量仍返回 413，不修改已有草稿。

暂停/取消状态采用同样的收件保留语义：显式 task_id 指向 paused/cancelled 草稿的普通输入保存为 unassigned，不改变草稿、不自动恢复，也不拒绝整批。原 payload 保留指定 task_id，待用户恢复并明确分配；无媒体的精确控制文字“继续”或显式 resume 操作才能恢复收集。此语义是收件与后续归属分开处理的既有设计。

新增合成 `reply_to_event_id` 只在同一 binding 中查找来源；显式 task_id 优先、未知/多候选不回退到其他草稿、唯一 collecting 优先、否则唯一 frozen 建下一草稿。该字段不声明已接通真实微信回复格式。None 使用序列化排除保持此前 payload 摘要不变。

bridge 由 root 实现，本记录的联合运行不作为核心作者对自身代码的独立审阅结论。schema 迁移、备份恢复、HTTP、UI、完整性及独立审阅以各自证据为准。
