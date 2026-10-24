# UX-02 材料拖拽与多文件切片证据（2026-10-23）

执行合同：[docs/plans/2026-10-23-material-files.md](../../plans/2026-10-23-material-files.md)（含 GitHub 复用评估：Dropzone/FilePond/Uppy/file-type 均因无法对接项目特有的回执协议与伪 DOM 测试夹具而不采用，复用其交互模式）。
基线：`90cf287`。起因：所有者要求拖文件到对话框直接保存上传、支持图片/Word/PDF/表格、选择后可删除、多文件、交互美观对齐 WorkBuddy 对话栏。

## 变更内容

1. **后端格式扩展**：`AssistantAttachmentInput.mime` 放宽为六值枚举（DOCX/XLSX/PDF/PNG/JPG/CSV），文件名后缀与 mime 映射校验（DTO model_validator）；`assistant/attachments.py` 新增 `_assistant_type` 内容嗅探（docx 维持 read_package 深校验；xlsx 校验 ZIP 结构；pdf/png/jpg 魔数；csv 须 UTF-8 可解码且非空）；案件侧 `_type` 不变（仍仅 DOCX/PDF）；`AssistantMaterialPolicy.policy_id` 放宽为 `assistant-local-docx-v1`（存量兼容）+ `assistant-local-files-v2`（新上传）；parse 仍仅 DOCX（非 DOCX 400 FILE_UNSUPPORTED）；下载原件文件名后缀改为按原件实际后缀。
2. **多文件待传队列**：file input 多选；队列 chips（文件名+大小+× 单个移除）+「清空待传」；一次同意、顺序逐文件上传（各自独立 request_id 回执），进度 i/N 反馈，失败即停保留剩余队列；NETWORK_UNKNOWN 重试核销后自动退役对应队列项（inflight 跟踪）。
3. **拖拽上传**：整页 dragover 显示虚线高亮蒙层（pointer-events 不拦截）；drop 入队并展开面板；扩展名+mime 双重前端预筛，不支持格式即时点名提示；无对话时依托控制器既有惰性建话路径。
4. **删除按钮边界**：待传队列可任意移除；已上传原件不提供物理删除——完整性账本要求历史快照引用的附件行与原件文件存在，物理删除需账本版本化，另立切片。已上传材料用「移出本次」脱离对话范围。
5. 非 DOCX 材料行显示格式标签（Word/PDF/表格/图片），预览显示"仅保存原件+下载"，不出读取按钮。

## 验证结果

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| Python 新增格式测试（六格式往返/嗅探拒绝/parse 仅 DOCX/旧 policy 兼容） | 5 passed | 包含于 python-related.log |
| Python 关联回归（附件/材料/本机材料八件套） | 109 passed / 2 failed（环境家族，见下） | [python-related.log](python-related.log) |
| 基线 worktree 同等复验（HEAD 未含本片改动） | 同 2 项失败复现（safe-delete shim 超深路径 Errno 53 家族） | [baseline-reproduce.log](baseline-reproduce.log) |
| 前端全套件（新增 4 项：多选队列与顺序上传、失败保留队列、拖拽入队与格式拒绝、非 DOCX 预览无读取按钮） | 146 passed / 0 failed | [frontend-suite.log](frontend-suite.log) |
| 四项工程门禁（schema --check、verify_defaults、verify_sources、verify_runtime_dependencies） | 均 exit 0 | [门禁1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |

桌面侧零改动，桌面套件不适用。

## 边界

无 schema 变更；无依赖变更；未引入第三方库（GitHub 评估见执行合同）；物理删除原件不在本片；parse 仍仅 DOCX；每次发送的原生确认窗不变；真实供应商不在本片。

## 追加：.doc（旧版 Word）支持（2026-10-24）

所有者追加指令：支持 `.doc`。实现：`application/msword` + `.doc` 后缀入 mime 映射与前端预筛/accept；OLE2 复合文档魔数（D0 CF 11 E0 A1 B1 1A E1）嗅探，伪造内容拒绝；读取原文仍仅 DOCX，.doc 仅保存原件+下载（前端格式标签同样显示"Word"）。验证：格式测试 5/5（含 .doc 往返与伪造拒绝）、前端全套件 146/146（drop 用例含 .doc 入队）、四开发门 exit 0。
