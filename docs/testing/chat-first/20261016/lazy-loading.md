# CH-00B PDF 延迟加载窄切片

2026-10-16；Q 基线 c0f9ae466344e5d585c04d6a9e3ff959a2b7b798。仅独立虚构材料与新建测试目录；未启动、退出或操作实际桌面应用，未调用模型或联网资料。

## 变更

- `src/cn_contract/documents/ingest.py`：将唯一顶层 PDF 适配器导入移到 `ingest` 和 `_parse` 的 PDF 分支。PDF 格式判断、授权、资源上限、逐页校验、原件写入顺序和解析返回均不变。
- `tests/integration/test_document_lazy_loading.py`：4 个独立 Python 进程场景，覆盖文档 API 导入、web.app 导入、DOCX 入库/解析/精确原文回查，以及首次 PDF 入库/解析/损坏文件和超页数拒绝。
- 未新增依赖、修改 packager 配置或从安装包移除 PDF 依赖；静态 `from .pdf_adapter import parse_pdf` 仍能被现有 PyInstaller 解析。

## 实际检查

所有命令均在 `D:\Documents\ChatGPT\律所项目` 使用现有 `.venv\Scripts\python.exe`。原始日志和 JUnit 在 `.local/chat-first-20261016/lazy-loading/`。下文是子任务当时的记录；后续冻结程序及完整回归结果见本目录README。

1. `python -X utf8 .local/chat-first-20261016/lazy-loading/measure_import.py before`：5 个进程，退出 0，见 before.json。
2. `python -m pytest tests/integration/test_document_lazy_loading.py -q --junitxml=.local/chat-first-20261016/lazy-loading/red.xml`：退出 1，4 失败、0 错误。3 项因提前载入 PDF 模块失败；DOCX 一项因测试直接比较不同 Pydantic 类（AnchoredSpan/Anchor）而先失败，不能把该项计为有效特性 RED。
3. 修改两处导入后 `python -X utf8 -m pytest tests/integration/test_document_lazy_loading.py -q --junitxml=.local/chat-first-20261016/lazy-loading/green.xml`：退出 1，3 通过、上述测试错误 1 失败。保留原日志；随后改为完整 model_dump 字段比较，未修改生产行为来迎合测试。
4. `python -X utf8 .local/chat-first-20261016/lazy-loading/measure_import.py after`：5 个进程，退出 0，见 after.json。
5. `python -X utf8 -m pytest tests/integration/test_document_lazy_loading.py tests/unit/test_document_parts.py tests/security/test_upload.py tests/integration/test_parsing.py tests/integration/test_pdf_visual_trust.py tests/integration/test_document_reparse.py -q --junitxml=.local/chat-first-20261016/lazy-loading/targeted.xml`：**144 passed，0 失败/错误/跳过，75.59 秒，退出 0**。其中新测试 4 项；其余覆盖授权、上传限额、所有页面、不可见文字、复杂 PDF、原件/锚点完整性和重新解析。
6. `python -X utf8 .local/chat-first-20261016/lazy-loading/check_packager_graph.py`：现有 PyInstaller modulegraph 静态解析发现 `pdf_adapter`、`pdf_visibility`、`pdfplumber`、`pdfminer.pdfpage` 四节点，退出 0。**未进行冻结程序实机运行。**
7. `git diff --check -- src/cn_contract/documents/ingest.py tests/integration/test_document_lazy_loading.py`：退出 0。

## 导入微测量

|指标|前（5 次中位）|后（5 次中位）|
|---|---:|---:|
|`cn_contract.web.app` import 秒|0.8270686|0.7475610|
|该时点 Windows 工作集字节|88,494,080|81,915,904|
|该时点 Windows PrivateUsage 字节|76,124,160|68,636,672|

前最大 import 为 0.8407423 秒，后最大 0.7834189 秒。每次独立 Python 进程，未清系统文件缓存；内存由 Windows GetProcessMemoryInfo 取得，进程生命周期峰值不等于整个产品峰值。原始每次结果和源码摘要在 before.json/after.json；硬件/系统在 environment.json。

以上只能证明这组运行条件下导入开销的变化，**不是 Electron 可输入时间、系统冷启动、进程树空闲内存、应用峰值内存或安装包减量**。首次 PDF 使用仍承担原本的模块初始化开销。PDF 引擎仍在主后端进程，未新增解析进程隔离；后续能力包拆分及冻结候选验证仍待。

源文件最终 SHA256：b9689e759667b668f6591ba4bb31e5ee050452aa505f38b0215cec14d77681c1。

测试文件最终 SHA256：76d28deb78dcb1d15758ca8d76657bf0b3041b045b748e2de4e154c753b4c045。

本子任务没有提交、修改 TASK_STATUS 或开展完整回归；由统筹合并审阅与阶段记录。
