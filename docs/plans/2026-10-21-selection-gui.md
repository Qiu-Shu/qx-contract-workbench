# CH-06B3 律师选片 GUI 执行合同（2026-10-21）

基线：`51b2875`（codex/contract-review-v2，B2c2 回执已核对）。本片把 B2b1 预览接口、B2b2 发送闭合、B2c 有界轮次已经具备的「选定已保存片段后一次回答」能力接通到律师可见的界面与桌面原生确认窗。只用独立合成数据；不接真实供应商、不动真实材料。

## 1. 现状事实（调研结论）

- 服务端已存在：`POST context-preview`（B2b1，确定性预览，恒 `sending_enabled=false`）、`POST context-generations`（B2b2，202 登记，格式服务端固定）、`NativeModelControl.authorize_context`（B2b2/B2c2，服务端重建 basis 比对后才授权）。
- 前端已有：检索面板（B2a，`state.research.items`  receipts 内含本会话已保存引用的 id 与标题/行号投影）、引用片段查看侧栏（`assistant-citations.mjs`）、生成控制器（capability→原生确认→提交→找回→历史）。
- 桌面已有：`desktopAssistant.authorizeGeneration` 桥 → `desktop:approve-generation`（独立 HTTP 快照 + 模态确认窗 + 控制通道 `authorize`）；Python 侧 `desktop_control.py` 私有管道 `_OPERATIONS` 不含 `authorize_context`。
- **缺口**：①网页没有枚举/勾选已保存引用的界面；②预览响应不含授权所需 basis（`source_bindings.citation_sha256` 是持久记录的规范编码哈希，JS 侧无法从投影自算）；③桌面控制通道与确认窗没有 context 变体。

## 2. 设计定稿

### 2.1 服务端（Python，无 schema 变更、无新路由）

- `MainContextSelection` 追加 `request_id: UUID | None = None`（可选，缺省行为与字节不变）。
- `MainContextPreview` 追加 `send_basis: MainContextSendBasis | None = None`。DTO 校验：`send_basis` 非空 ⟹ `state=='ready'` 且 basis 的 `manifest_sha256`/`config_sha256`/`wire_sha256` 与预览逐字段一致、`system_sha256 == sha256(system_text)`。`sending_enabled` 恒 False 不变。
- `preview_context`：`selection.request_id` 给定且 ready 时，用 `assemble_context` 已取回的 records 调 `build_basis(request_id, ...)` 组装 `send_basis`；basis 是数据不是授权（既有注释语义）。
- `desktop_control.py`：`_OPERATIONS` 与分发表加 `authorize_context`（期望状态 `{'authorized','existing'}`，结果键严格 `{'status'}`）；`NativeControlHandler` 绑定 `main.authorize_context`。未知操作、异常映射、禁用清理语义不变。

### 2.2 桌面端（Electron）

- `model-control.cjs`：`STATUSES`/`validPayload` 加 `authorize_context`：payload 键 `{session_token, expected_config_version, basis, max_total_usd, valid_for_seconds, max_rounds}`；basis 严格形状校验（`input_format=='library-context-v1'`、`template_version=='saved-library-context-system-v1'`、`request_id`、七键 scope、`expected_composer_revision`、四个 sha256、`source_bindings` 1–8 项 `{saved_citation_id, citation_sha256}` 且 id 唯一）；本片 `max_rounds` 锁 `1`。
- `backend.cjs`：`authorizeContextModel(payload)` → `_model('authorize_context', payload)`。
- `model-session.cjs`：lease 加 `authorizeContext({session_token, basis})`，ack 校验与失败 revoke 清理语义同 `authorize`。
- `model-approval.cjs`：新增 `desktop:approve-context` 处理器，复用 generation 处理器的并发/guard/cleanup 骨架：
  1. 校验渲染进程输入 `{conversation_id, request_id, expected_scope, expected_composer_revision, citation_ids[1..8 唯一]}` 与 captureContext；
  2. 桌面**自行** HTTP 读草稿（GET，同既有 snapshot）+ **POST context-preview**（新增 `postJSON`：读 `qx_csrf` cookie 作 `X-CSRF-Token`，body 为上述选择 + 同一 request_id）——预览数据从不经渲染进程转手；
  3. 比对：预览 state=='ready'、`send_basis` 非空且 `basis.request_id==request_id`、scope/revision 一致、`source_bindings` 的 id 序列与 `citation_ids` 逐位相等、草稿问题非空且无材料；
  4. 确认窗展示问题全文 + 片段清单（标题/类型/行号/待核对）+ 接收方 + 费用上限；
  5. 批准后 `lease.authorizeContext({session_token, basis: send_basis})`。取消 → `APPROVAL_CANCELED`；任何一步失败按既有语义拒绝/清理。
- `model-approval-window.cjs/.html/.js`：details 增加 context 变体严格校验 `{kind:'library_context', content, sources[1..8]{saved_citation_id,title,kind,line_start,line_end}, model, max_total_usd, recipient}`；窗口渲染片段清单。generation 变体字节与校验不变。
- `preload.cjs`：`authorizeContext: value=>ipcRenderer.invoke('desktop:approve-context',value)`。

### 2.3 网页前端

- `assistant-api.mjs`：`submitContextPreview(id,body)`、`submitContextGeneration(id,body)`；找回复用 `findGenerationRequest`，历史复用 `getGenerationHistory`（attempt 联合类型已含 context）。
- 新 `assistant-context.mjs` 控制器（仿 research controller 的 epoch/stamp/pending 模式）：
  - 候选清单：从 `state.research.items` 的 receipts 汇集（`citation_ids` 与 `page.citations` 按位配对、跨检索去重）；仅内存，**不新增任何持久草稿**。
  - `state.context = {selected, preview, phase, canSend, error}`；`selected` 保点选顺序、≤8、去重。
  - 失效规则（readiness 既定）：点选/撤选/编辑文本/切换对话/scope 或 revision 变化 → `preview=null`、重铸 request_id、进行中的确认作废。
  - `preview()`：先 saveDraft → POST context-preview；校验响应 scope/revision、`manifest.question==已保存草稿`、sources 与 selected 逐位一致、`sending_enabled===false`、ready 时 send_basis 自洽。
  - `send()`：preview ready 且桥存在 → `nativeContextAuthorization({conversation_id, request_id, expected_scope, expected_composer_revision, citation_ids})` → POST context-generations（同 request_id）→ by-request 找回（NETWORK_UNKNOWN 只查不重发）→ `host.accept` → 交回既有 generation 历史跟踪。
  - gating：library 启用、非只读、无材料、无 skill、草稿非空、选中 ≥1；无桌面桥时可预览不可发送并明示。
- `assistant-state.mjs`：挂 context controller，与 generation/research 互斥（blocked/unknown 链）；`send()` 分派：`context.selected.length>0` → context.send()；`edit/selectSkill/open/reset` 串联 `changed()/reset()`。
- `assistant-render.mjs`：选片面板（复选列表：标题+类型+行号+待核对；计数；预览摘要：问题预览、来源数、wire 字节/上限、状态文案）；发送按钮在选中片段时文案为「确认并发送资料回答」；`renderAttempt` 对 context 输出的 `candidate.citations`（saved_citation_id+quote_sha256）渲染为可点「核对已保存片段」按钮，走既有引用侧栏。
- `assistant.html`：新增 `#context-panel`（默认 hidden，`data-library-enabled` 且无材料时由渲染层控制）；`assistant.css` 面板样式；`assistant.mjs` 绑定与桥探测。

## 3. 验收（全部达成，证据见 [selection-gui/20261021](../testing/selection-gui/20261021/README.md)）

- ✅ Python：preview 扩展（无 request_id 旧字节不动、ready+request_id → send_basis 逐字段一致、input_too_large → 无 basis，5 项）；desktop_control `authorize_context` 分发（合法/未知操作/错误码映射/严格结果键，协议套件 38 项）；B2b2 关联回归不回归（125 通过，2 失败为基线同等复现的环境家族）。
- ✅ 前端 node 套件：选择上限/保序/撤选与编辑失效/预览校验/确认-提交-找回/撤权清理/无桥 gating（新增 11 项，全套件 66/66）。
- ✅ 桌面 cjs 套件：control 校验矩阵（16 项）；approve-context（快照不符/预览非 ready/取消/批准/CSRF 缺失，4 项）；窗口 context details 校验（4 项）；既有 generation 套件不回归（全套件 264/264）。
- ✅ 端到端：回环 provider 下「检索→保存片段→HTTP 预览携带 send_basis→原生授权→POST context-generations 202→回环字节逐字节相等→历史呈现与 by-request 找回」一次走通；篡改 basis 授权前拒绝零外发（2 项）。
- ✅ 四开发门 exit 0；关联回归 2 个失败项经基线 `51b2875` 独立 worktree 同机同参数 2/2 同等复现佐证为预存在环境家族。

## 4. 边界

v1 单轮（`max_rounds=1`，UI 不暴露轮数；v2 多轮界面另立片）；无新 schema/表/列/触发器；无新依赖；真实供应商不接（回环合成）；选片状态不持久化（无第二草稿系统）；法库内容变化不自动刷新已选；CH-07 自动档案、CH-08 导出、安装器/打包验收不在本片。
