# 手工档案维护独立审阅（2026-10-24）

审阅范围：`assistant-profile.mjs`、`assistant-api.mjs`、`assistant.css`、`assistant.mjs` 的 readonly 传递、相关 HTTP 路由与档案保存合同、`test_assistant_profile_routes.py` 新增测试。审阅者没有编写本次产品实现；本次只追加五个前端竞争回归、运行隔离合成测试及记录证据，没有修改产品源码、读取凭据或发起真实模型请求。

结论：发现并用失败测试确认两类必须修复的问题，主执行者已修正；最终 **39 passed / 0 failed / 0 cancelled / 0 skipped**，当前审阅范围没有仍待修复的阻断项。此为源码与合成行为结论，不替代 Windows/Electron、人工体验或法律质量验收。

## 已确认并修复的问题

1. **确定拒绝后残留无法恢复的 pending。** 保存过程中关闭面板或同一对话重新读取，使 epoch 改变；POST 随后明确返回 409/422。旧实现先拒绝晚到 UI 回调，再清理 pending，因此重新打开也只能查询不存在的回执，无法再次手工编辑。新增两个独立用例在修复前均失败（`profile-review-rejection-red.log`，0/2），修复后均通过（`profile-review-rejection-green.log`，2/2）。当前实现先清理明确 4xx 拒绝的 pending，再执行 UI 的身份/epoch 屏障。网络未知和无效响应仍保持回执查询，未增加 POST 重试。
2. **旧保存成功提示跨对话回写。** POST 已返回合法保存回执后，跟随的档案重读尚未结束；切换另一对话并打开其第 9 版，再结束旧重读。旧 `load` 已正确丢弃数据，但 `finishReceipt` 仍把原对话的“已收到保存回执”写到新对话。独立竞争用例修复前 0/1（`profile-review-late-notice-red.log`）；当前实现核对重读成功与当前身份，最终通过。`conflictRefresh` 同样在等待 controller 刷新和档案重读后重新核对身份；新增两个阶段的竞争用例均通过（`profile-review-conflict-race-green.log`）。这两个 conflict 用例首次执行时主执行者已完成修复，未伪称取得修复前 RED。

五个新增回归位于 `scripts/test_assistant_profile_panel.mjs:287` 起；最终完整档案面板脚本日志为 `profile-panel-independent-final.log`。子集已包含在 39 项中，不累计。

```sh
node --test scripts/test_assistant_profile_panel.mjs
```

## 其余合同核对

- HTTP 档案路由先鉴权与对象授权，再读取提交体；读取体后重新鉴权。路径 conversation 与 body scope 不一致时拒绝。保存层继续核对当前所有权、归档/恢复状态、完整 scope、profile revision、接待目标及其 revision。
- 手工维护使用 `manual_edits`、空模型 proposal 列表和 `project_intake:false`，不触发模型，也不改写接待登记。明确空值使用 `{kind:'null', value:null}` 受保护；金额保留字符串，日期转换 UTC，材料“checked”只来自显式手工编辑。
- 回执按原请求 ID 查找，不使用新的 POST 恢复未知结果；双击提交只产生一次提交，错误 conversation 的回执不展示为成功。确定拒绝与结果未知在当前实现中分别处理。
- 历史版本入口即使选择数字上的最新版本也保持只读，必须重新读取当前版本才显示编辑入口。readonly、归档、冲突及撤权在保存操作前再次阻断；服务器仍是权限边界。
- saved profile、来源引用和接待 baseline 均有身份/版本核对；用户输入或范围变化使编辑器失效。文字使用 textContent，未引入 HTML 注入。
- 面板关闭清空所显示数据，Escape/关闭按钮恢复入口或 composer 焦点；异步读取、pagehide 与范围变更保留晚回调屏障。没有就无证据的体验问题扩大改动。

父执行者报告的浏览器、HTTP 和更广 Python 结果属于其独立运行证据；本审阅没有重复真实网络联调，也未将这些结果写作本审阅者执行。
