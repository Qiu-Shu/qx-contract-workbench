# Bridge 独立边界复核

复核对象：root 编写的 `src/cn_contract/task_drafts/bridge.py` 及原 bridge 测试。复核者负责草稿核心，未编写 bridge 产品实现；该复核不构成对自身核心实现的独立结论。

工作目录：`D:\Documents\ChatGPT\律所项目`。执行命令：

`.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts_bridge_review.py -q`

实际退出码 **0**；**10 passed in 16.04s**。

新增探针实际验证：冻结后原件篡改被拒绝；synthetic 注册撤销被拒绝；后续重新解析不替换冻结 baseline；非空目标案件拒绝混入；已取消执行不能复活审查；并发准备只复制一次；已完成结果拒绝不同事实版本重放；local 政策即使附件字节在合成注册表中仍被拒绝；第二附件解析失败回滚所有本次文件、文档和事实；冻结 matter 绑定不能指向另一个虽有访问权的案件。

本轮未发现可复现的 bridge 阻断缺陷；以上为定向合成探针，不代表完整回归、真实试点或生产验收。未连接真实微信、外部模型或实际合同，未对外发送。

## Native 合成入口追加复核

root 随后给 `web/services.py` 的 candidate_parse/review 加入内部 `synthetic_task=True` 入口，bridge 在调用时固定传入；全局 assisted_draft 配置保持不变。新增六项独立探针验证：两种入口均拒绝未注册摘要及 local 案件（四项）；普通 assisted review 仍返回 NOT_SUPPORTED（一项）；两个不同附件即使字节摘要相同，也保留两个 source→version 关联，重复准备不再复制（一项）。

同一命令再次实际运行：退出码 **0**；**16 passed in 28.60s**。该次覆盖原十项及新增六项，无失败。

静态独立复核发现一项 native 成功路径尚需修复：`review/workflow.py` 的 `current_manifest` 仍对 assisted_draft 下的 Mock config 返回 DATA_POLICY_UNAPPROVED，web 层 guard 本身不能闭合最终审查及历史读取。已报告 root；该项修复及成功路径验证以随后回执为准，本次十六项通过不宣称 native 完整成功路径已通过。

## Task execution 准入修复后的独立复核

root 随后新增 `task_drafts/mock_policy.py`，把实际执行 ID 传入 `web.services.review`、`workflow.run_review` 和 `current_manifest`。本次逐层检查执行所属会话、当前案件授权、冻结 scope、目标版本映射、源附件授权及原件摘要、服务端 synthetic 注册和案件政策；配置中的 synthetic 标记本身不授予权限。普通 assisted 入口仍保持原有限制。

新增八项探针：五种不具备执行权限的 config（仅标签、非法 ID、未知 ID、尚未 running 的执行、错误 provider）均不能生成 run；native 完成结果在新 session 中可读取，撤销案件权限后拒绝读取；注册被撤销及原件被篡改时，实时读取分别拒绝且不创建新 run。

最终实际命令：`.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts_bridge_review.py -q`；退出码 **0**；**24 passed in 59.76s**。该次包括前十六项与新增八项，未发现这些边界上的可复现产品缺陷。未运行或代称全仓回归。

过程证据：早一次定向执行在 root 同步调整注册表导入方式时出现测试 monkeypatch 目标过期，结果 **2 failed, 7 passed, 15 deselected in 30.76s**、退出码 **1**；两项失败均为 fixture 的 AttributeError，不作为产品缺陷。校正为当前 `backup._registered_hashes` 入口后，上述二十四项全部通过。

另曾运行 `.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts_bridge_review.py -q -k restore_fence`，得到 **1 failed, 24 deselected in 5.25s**、退出码 **1**：恢复围栏下 `read_run(current=True)` 返回 BLOCKED_LIVE。root 确认这是现有设计，恢复只读副本须使用 `current=False` 的历史读取，写入与实时重新校验仍被围栏阻断；该探针的“恢复后实时读取应成功”前提不成立，已移除，未放宽产品 guard。真实归档往返及恢复历史读取由存储复核单独验证。
