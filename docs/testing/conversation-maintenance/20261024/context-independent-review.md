# 连续对话上下文独立复核

日期：2026-10-24。范围仅为本次 profile 发送的有界历史；原接待功能本地未提交改动保持不动。独立复核者只新增测试与本记录，产品修复由主执行者完成。

## 结论

最终独立回归 **11 passed，exit 0，6.09 秒**。使用真实本地授权、登记、claim、settle、档案回执及完整性校验，以独立虚构资料构造记录，不访问远端模型，不处理真实合同或密钥。

```text
TMPDIR=/private/tmp /tmp/qx-audit-20261024-venv/bin/python -m pytest tests/integration/test_conversation_history_review.py -q
...........                                                              [100%]
11 passed in 6.09s
```

## 发现并验证修复的问题

原 `conversation_history.select_history` 检查 output ID 与 scope，但未核对 `output_json.run_id`、`output_json.created_at` 与实际存储列。独立测试把已有输出 JSON 的 run ID 改为另一随机 ID，或把 JSON 时间改为前一天，选择器仍采纳历史文本。新增两项回归原先均为 `DID NOT RAISE`；该轮实际结果为 **7 passed，2 failed**。

主执行者随后补充查询及核对 run/output 关系、输出 JSON 的 run ID 和时间，并约束 attempt 的 conversation。修复后上述两项及其余新增回归全部通过。修复源位置：`src/cn_contract/assistant/conversation_history.py` 的 `select_history`，本记录没有代替产品修复或假称先前已通过。

## 验证覆盖

| 检查 | 观测结果 |
| --- | --- |
| 会话、绑定、输入修订及时间截止 | 错误会话/绑定、修订 0、输出前一微秒均无历史；输出同一时刻可选；后续消息不进入旧修订 |
| 历史字节预算 | 刚好容纳时保留两轮，少一字节仅保留最新完整问答，零预算不包含历史 |
| 当前请求总预算 | 当前文字、预留及历史的明确边界决定是否包含历史；只够当前请求时返回空历史 |
| 超长最近回答 | 12,000 个中文字符的最近回答超出 32 KiB，既不截断文本/问答，也不跳过后强塞更早轮次 |
| 八轮上限 | 实际完成十轮后只选输入版本 3–10，完整性验证通过 |
| 一次许可 | `max_calls == 1`；只替换历史回答的 basis 被拒绝，原 basis 仍有效 |
| 历史回放 | 第三轮完成后，第一轮无历史 v1 和第二轮有历史 v2 均保持原结果，完整性验证通过 |
| 存储篡改 | 第二轮完成后修改第一轮输出文本，第二轮读取、全账本校验和备份创建均拒绝，未发布备份文件 |
| 输出身份/时间不一致 | JSON run ID 或时间与实际列不符时拒绝用于历史 |
| 实际 QXBAK | 同一工作区同时含 v1/v2；创建、恢复、重新登录、读取两轮、全账本校验、再次备份及再次恢复均通过 |
| 恢复后许可边界 | 保存的 `input_json` 字节及历史不变；恢复工作区 claim 被 `BLOCKED_LIVE` 拒绝 |

## 边界

本复核未运行外部付费模型，未验证 Windows 安装包或人工阅读体验。桌面窗口完整历史展示与恶意载荷校验做了源码复核；桌面自动回归由主执行者单独记录。旧 wire 的逐字节兼容、其他库资料路径及原接待功能回归，以主执行者相关测试为准，不由上述 11 项代替。

测试文件：`tests/integration/test_conversation_history_review.py`。新增测试不修改产品代码，不变更 schema，不增设自动化或持久记忆。
