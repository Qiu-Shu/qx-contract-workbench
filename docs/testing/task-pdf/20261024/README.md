# 阶段 C：合成 PDF 持久合同任务

日期：2026-10-24，Asia/Shanghai。工作区：`D:\Documents\ChatGPT\律所项目`，分支 `codex/contract-review-v2`。接续已同步的 A＋B 产品提交 `0178859`；[前阶段证据](../../task-drafts/20261024/README.md)保留其独立范围与历史失败记录。

本片让已登记的合成 PDF 从对话附件读取进入同一 TaskDraft，冻结后复制为案件不可变原件，复用 PDF 页锚点、人工事实确认及本地 Mock 审查。指令先到、材料先到均已实际通过。扫描件、部分未读、加密、视觉不可靠及未登记来源继续阻断；没有加入 OCR、第三方解析依赖、真实微信或真实模型。

当前结论是源码合成闭环通过。安装版仍为 0.4.1；产品提交 `4b62f06` 已同步 GitHub，远端 SHA、tree 与 5,002 个受控条目核对一致，见 [同步回执](github-sync.md)。

## 实现与证据分类

| 类别 | 本片结论 |
| --- | --- |
| 源码已实现 | 附件 PDF 读取及独立解析版本；original 基线；DOCX/PDF 冻结和来源白名单；固定合成 PDF 上传/备份登记；界面读取、页位置及 PDF 主合同；浏览器脚本格式参数 |
| 已有测试证据 | 原合同侧 PDF 解析、视觉质量、页数及来源核验实现和测试早已存在。`test_document_parts.py`、`test_pdf_visual_trust.py` 的完整模块本片 **NOT_RUN**；本片新增用例复用了独立样本并实际验证相应入口行为，不把原模块存在算作重跑 |
| 本轮实际验证 | 9 个 Python 文件、130 个不同用例分进程全部通过；全部 assistant Node 脚本 170 项通过；PDF 两种顺序及 DOCX 一种顺序 Chromium 闭环；完成 PDF 任务实际 qxbak 往返；四开发检查退出 0 |
| 尚未实现或未运行 | 真实微信、真实合同模型、OCR、生产迁移及新安装器均 **NOT_RUN**。完整单进程/全仓 Python、已安装 Electron 窗口及本片桌面 Node 套件 **NOT_RUN**；不复用 A＋B 的桌面测试数量作为本片重跑 |

## 行为与源码定位

以下为本片源码实际行号，路径相对仓库根；未来修改可能使行号移动。

| 链路 | 文件、符号及行号 | 实际行为与测试 |
| --- | --- | --- |
| 受保护附件读取 | `src/cn_contract/assistant/attachments.py:211 parse_attachment` | 可信 MIME 仅 DOCX/PDF；PDF 请求基线仅 None/original；局部导入既有 parse_pdf，成功/partial 存 original，解析版本为 `qx-pdf-attachments-v1`；DOCX 保留原版本。新 PDF 模块验证读全页、重放、历史及错误基线 |
| 原有 PDF 质量及页锚点 | `src/cn_contract/documents/pdf_adapter.py:17 parse_pdf`、`:83` 文本锚点、`:91` 表格锚点；`documents/anchors.py:8 make_anchor` | 仅有非空 anchors 且无 quality/unsupported 才标 readable。扫描页、注释、图片、白字、遮挡及裁剪保留具体未读范围；加密、损坏、页数超限保存失败回执 |
| TaskDraft 冻结 | `src/cn_contract/task_drafts/service.py:112 _manifest`、`:416 freeze_draft` | DOCX/PDF 共同使用完整可读、主合同选择、版本与清单摘要检查；partial 不可冻结。混合两格式分别选择主合同，保留两份来源映射 |
| 准备与 Mock 当前准入 | `task_drafts/mock_policy.py:28 sources`、`:62 require_mock_execution`；`task_drafts/bridge.py:51 prepare_execution`、`:84 review_execution` | 原件、冻结 parse 修订/摘要、登记 hash、策略和当前权限重核。既有 ingest/candidate_parse 重解析生成案件版本页锚点；未确认事实拒绝，人工确认后只保存一次 Mock |
| 默认固定合成登记 | `task_drafts/synthetic.py:7 PDF_HASHES`；`web/assistant_attachments.py:55 register_routes`；`ops/backup.py:198 _registered_hashes` | 固定 PDF 仅并入附件准入与备份；不改变既有 assisted-v1 的 12 份 DOCX 策略，不放开普通案件上传。默认原生 HTTP 测试验证登记样本接受、未登记拒绝及普通案件仍拒绝 |
| 材料预览 | `web/static/assistant-materials.mjs:38 bindMaterials`、`:129` 读取操作 | PDF 本地读取/重读、页号、原文及受保护原件链接；无 DOCX 修订选择。XLSX、图片、旧 DOC 等仍只保留原件 |
| 任务材料选择 | `web/static/assistant-tasks.mjs:101 media`、`:150 renderMedia` | PDF 仅 readable＋对应 parser_version＋original 才标 ready；partial 保留等待读取及人工核对提示；PDF 可作为主合同或附件 |
| 备份恢复 | `tests/integration/test_task_pdf_backup.py:25 test_completed_pdf_native_backup_preserves_pages_sources_results_and_fences_replay` | 完成任务、PDF 页锚点/坐标、来源映射、Mock 结果及受保护文件实际往返；恢复副本 prepare/review/收件全部 `BLOCKED_LIVE`，零重放 |
| 浏览器验收 | `scripts/validate_task_drafts_browser.py:28 main` | `--assisted --format pdf` 可组合，`--order` 保留两种消息顺序；默认 DOCX 行为保留 |

表中 `task_drafts`、`documents`、`web`、`ops` 的省略前缀均为 `src/cn_contract/`。本片无 DTO、schema、迁移或运行依赖变化；冻结媒体与 ParseResult 原有结构已能保存 PDF 页及坐标。

## 固定虚构材料

样本：`tests/fixtures/task-pdf-v1/native-sales.pdf`，4,157 字节、2 页，SHA256：`8e5640e6e341f785f4e24166f56658527246004c67450ce672b80b08a7e141cd`。旁边的 `manifest.json` 记录独立虚构来源、大小、摘要及限制；`generate.py` 可复现，使用开发工具中的 ReportLab，没有新增产品依赖。

生产解析器实际返回 2 个 pdf_span、page 1/2 和 bbox，quality/unsupported 均空；中文价款 13750 元及预付款 20000 元可读取。Poppler 渲染两页时以 SimSun 替代 CID 字体，根任务逐页看过中文及金额，无观察到的遮挡；字体替代和本机渲染不能证明所有设备显示一致。该样本仅供工程模拟，不是法律质量基准。

## 验收矩阵

| 场景 | 本轮实际状态 |
| --- | --- |
| PDF 默认原生附件上传、本地读全页及受保护原文 | PASS：默认 HTTP 注册测试、Chromium，不靠测试 hash 注入证明默认准入 |
| 同一 request 重放、重新读取保留旧修订 | PASS：PDF 组件测试；相同 version/字节的完整 ParseResult 相等 |
| 附件到案件复制，页号/bbox/quote 保留 | PASS：桥接测试；新版本 anchor ID 与附件 ID 不混用 |
| PDF 主合同＋DOCX 附件、DOCX 主合同＋PDF 附件 | PASS：明确选择主合同及两份原件/映射验证 |
| 全扫描、夹有未读页但首尾可读 | PASS：partial、明确 OCR_NOT_DEPLOYED、不能冻结，无执行创建 |
| 注释、白字、遮挡、裁剪、实际绘制图片 | PASS：保留质量提示/候选原文，不能作为完整可读材料冻结 |
| 有效加密 PDF（空密码可打开）、损坏 PDF、页数超限 | PASS：失败回执、原件保留、无部分材料接受；加密对照确实能解出独立虚构明文 |
| PDF 请求 DOCX 修订基线 | PASS：accepted/rejected/custom 均拒绝；无 parse 写入 |
| 未登记 hash、当前登记撤销、local 策略冒充合成 | PASS：默认 HTTP 及桥接负例；零案件文档残留 |
| 当前所有权及旧 request 重放时权限重核 | PASS：当前主体拒绝，原 parse 数量不变；既有核心/桥接撤权用例实际回归 |
| 人工事实确认之前拒绝；确认后一次 Mock | PASS：中文样本组件、原生备份流程及 Chromium；重复 review 同一结果 |
| 指令先到、PDF 后到 | PASS：实际 Chromium 6 步闭环 |
| PDF 先到、之后补指令到同一任务 | PASS：实际 Chromium 7 步；无指令阶段冻结不可用、执行数 0 |
| 刷新取回结果，不产生第二次审查 | PASS：两种 PDF 顺序及 DOCX 回归 |
| 已完成 PDF 的 qxbak 备份恢复 | PASS：1 个真实往返用例，历史/原件/坐标/结果精确相等；恢复副本收件、准备、审查全拒绝，调用哨兵为 0 |
| 第二代 PDF 再备份/恢复 | NOT_RUN；不把前阶段 DOCX 双往返当成本片 PDF 双往返 |
| 真实 PDF/合同法律质量、OCR、微信、真实模型 | NOT_RUN |
| 新安装器、已安装 Electron、本片原生包升级 | NOT_RUN；0.4.1 安装版没有更新 |
| 原生长进程崩溃及 WIN-PATH-02 完全关闭 | 尚未关闭；本片没有专项复现或修复证据 |

## 本轮命令和实际数量

Python 按独立进程运行目标文件；不是一次全仓或单进程 130 项测试。JUnit 的 tests/failures/errors/skipped 已逐份读取，以下 130 个用例互不重复，全部失败/错误/跳过数为 0。

| 文件 | 通过数 | 本地最终回执 |
| --- | ---: | --- |
| `test_task_drafts_pdf.py` | 23 | `backend/final.xml`，30.68 秒 |
| `test_assistant_attachments.py` | 14 | `backend/old-attachments.xml`，14.88 秒 |
| `test_task_drafts.py` | 32 | `backend/old-core.xml`，29.84 秒 |
| `test_task_drafts_bridge.py` | 12 | `backend/old-bridge.xml`，26.49 秒 |
| `test_task_drafts_bridge_review.py` | 24 | `backend/old-bridge-review.xml`，41.43 秒 |
| `test_task_pdf_registry.py` | 4 | 与下行共 `registry-formats-green.xml`，12.17 秒 |
| `test_assistant_attachment_formats.py` | 9 | 同上 |
| `test_task_pdf_backup.py` | 1 | `backup-green.xml`，8.75 秒 |
| `test_assistant_frontend.py` | 11 | `frontend.xml`，JUnit 4.70 秒；进程回执退出 0 |

通用命令：`.venv/Scripts/python.exe -B -X utf8 -m pytest -q -p no:cacheprovider <目标文件> --tb=short --basetemp <独立临时目录> --junitxml <独立回执>`；最终 frontend 实际命令为 `.venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/integration/test_assistant_frontend.py --junitxml=.local/task-pdf-20261024/frontend.xml`。原始终端/退出及 XML 保存在 `.local/task-pdf-20261024`，不纳入 Git。

全部 assistant Node：以 `Get-ChildItem scripts -Filter 'test_assistant*.mjs'` 取得文件后 `node --test $assistantTests.FullName`，实际退出 **0**，**170 passed / 0 failed/cancelled/skipped**。不是在原 A＋B 的 161 项上额外累加 170 项。

四开发门：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`，均以项目 Python 执行并实际退出 **0**。来源检查 13 项仍标 `NOT_PRODUCTION_APPROVED`；55 运行包＋1 构建包检查的 `native_build_verified=false`、`network_calls=0`，不构成原生构建或生产批准。

浏览器实际命令：`.venv/Scripts/python.exe -B -X utf8 scripts/validate_task_drafts_browser.py --assisted --format pdf --order <instruction-first|material-first> --output <独立目录>`。两个运行分别退出 **0**，12.02/11.97 秒，报告 6/7 个步骤。默认格式 DOCX 回归以同脚本 `--assisted --output .local/task-pdf-20261024/browser-docx-regression` 运行，实际退出 **0**，10.35 秒、6 步。

三个浏览器运行各自均为：2 条 inbox、1 草稿、1 执行、1 文档版本、1 review、0 assistant run；`page_errors=[]`、`external_browser_requests=[]`，840 宽视口无横向溢出。上传、解析及事实确认经实际页面控件，脚本只对独立虚构事实执行明确确认；每次创建全新临时数据库，不读取用户运行库。截图及 JSON 报告留在本地，不纳入 Git。

## 有效 RED 与纠错记录

| 阶段 | 真实失败及处理 |
| --- | --- |
| 后端 parse | 1 项因旧附件 MIME 拒绝失败；3 种 PDF 修订基线预期 BASELINE_REQUIRED 而得到 FILE_UNSUPPORTED。分支实现后相应通过 |
| 冻结与桥接 | 12 项阶段出现 3 failed/9 passed，冻结仍认 PDF 不支持；放开明确 MIME 后桥接单项在 mock_policy MIME 拒绝处继续有效失败。最小两处准入修改后初始 12 项通过，最终增补至 23 项通过 |
| 默认注册 | 首轮 4 failed，其中 2 项有效失败为备份未登记及默认 HTTP 409；另 2 项是测试把响应错误字段写为不存在的 error。修正断言后先得到 2 failed/2 passed 的有效 RED，再补齐附件及备份固定登记；最终与格式回归 13 项通过 |
| 界面 | 测试 helper 最初只找 DOCX 文案，不能算有效业务失败；修正 helper 后 35 项中 10 项因缺少 PDF 读取、误标 unsupported/主合同缺项等实际行为失败。最小界面实现后 35 项通过，最终全部 assistant 170 项通过 |
| 其他测试误用 | 图片夹具最初只登记资源未绘制，解析器正确返回 readable；改为实际 /Im1 Do。中文事实测试误用 field_name，改为现有 Fact.field。备份测试误用 TaskDraftView.manifest，改为完整 TaskDraftView 快照比较。均只修测试，不把这些失败冒充产品 RED |
| 浏览器协作 | WorkBuddy 加格式参数时误把 --assisted 与 --format 放在互斥组，组合参数会退出；根任务和独立审阅发现并修正，随后实际完成两个 PDF 及默认 DOCX 流程。没有把代理声称完成当作验收 |

独立审阅以本片实际文件及差异检查质量阻断、锚点稳定、固定登记、旧格式行为和脚本参数；最终没有未解决的已报告问题。它不等于完整安全审计或全仓测试。

提交前检查最初把新 PDF 当成文本，对 ReportLab 对象及 xref 的必要填充空格报 whitespace（退出 2）；沿用仓库固定样本保留字节的约定，仅把该目录的 PDF 标为 binary，未改 PDF 字节或登记摘要。随后重新核验暂存样本与已测原件相同。

WorkBuddy 本轮只读复核 `wb-bg-328167c9aa0c`、浏览器脚本协作 `wb-bg-821159f9ae73` 的原生 ACP 回执均核实请求及实际模型为 `kimi-k3-2`；写脚本会话为 `3a0c2e8d-d223-4a74-badf-844b867a06f2`。其产出经根任务复核、纠错及本机实际运行；没有借协作授权发送真实合同、连接账号或调用产品真实模型。

## 接续与限制

阶段 C 的固定合成原生文本 PDF 闭环已实现并取得本页证据。D 官方微信适配、E 真实模型/有限期授权继续保留独立准入；自动开发不替律师确认真实事实、正式签发或向第三人发送。

本片未安装或更新 Electron、机器人、PDF/OCR/模型依赖，没有使用真实合同、真实供应商调用或外部账号。PDF 字体跨设备显示、扫描件 OCR、生产迁移、法律质量和既有原生长进程崩溃/WIN-PATH-02 仍有明确未完成范围；短进程通过不关闭它们。真实材料、密钥、运行库、备份归档、截图和原始日志留在本机，Git 只同步经核查的源码、独立虚构样本及本页证据摘要。
