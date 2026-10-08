# 离线OCR与原页校对 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 用户已选择主助手直接完成计划、实施与验证，无需逐阶段确认。

**Goal:** 将独立虚构PDF的授权原页、真实离线OCR候选和逐案来源核对接入既有工作台，保留无法部署时的明确阻断。

**Architecture:** 复用受保护原件、案件授权、事实快照和现有中文页面。PDF.js只在本地渲染；OCR使用独立环境和受限进程，原始候选与律师确认记录分离。业务DTO仍唯一位于domain.py。

**Tech Stack:** 现有Python3.12/FastAPI/SQLAlchemy；固定PDF.js6.4.299；独立CPU PaddleOCR3.7.0/PaddleX3.7.0/PaddlePaddle3.3.0与预检固定v5 mobile权重。

**Spec:** `docs/superpowers/specs/2026-10-08-offline-ocr-proofreading-design.md`，用户已明确采用。

## Global Constraints

- 当前分支增量，原件和历史证据保留，独立虚构材料，真实DeepSeek/QCC/云OCR/正式签发关闭。
- 资产取得后逐字节核验及记录许可/NOTICE，未核不运行；独立环境不改当前.venv。
- PDF当前版本/成员/hash核验；浏览器同源本地资源，无任意URL入口。
- OCR每页1600万像素/最长边8192、60秒、进程组2GiB；缺OS硬限拒绝启动。
- 仅按需页OCR，逐页结果，不能只处理前N页后称完成；金额使用Decimal和单位。
- 审计和确认不能由客户端伪造；全量套数与48页、法律结果分别记录。

## Review Focus

- 成员被撤销或版本被替换后，旧页面/原件/候选请求不得继续成功；Task1和Task3覆盖。
- PDF外链/动作、解析特殊字符、旋转/CropBox与重复文字不能造成外发或错位来源；Task1覆盖。
- 缺失/损坏资产、worker子进程或缺隔离不能回退下载/非受限执行；Task2覆盖。
- 来源核对事务中途失败、重放或跨案记录不能留下可消费的半成品；Task3覆盖。
- 全拒绝或仅mock不计OCR运行正例；48页记录错误、正确和阻断分母，Task3覆盖。

### Task 1: 固定PDF.js资产与授权原页预览

**Files:** `sources/pdfjs-assets.lock.json`、`sources/third-party-notices/pdfjs/`、`scripts/prepare_pdfjs_assets.py`、`src/cn_contract/web/pdf_review.py`、`web/static/pdf-review.mjs`、既有app/template/styles、`tests/integration/test_pdf_original_viewer.py`、`tests/unit/test_pdfjs_assets.py`。

**Interfaces:** `register_routes(app,database,actor_in)`注册受保护GET原件接口；`GET /api/matters/{matter_id}/documents/{version_id}/original?sha256=...`只返回相符且当前的PDF bytes。`GET /static/pdfjs/{path}`仅提供受锁资产，不接收文件路径或远程URL。前端`showPdf(version,page,bbox)`由现有事实页/锚点按钮调用。

- [ ] 取得官方固定tgz，校验npm integrity、完整清单、安全解包边界与许可，记录实际采用；浏览器仅复制运行所需完整资源集。
- [ ] 写失败测试：原件接口404→授权200/exactbytes/no-store；未登录/跨案/撤权403或401；stale/hash篡改409；DOCX拒绝；资产缺失/损坏拒绝、目录穿越404。
- [ ] 实现原件只读接口与精确资源白名单；不放开整目录静态挂载。
- [ ] 接入PDF.js原页+文字侧栏，25%–300%缩放、90度旋转、翻页和锚点定位；禁脚本/动作/外链；尺寸超限明确拒绝。
- [ ] 运行 `pytest -q tests/integration/test_pdf_original_viewer.py tests/unit/test_pdfjs_assets.py -W error`；实际浏览器加载独立多页PDF及缩放/旋转/定位，保存截图和同源资源观察。
- [ ] 记录目标/关联结果并本地提交；不把单页或DOM成功记为全面视觉验收。

### Task 2: 固定CPU资产、独立环境与受限OCR worker

**Files:** `sources/ocr-assets.lock.json`、`sources/third-party-notices/ocr/`、`scripts/prepare_ocr_assets.py`、`documents/ocr_assets.py`、`documents/ocr_worker.py`、`documents/ocr_process.py`、`documents/ocr_adapter.py`、`domain.py`、`tests/unit/test_ocr_assets.py`、`tests/integration/test_ocr_worker.py`。

**Interfaces:** `verify_ocr_assets(root,manifest)`验证完整模型/环境资产；`run_ocr_page(image_bytes,source_metadata,*,worker_config)`只接受后端生成的本地位图和来源DTO，返回OCRResult或明确ServiceError。worker没有案件DB/凭据/任意shell参数。`OCRResult`与`OCRBlock`在domain.py定义，所有识别文本初始unverified。

- [ ] 公共发行wheel-only解析并锁定完整依赖；不运行sdist构建，实际下载hash及包内许可检查；获得全部采用证据后安装专用环境。
- [ ] 获取两固定revision模型的完整资产；校验LFS声明及实算hash。缺模型/损坏/混版本/额外文件/逃逸目录真实失败测试，然后实现校验门。
- [ ] 独立虚构worker探针验证AppContainer无网络能力与Job Object内存/进程组/超时；不能创建限制则拒绝，不回退。
- [ ] 先真实失败测试再实现单页CPU输出至唯一DTO；仅显式本地模型路径；禁用自动模型选择和非必需预处理。
- [ ] 实际单页预测、缺资产、外网/loopback尝试、超时/超内存/子进程清理；记录原始输出与退出码。
- [ ] 运行 `pytest -q tests/unit/test_ocr_assets.py tests/integration/test_ocr_worker.py -W error`。OS或依赖阻断时明确记录未运行真实OCR的项目，保留可独立完成的viewer成果。

### Task 3: 来源核对、事实消费与48页工程验收

**Files:** `domain.py`、新`documents/proofreading.py`和存储、`facts/confirm.py`、`facts/storage.py`、`web/pdf_review.py`、前端原页模块；`tests/integration/test_pdf_proofreading.py`、`tests/fixtures/ocr-proofreading/`与实际运行记录。

**Interfaces:** `submit_page_verification(matter_id,input,actor,db)`保存来源区分的不可变核对记录；`read_current_verification(...)`校验原件/候选/当前权限/版本；OCR和转录不能直接作为PDF_SPAN伪锚点。现有事实服务消费核对来源后仍要求完整事实确认。

- [ ] 定义原页核对输入/输出DTO与存储：source_kind三枚举、原件及候选hash、值/理由/服务端用户与UTC、前版本；测试缺字段和来源伪装拒绝。
- [ ] 按失败测试实现事务/幂等/重放/撤权/版本失效，采用候选后失效旧事实与成果；原始OCR数据不覆盖。
- [ ] 前端显示原页、原始候选、已确认值及来源类型；律师转录和提供者澄清不能显示为扫描文字层。
- [ ] 生成六类各8页独立虚构输入及关键字段/位置观察清单。实际执行48页；清晰印刷必须有真实正确正例；阻断和识别正确分别统计，未运行填NOT_RUN。
- [ ] 运行 `pytest -q tests/integration/test_pdf_proofreading.py -W error`，以及事实/审查/决定/导出关联回归；新目录浏览器完成实际工作稿确认路径。
- [ ] 按改动运行完整工程回归，核对原生清单与JUnit；更新实际采用来源、启动绑定和Git字节一致性。独立审阅本轮整体改动，修复重要发现并保存证据。
- [ ] 更新TASK_STATUS/ASSISTED_SCOPE、阶段测试记录和Obsidian；本地提交，真实模型/外查/法源/生产状态单列。

## 计划自检与执行记录

Task1生产的版本绑定原件接口供Task3校对页面使用；Task2的OCRResult供Task3使用，DTO由主助手单点修改。资产校验门与原件/候选校验门职责不同，不能互相代替。Task2若发生真实隔离/资产阻断，可继续Task1及Task3的独立手工来源记录，但不能称全套OCR通过；必须在账本记录实际边界。

执行账本：`.audit-local/ocr-proofreading-20261008/progress.md`。证据保留遵从项目AGENTS要求，不按通用技能删除。待执行项不计完成。
