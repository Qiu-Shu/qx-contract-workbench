# 第三轮独立复核：共享源顺序门与个人微信兼容

复核仅涉及 `instruction_order.py`、`service_records.instruction_events`、`personal_runtime._question` 小增量。未改产品源码、Git/index；独立合成数据库、MockTransport，无真实账户。

## 结果

`test_personal_compatibility.py` 已扩展此前要求的缺源序、矛盾源序两例，并加入一个针对现有桌面恢复按钮的兼容对照。

| 场景 | 实际主模型调用 | 断言结果 |
| --- | --- | --- |
| 新于暂停的明确继续 | 1 | 通过 |
| 旧于暂停的迟到继续 | 0 | 通过 |
| 跨首次接收批次的缺源序继续 | 0 | 通过 |
| seq 与创建时间矛盾的继续 | 0 | 通过 |
| 桌面明确恢复已暂停草稿 | 0，预期 1 | 失败 |

前四例逐项核对原事件 id、payload_json、payload_sha256 均完整不变。原旧个人微信链迟到恢复 P1 已实测关闭。

## 新实证 P2：桌面“恢复收集”被历史暂停再次拦截

现有 `web/static/assistant-tasks.mjs:335` 为 paused/cancelled 草稿提供“恢复收集”，调用 `update(draft,{action:'resume'})`。合成探针先从微信接收合同和有完整 seq/time 的暂停，验证 paused/0 次调用；随后直接通过既有后端 `tasks.update_draft(... action='resume')`，确认返回 collecting；再 `runtime.advance`，实际仍 0 次调用。

原因是 `personal_runtime.py:_question` 检查已排序历史控制的最后一条仍为 paused，并直接返回 None。桌面明确恢复不是新微信控制事件，因此这个判断抹去了已通过后端验证的恢复动作。需证明并保留有效桌面恢复，不能依赖 collecting 状态本身绕过迟到消息保护，也不能一律拒绝已有恢复按钮。

命令：`.venv/Scripts/python.exe -X utf8 -m pytest .local/unified-plan-20261101/review/test_personal_compatibility.py -q -s --tb=short -p no:cacheprovider --basetemp=.local/unified-plan-20261101/review/pytest-personal-rereview3 --junitxml=.local/unified-plan-20261101/review/personal-rereview3.xml`

实际：**4 passed、1 failed，36.52 秒，exit 1**。未重跑全部回归。

复核时摘要：
- instruction_order.py: `7178f3b0ec08b90ba14728f8fa1af82da7e43776c950a69cab27ad76ddd37779`
- personal_runtime.py: `a559429ad935aabf22ed4efc86632f8713b2daad75d64841d634c099a9e6b818`
- service_records.py: `efc23b8cb5449d9ba1a946c202c280372cda664aa9088093f73f49a8d7e8d639`
