# CH-06B3 律师选片 GUI 切片证据（2026-10-21）

执行合同：[docs/plans/2026-10-21-selection-gui.md](../../../plans/2026-10-21-selection-gui.md)。
基线：`51b2875`（CH-06B2c2 回执提交）。本片全部材料为虚构合成，无真实案件/密钥/供应商调用。

## 本片范围

律师在对话页勾选本会话已保存引用 1–8 条 → 服务器确定性预览 → 桌面原生确认窗 → 发送一次资料辅助回答（v1 单轮锁定）。三层改动：

1. **预览扩展（Python）**：`MainContextSelection` 新增 `request_id`（可选，旧字节不动）；`MainContextPreview` 新增 `send_basis`——basis 的 `source_bindings.citation_sha256` 是持久记录规范编码哈希，JS 桌面端无法从预览投影自算，必须由服务器在 ready 且给了 request_id 时用 `assemble_context` 返回的 records 调 `build_basis`/`build_basis_rounds` 组装。DTO 校验：send_basis 非空 ⟹ state=='ready'，且 scope/revision/三 sha 逐字段一致、source_bindings 与 manifest.sources 顺序一致；`sending_enabled` 恒 False 不变。`desktop_control.py` `_OPERATIONS` 新增 `authorize_context` 分发到既有 `NativeModelControl.authorize_context`。
2. **桌面授权链（Electron）**：preload `desktopAssistant.authorizeContext` 桥 → IPC `desktop:approve-context`（`model-approval.cjs` 新处理器：`validContextInput` 校验 → 桌面**自行** GET 草稿/材料 + **POST context-preview**（新 `postJSON` + `csrfCookie` 读 `qx_csrf` 作 `X-CSRF-Token`）→ 预览 state/scope/revision/question/sources 顺序/send_basis 全量比对 → 确认窗展示问题全文+片段清单 → `lease.authorizeContext({session_token, basis})`）；`model-control.cjs` 新 `validContextBasis` 严格校验（十键形状、v1 字面量锁、max_rounds 锁 1）；确认窗 `library_context` 变体（六键、sources 1–8 五键逐项校验、窗口高 700，渲染片段清单、决策仍走既有 boolean 通道）。
3. **前端选片（Web）**：新 `assistant-context.mjs` 控制器——`savedCitations` 从 research receipts 汇集（citation_ids×page.citations 按位配对、去重、≤8/receipt）；保序勾选 ≤8；request_id **惰性铸造**（仅 preview 时 mint，避免消耗既有测试的确定性 uuid 序列）；点选/撤选/编辑/换对话即预览作废；与 generation/research 三向互斥；send 流 saveDraft→原生确认→POST context-generations→NETWORK_UNKNOWN 只经 by-request 找回不重发→host.accept→tracking。渲染层 `#context-panel` 复选列表/计数/预览摘要/状态行，发送按钮 contextMode 文案「确认并发送资料回答」，context 输出引用渲染可点「核对已保存片段」走既有引用侧栏。

## 验证结果

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 前端全套件（scripts/test_assistant_*.mjs，含新增选片 11 项：枚举/上限/保序/失效/预览校验 5 变体/确认-提交-找回/取消/无桥 gating/readonly+skill 阻断/撤权清理） | 66 passed / 0 failed | [frontend-suite.log](frontend-suite.log) |
| 桌面全套件（tests/*.test.cjs，含新增 model-control-context 16 项、context-approval 4 项、确认窗 context 变体 4 项；judge-settings-ui 桥键断言同步 authorizeContext） | 264 passed / 0 failed | [desktop-suite.log](desktop-suite.log) |
| Python 关联回归 10 文件（send_basis 5 项新增、端到端合成走通 2 项新增、desktop_control_protocol 38 项含 authorize_context 分发与严格 ack） | 125 passed / 2 failed | [python-related.log](python-related.log) |
| 2 个失败项基线复验：`51b2875` 独立 git worktree 同机同参数 | 2/2 同等失败（预存在环境家族，非本片回归） | [baseline-reproduce.log](baseline-reproduce.log) |
| 四项工程门禁：schema --check、verify_defaults、verify_sources、verify_runtime_dependencies（development） | 均 exit 0 | [门禁1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |

## 端到端合成走通（tests/integration/test_assistant_context_selection_e2e.py）

一条连续链路核验桌面授权桥所依赖的完整合同：HTTP POST context-preview（带 request_id）→ ready 预览携带 send_basis 且与 assemble_context 重建 manifest 全等 → 原生控制通道 authorize_context 授权（session 绑定 HTTP 登录会话，经 portal.call 保持在应用同一事件环，与生产同环语义一致）→ HTTP POST context-generations 202 → 轮询至 received → 回环服务器实收 1 次且线上字节与不可变登记 wire 逐字节相等 → 输出引用 saved_citation_id 与所选一致 → 历史含所发问题、by-request 找回得 completed → 重复授权返回 existing 不重授、重放提交返回同一 attempt 不重发；Jev 零预留零调用。篡改 basis（wire_sha256 置零）在授权前拒绝、零 attempt、零外发。

## 环境家族说明（非本片回归）

`test_preview_stays_blocked_after_backup_restore`（FILE_LIMIT_OR_LINK：`\\?\` 前缀 basetemp 路径 nlink 假阳性，WIN-PATH-01 起潜伏）与 `test_maintenance_completion_exits_with_parent_pipe_still_open`（同机制：文件守卫先于预期事件触发）在基线 `51b2875` 独立 worktree 同机同参数 2/2 同等复现；本片未改 `workspace_backup.py` 与备份相关代码（git diff 可证）。WIN-PATH-02 定论仍另列待查。

## 边界与未做

- v1 单轮锁定：max_rounds 锁 1、lease 单次语义、确认窗不展示 Jev 选项；v2 多轮界面不在本片。
- 无 schema/依赖变更；选片状态不持久化（刷新即清空）。
- 真实 DeepSeek 供应商接入仍待排期（用户持有 API key，密钥不入库）；本片全部为合成回环。
- 安装版 0.4.1 不变；真实材料/模型/云未动。

## 开发过程修正记录（全部保留）

1. `context_preview.py` 曾误从 `context_codec` 导入 `build_basis_rounds`（ImportError），改从 `rounds_codec` 导入。
2. 前端测试夹具三处缺陷修正（单 receipt 9 条超 ≤8 上限改 8+1 两 receipt、补 m0 消息、补 submitResearch/findResearchRequest 桩、selectedFixture 补 refreshGeneration）。
3. 前端 eager mint requestId 消耗确定性 uuid 序列导致 generation_state 回归失败，改惰性铸造后 66/66。
4. Python send_basis 测试修正：service.read_conversation 返回 DTO 不可下标改 `_owned` 取行；'order' 变体仅在 bindings≥2 时执行。
5. context-approval 测试笔误修正（缺失引号、并发用例期望）。
6. 端到端测试两处真实环境适配：`build_local_app` 要求工作区根为 data_parent 真子目录（弃 bare sqlite 夹具改 initialize_workspace）；registry/控制通道事件环绑定要求授权与发送同环（改 portal.call，与生产桌面同进程同环语义一致）。
