# 阶段 1 最终独立复核：桌面恢复收据

本次仅复跑原有 5 项个人微信控制探针，并只读检查新增 `task_drafts/controls.py`、`update_draft(action=resume)`、审计动作登记与 `personal_runtime._question` 收据分支。

## 实际结果

命令：`.venv/Scripts/python.exe -X utf8 -m pytest .local/unified-plan-20261101/review/test_personal_compatibility.py -q -s --tb=short -p no:cacheprovider --basetemp=.local/unified-plan-20261101/review/pytest-personal-rereview4 --junitxml=.local/unified-plan-20261101/review/personal-rereview4.xml`

**5 passed，22.48 秒，exit 0。** 正常源时序继续调用 1 次；迟到旧消息、跨批缺源序、矛盾源序均调用 0 次；桌面通过既有后端明确恢复后调用 1 次。原 4 项的事件 id、原 JSON 和摘要保留断言继续通过。

## 收据机制检查

- 写入发生在 `update_draft` 的现有 owner/活动库/归档/预期 revision 检查之后，和草稿状态更新处于同一嵌套事务。
- 复用现有 append-only `audit_events`，动作和实体类型有显式登记；没有新增表或放宽不可覆盖约束。
- 摘要包含 actor、conversation、draft，以及每条观察到的控制事件 id/payload_sha256。已保存的收据不能匹配新附加控制事件后的摘要。
- 读取匹配目标 actor/conversation 和 payload 中的 draft/entity/hash；恢复分支仅排除已解决的草稿控制文本，原件仍保留。所有权和运行许可仍由既有后端路径检查。
- 作者新增的新停止使旧收据失效测试已读取；本次按要求未重复运行该作者目标组，不把它计入独立 5 项结果。

**本次限定范围内未发现新的可复现阻断项。** 前三轮红测报告保留原状；它们的失败案例已经在后续独立复核中关闭。本结论不能代替最终全量回归、生产、真实微信或真实模型验收。

复核时 SHA-256：
- controls.py: `59d321e8b58c8d5d1bbae7edb6c9740bd2f51ae7dfb0eaac26d977a56f4b2f36`
- task_drafts/service.py: `73582adfc212fa664ec5856b4aae7af9573530c478d8ca5757ab8f0b86528934`
- personal_runtime.py: `9df5795299df3a26460f39a9873878d9794c0566496069737ca9039389102c2c`
- audit.py: `158a363d98b3021784ab973a938763a718e5adc3eab194ae1b8580e1863f871c`

未改产品源码、Git/index，未打开生产数据库、真实微信或模型。
