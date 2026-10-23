# UX-02 材料拖拽与多文件切片执行合同（2026-10-23）

所有者指令：① 拖文件到对话框直接保存上传；② 支持图片/Word/PDF/表格；③ 参考 WorkBuddy 对话栏交互；④ 选择文件后要有删除按钮；⑤ 多文件上传；⑥ 注重交互便捷与美观。并指令：先在 GitHub 搜索可复用项目，不重复造车轮。

## GitHub 复用评估（结论：不引入整包上传库，复用其交互模式）

| 候选 | 许可 | 体量 | 与本项目契合度 | 结论 |
| --- | --- | --- | --- | --- |
| Dropzone.js（18k★，MIT） | MIT | ~14KB gzip | 自带 XHR 传输与整套 UI；无法对接本项目"metadata+file 双段、request_id 回执、by-request 找回、控制器单通道"协议；无构建链下需 vendor UMD | 不采用 |
| FilePond（16k★，MIT） | MIT | ~15KB gzip 核心+插件 | server.process 可自定义，但其自渲染队列与本项目材料面板（读取/移出/回执语义）范式冲突；前端测试用自制伪 DOM 夹具，库无法在其中运行，需双代码路径 | 不采用 |
| Uppy | MIT | ~45KB+ | 面向 tus/S3 等云上传，过重 | 不采用 |
| file-type（MIME 嗅探） | MIT | 依赖 strtok3 等 | 面向 Node 流；后端 Python 侧魔数嗅探约 30 行 | 不采用 |

决定性约束：上传传输层是项目特有协议（幂等回执 + 不可篡改账本），任何现成库都无法复用传输；交互层（拖拽蒙层、chips 队列、逐个删除）原生实现约 200 行且可进现有测试夹具。复用其成熟交互模式（FilePond 的 chip 队列 + × 移除、Dropzone 的整区拖放高亮），不自造新范式。

## 变更内容

1. **后端格式扩展**（`domain.py`、`assistant/attachments.py`）：DOCX 之外新增 PDF、XLSX、PNG、JPG、CSV。mime Literal 收窄为六值枚举；文件名后缀与 mime 映射校验；内容嗅探（docx 维持 read_package 深校验；xlsx 校验 ZIP 结构；pdf/png/jpg 魔数；csv 须 UTF-8 可解码）。`AssistantMaterialPolicy.policy_id` 放宽为 `assistant-local-docx-v1`（存量行兼容）+ `assistant-local-files-v2`（新上传）。**读取原文（parse）仍仅 DOCX**，其他格式仅保存原件+下载。
2. **多文件待传队列**：文件选择多选；队列 chips（文件名+大小+× 单个移除+清空）；一次同意、顺序逐文件上传（各自独立 request_id 回执），进度 i/N 反馈，失败即停并保留未传队列。
3. **拖拽上传**：对话区 dragover 显示高亮蒙层"松开以添加材料"；drop 入队并展开面板；不支持格式即时点名拒绝；无对话时依托控制器惰性建话（materialPending → createConversation），不新增路径。
4. **删除按钮边界（诚实说明）**：待传队列可随意 × 移除；**已上传原件不提供物理删除**——完整性账本（attachment_integrity）要求历史快照引用的附件行与原件文件必须存在（否则 ASSISTANT_MATERIAL_REFERENCE / 备份校验失败），物理删除需账本结构版本化，另立切片。已上传材料用既有「移出本次」脱离对话范围。

## 验收

- Python 集成测试新文件：六格式接受/魔数不符拒绝/后缀与 mime 不匹配拒绝/非 DOCX parse 拒绝/存量 docx 路径回归。
- 前端夹具测试：多选入队、chip × 移除、清空、顺序上传计数、失败保留队列、drop 入队与格式拒绝、非 docx 不显示读取按钮。
- 既有三层套件全绿（前端/桌面/Python 关联）；四开发门 exit 0。

## 边界

无 schema 变更（账本/表结构不动）；无依赖变更；不引入第三方库；物理删除不在本片；parse 仍仅 DOCX；合成材料哈希登记机制不变。
