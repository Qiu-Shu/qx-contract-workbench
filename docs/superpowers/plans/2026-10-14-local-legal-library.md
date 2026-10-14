# 本地案例法规资料库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使本机17,184份法规与2025年3,837,307条案例记录能够中文检索、筛选、核对原文、保留版本并安全恢复导入。

**Architecture:** 在现有`cn_contract`内增加独立资料库模块，复用旧试点严格CSV及字节定位语义，既有DuckDB只读接续。原始资产、来源目录、清洗结果、审核事件与检索代际分开；查询通过固定服务接口提供给CLI及已有登录页面。为避免跨库事务，首批派生元数据和FTS放同一SQLite代际，DuckDB保留既有原文试点与批量核对用途，不再重复保存三份正文。

**Tech Stack:** 现有Python3.12、Pydantic、FastAPI、Jinja2；标准库sqlite3/FTS5、csv、hashlib、json；旧试点DuckDB1.5.6在原独立环境运行。首批中文用可重建的字符二元索引与原文复核，不增加分词依赖或搜索服务。SQLite缺FTS5时明确阻断，不能静默退回全表扫描。

**Spec:** `docs/superpowers/specs/2026-10-14-local-legal-library-design.md`，2026-10-14用户已确认。用户随后明确要求无人值守、以完成程序及数据为目标持续推进，覆盖本计划后续例行确认。当前按计划执行，逐项实际状态见专属进度记录。

## Global Constraints

- 原目录`D:\Documents\ChatGPT\律所项目`、原分支`codex/contract-review-v2`继续，保留所有现有功能；不重写三个工程。代码和虚构测试入Git，原文及实际索引不入Git。
- 原件只读。资料库输出`D:\Documents\群兴法律资料库`，CLI必须显式指定根目录；不能与输入、既有试点或合同案件目录重叠，拒绝路径重定向。旧试点`D:\Documents\裁判文书数据库试点2025`只读。
- 原始案例`F:\裁判文书网数据库\2025`；法规`F:\裁判文书网数据库\全量法律\全量法律`。1985—2024年在百度网盘尚未下载，本期不处理。
- 新业务DTO只在`src/cn_contract/domain.py`定义；不改变既有DTO默认值/报告schema、登录、CSRF、同源校验、案件授权或正式法源准入。
- 规范值保留原值与规则版本；来源核验、文本完整性、法律效力及适用性分开。缺URL不补造；同案号不自动合并；同名法规不同内容不覆盖。
- 普通检索不调用模型、不联网。真实资料不进入普通CI、WorkBuddy正文输入或云端。本期不购买云资源、不上传、不实现自动方法蒸馏。
- 首轮资源边界：进程预算8GiB，索引/临时派生物预算200GiB，D盘保留至少40GiB空闲；达到边界保存检查点后停止。启动时核对资源，不能将软预算称作操作系统硬隔离。
- 新模块尚不存在时，测试在函数内部动态装载并断言接口，避免只因collection error而把“测试失败”记为功能失败。
- 提交仅包含本任务明确文件并记录实际验证；本机Git作者身份未配置，后续无人值守本地提交使用命令级`Codex <codex@local.invalid>`明确标记自动化作者，不冒用历史作者，不更改全局或仓库身份配置。此前文档提交失败后已撤回暂存；不自动推送。

## Review Focus

1. CSV跨行引号损坏后边界不明：停止该文件并保留未处理范围，不能跳一行继续（LIB02）。
2. 同一条法在目录、正文及引述中出现：保留歧义，不能把目录误作可引用正文（LIB03）。
3. 中文检索含零宽/全角、两字词、标点或SQL/FTS控制字符：规范化一致，语法不能注入，命中回到原字符位置（LIB04）。
4. Windows打开旧索引时切换新版、导入强制终止或磁盘不足：旧查询和审核可用，恢复无丢失/重复（LIB05）。
5. 恶意Markdown/URL、路径穿越和过期登录：显示纯文本、只读允许资产、鉴权不被资料库绕过（LIB06）。

## 文件与接口约定

新增`src/cn_contract/library/`：`assets.py`来源资产和hash、`catalog.py`目录与审核、`csv_source.py`严格解析、`pilot_adapter.py`旧库只读接续、`cleaning.py`字段规范化、`law_sections.py`原文分段、`index.py`检索代际、`service.py`查询/回查、`__main__.py`CLI。薄网页路由放`src/cn_contract/web/library.py`，页面放现有templates/static。不要重构无关大文件。

派生数据目录：`assets/<sha256>/original`保存一次原字节快照；`catalog.sqlite`登记来源批次、hash、原路径别名、已完成范围、失败和审核事件；`generations/<id>/search.sqlite`存规范字段、定位和FTS；`current.json`仅指向通过验证的代际。案例正文由不可变资产的CSV字节范围读取，法规正文由原始Markdown读取，派生库不重复存原CSV/raw_fields/body三列。UTF-8解码、CSV还原后原值可回查。

业务DTO：`LibrarySource`（来源批次、hash、大小、相对资产键、格式、原路径别名）；`LibraryRecord`（稳定id、source_id、ordinal、字节范围、raw_hash、body_hash、规范字段、异常与状态）；`LibraryFragment`（record_id、version_id、原文字符start/end、行号、角色、条号候选、歧义）；`LibraryQuery`（资料类型、关键词、phrase/all模式、案号/法院/案由/地域/裁判日期、limit和cursor）；`LibraryPage`（命中、覆盖数、next_cursor、截断/超时状态）；`LibraryOriginal`（版本、原值、正文、hash、定位）；`LibraryReviewEvent`（对象版本、操作人记载、时间、审核项目、前后值、理由、前序摘要）。字段范围检查用既有DomainModel，不允许输入任意文件路径或SQL。首批法规效力时点筛选不开放，文件名日期只展示候选。

稳定id为规范JSON `["qx-library-v1",batch_id,source_sha256,ordinal]` 的SHA256；法规ordinal固定1。同文件跨目录作为位置别名复用，同内容跨批次保留来源关系；body_hash只用于候选分组，不覆盖正文。旧record_id保存为alias。

`version_id`取正文内容hash；法规`series_id`取规范标题+地域候选+机关候选的hash，关系固定machine_candidate，不能据此认定同一法规。试点原字节不匹配时停止该alias接续，保留旧库原字节和逐条异常，不静默映射到新源。FTS固定detail=full，性能未达标再分片；服务与不透明游标不暴露单数据库假设。

## LIB01 来源快照、目录和审核基础

**Files:** 新建`library/assets.py`、`catalog.py`、`__init__.py`；修改`domain.py`；新建`tests/unit/test_library_sources.py`。

**Interfaces:** `register_source(root: Path, path: Path, batch_id: str, kind: str) -> LibrarySource`；`read_asset(root: Path, source_id: str, start: int, end: int) -> bytes`；`append_review(root: Path, event: LibraryReviewEvent) -> str`。`kind`只接受case_csv/law_markdown，读范围最多32MiB，写入只允许library root。

- [ ] 写失败测试：`test_source_copy_hash_and_alias`验证移动后的相同字节hash/id不变、源字节不变；`test_snapshot_change_abort`在复制中变更源时不登记完成；`test_reject_overlapping_and_redirected_roots`覆盖输入输出重叠、junction/symlink；`test_audit_append_only`验证历史审核不可更新/删除。
- [ ] 运行`.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_library_sources.py -q`，记录真实失败；不得用收集失败替代功能失败。
- [ ] 流式复制并同步计算完整SHA256，前后大小/时间检查，临时快照校验后提升；已存在资产重新核对hash，不覆写。目录写事务，审核表与索引分离；未知状态固定pending/unverified，不开放正式法源批准。
- [ ] 原文件被改动后已快照版本仍可查；新输入按新hash形成版本。运行来源测试及`tests/unit/test_domain.py`，记录通过数量，检查既有报告schema不变。
- [ ] 记录本任务验证及变更；仅在已配置真实Git作者身份时提交本任务文件。

## LIB02 案例清洗、试点接续及批量检查点

**Files:** 新建`library/csv_source.py`、`pilot_adapter.py`、`cleaning.py`、`__main__.py`；扩展`catalog.py`；新建`tests/unit/test_library_cases.py`、`tests/integration/test_library_resume.py`。

**Interfaces:** `iter_case_records(root, source: LibrarySource, start_ordinal: int, start_byte: int) -> Iterator[LibraryRecord]`；`clean_case(values: dict[str,str]) -> dict`；CLI `import-cases --library-root PATH --input PATH --batch-id ID --limit N --batch-size 1000`；`import-pilot --library-root PATH --pilot-root PATH`。limit必须正整数，不设旧试点一万条总量限制，但首次实机显式10000。

- [ ] 写失败测试：`test_multiline_offsets_and_bom`逐字节还原多行/引号/BOM；`test_null_metadata_preserves_literal_body`验证元数据None/null/NaN为空而正文原句不变；`test_same_case_different_body_survives`必须保留2条；`test_broken_quote_stops_file`停止且未处理量可见；`test_date_conflict_keeps_raw`无效及互相冲突的日期不猜补。
- [ ] 运行案例测试，记录功能失败；再实现旧`pilot.py:Lines`等效解析与32MiB上限，不删除旧试点代码的限额。表头必须含案号/文书内容且无重复列，未知列保留可回查。
- [ ] 日期按严格解析保存；案号用NFKC与空白规范化形成另一个字段。批量提交已解析记录与next ordinal/byte，恢复前核对快照hash和表头；批次失败回滚，完成范围只在事务成功后前移。
- [ ] `pilot_adapter.py`只用标准库和duckdb，运行于原试点Python并固定只读SQL/禁扩展外联，流式输出已有记录与旧id/字节位置/hash。主进程校验资产字节相同后建立映射和新索引输入；旧库不迁移写入，普通CI用虚构模拟，实机再验证10,000条全映射。
- [ ] 实际子进程中断测试`test_kill_resume_exact_count`与`test_source_changed_reject_resume`：恢复后总量、id集合和原字节等于不中断导入；源变更不得接旧断点。执行以上两组测试，保存退出码和报告；按同样身份约束提交。

## LIB03 法规全量导入、版本和原文分段

**Files:** 新建`library/law_sections.py`；扩展`cleaning.py`、`__main__.py`；新建`tests/unit/test_library_laws.py`。

**Interfaces:** `import_laws(root: Path, input_dir: Path, batch_id: str) -> dict`；`split_law(record: LibraryRecord, original: str) -> tuple[LibraryFragment,...]`；CLI `import-laws --library-root PATH --input PATH --batch-id ID`。

- [ ] 写失败测试：同名不同字节得到不同版本，完全同内容保留来源别名；日期文件名仅为candidate；无URL保持null；标题“草案规定”不得自动判草案；正文提废止不自动判失效。
- [ ] 增加`test_toc_quotation_and_article_one_subsection`：目录/正文重复条号、条之一、引述、附件、表格及无条号都保留；无法可靠区分标ambiguous，可段落检索但不宣称条款定位成功。`test_zero_width_original_span`逐段验证原字符切片与hash。
- [ ] 运行法规测试记录失败，再实现结构分段。清洗只创建搜索视图，记录字符映射；不删表格、目录或没有条号的文本。原文分段完整覆盖且同版本内才能邻接。
- [ ] 运行来源/案例/法规目标测试，记录结果并按身份约束提交。实机全量导入放LIB07，不用真实全文作为CI夹具。

## LIB04 中文索引与统一查询服务

**Files:** 新建`library/index.py`、`service.py`；扩展`__main__.py`；新建`tests/unit/test_library_search.py`。

**Interfaces:** `build_generation(root: Path, record_ids: Iterable[str]) -> str`；`search(root: Path, query: LibraryQuery) -> LibraryPage`；`read_original(root: Path, record_id: str, version_id: str) -> LibraryOriginal`；`read_fragment(root: Path, fragment_id: str) -> LibraryOriginal`。CLI `search`/`show`调用相同服务，结果包含来源、版本及待核验状态。

- [ ] 写失败测试：离婚/租赁两字、词内子串、NFKC案号、phrase连续短语与all词组相与不同、同版本相邻、源字节损坏明确报错；关键词含引号/AND/SQL不能改变语义或执行语句。
- [ ] 索引使用独立FTS5 contentless表、保留位置以支持短语；案例按记录、法规按已标记片段建立整型rowid映射。汉字连续区间产生重叠双字token，其他字母数字按词；分隔符/拉丁token/汉字token分别编码，防止保留token与原文碰撞。查询同一规范化版本，用户输入不直接拼入FTS语法；最少2个中文字符，单字、纯标点或无可索引token返回明确提示。phrase连续匹配，all按用户空格分开的词组相与；一个无空格长词组仍按连续短语处理。原文复核排除清洗造成的假命中。
- [ ] 结构化字段建B-tree，日期/区域未知单独显示；默认不宣称按时点有效。标题权重优于正文，稳定id打破同分排序。默认20条、上限100；游标绑定查询hash+代际，过时代际返回可重开提示，禁止混页。
- [ ] 明确覆盖、无匹配、索引未就绪、超时和源损坏状态；搜索预算2秒，不把超时/候选未查完当无结果，不伪造总命中数。摘要由原文映射生成；字符映射按规则版本重算或压缩保存，不为383万全文逐字符冗余存储。contentless索引不调用假定正文存在的snippet函数。法规片段结果按资料版本归组，保留每个命中条款的位置。
- [ ] 执行搜索及前置目标测试，验证索引/原文结果一致与重复运行幂等，记录实测并按身份约束提交。

## LIB05 索引切换、恢复和迁移包

**Files:** 扩展`index.py`、`catalog.py`、`assets.py`、`__main__.py`；新建`tests/integration/test_library_generation.py`、`tests/integration/test_library_portability.py`。

**Interfaces:** `validate_generation(root: Path, generation_id: str) -> dict`；`activate_generation(root: Path, generation_id: str) -> None`；`export_manifest(root: Path, destination: Path) -> Path`；`relocate_library(root: Path) -> dict`核验而非自动移动。CLI `verify`/`activate`/`export-manifest`。

- [ ] 写失败测试：`test_failed_build_keeps_current_and_reviews`、`test_windows_reader_survives_pointer_swap`、`test_interrupted_batch_idempotent`、`test_disk_budget_stops_cleanly`、`test_export_relative_assets_restore_elsewhere`。最后一项在中文含空格新路径恢复后逐字节回查。
- [ ] 导入目录与索引跨库用幂等record_id和待索引状态协调：索引事务成功后才推进其检查点，崩溃后的重复投递先核对元数据，相同id同hash跳过、不同hash拒绝，不向contentless表盲目覆盖同rowid。元数据、FTS和该代际检查点在同一SQLite事务更新。不得宣称跨库具有单一原子事务。
- [ ] 写入者持OS锁；新代际完整性/数量/hash/固定检索校验后才原子替换`current.json`。旧请求持自己的只读连接，不删除使用中的旧代际；本期不自动清理旧代际。
- [ ] 迁移清单只使用相对资产键、版本及hash；本机绝对路径别名和案例账户资料不导出。导出路径不能覆写已有文件，缺资产明确失败；全量云上传与权限部署留后续。
- [ ] 实际子进程强制终止/重启、Windows占用文件切换、损坏索引和空间不足模拟通过后，记录命令、数量及未测项，按身份约束提交。

## LIB06 现有登录工作台中的资料查询页

**Files:** 新建`web/library.py`、`web/templates/library.html`、`web/static/library.js`、`web/static/library.css`；修改`web/local_server.py`、现有导航模板（实施前以rg定位实际共用入口）；新建`tests/integration/test_library_api.py`。

**Interfaces:** `attach_library(app: FastAPI, database: Database, root: Path) -> None`；`build_local_app(directory, *, port=8767, library_root: Path|None=None)`。`start/serve`新增显式`--library-directory`，默认None时原功能完全相同。路由`GET /library`、`POST /api/library/search`、`GET /api/library/records/{record_id}?version_id=...`、`GET /api/library/fragments/{fragment_id}`、`GET /api/library/status`。

- [ ] 写失败测试：未登录/过期会话拒绝；POST无CSRF/异源拒绝；读取任意路径和非法id拒绝；Markdown内script/img/javascript URL只显示文本；普通资料查询不写入合同权威法源和案件；旧选案/签发限制仍有效。
- [ ] 薄路由复用`web.app.actor_in`、`same_origin`和既有错误响应/CSP，搜索POST调用现有CSRF，读取需要当前登录；不新增免登录端口，不把本机库公开到LAN。网页只查资料，不开放远程导入或审核变更。
- [ ] 用现有Jinja/静态资源形成筛选、结果和原文三栏；标出覆盖量/待核验/历史候选，支持字号、键盘、窄窗、清空及加载失败。首次做页面时读取Impeccable Operate及现有项目Taste规则。既有客户/内部输出与案件不混入资料库。
- [ ] 导出当前结果为UTF-8 JSON或浏览器纯文本，保留版本、来源和状态，不自动对外发送。点击原文定位到确切字符范围，切查询清空旧选择并丢弃过期响应。
- [ ] 运行新API、`test_local_workbench.py`、`test_local_materials.py`、`test_local_material_boundaries.py`、`test_api_controls.py`和`test_authorities.py`；用独立虚构工作区实际浏览器验证，不重置原账户。现有源码绑定清单按实际定位后重封证，不能关闭绑定检查。按身份约束提交。

## LIB07 本机实料接续、扩量与交付

**Files:** 新建`docs/LOCAL_LEGAL_LIBRARY.md`和`docs/testing/LOCAL-LIBRARY-ACCEPTANCE-20261014.md`；更新`docs/TASK_STATUS.md`及统一口径；实际数据证据在资料库`evidence/`与项目`.local/`。

**Interfaces:** 使用LIB01—06 CLI/服务，不另写一套直接SQL导入捷径。实料验收配置放忽略目录，固定来源批次、脚本版本、参数、清洗版本和查询集。

- [ ] 完成17,184法规导入，以及旧试点10,000条全部映射和原字节回查；比较来源数、重复候选、错误/未处理数。用不少于30个本地已知命中做结果回查（法规/案例各至少10，吉林至少5），另查无命中、无URL、历史版本；不将命中与法律结论正确等同。
- [ ] 在2025每个源文件中确定分层样本，先扩至100,000条；记录实际导入吞吐、磁盘放大、进程内存、查询冷/热耗时与10个并发只读客户端。验收目标为已知命中不漏、定位全匹配、常用查询P95≤2秒；未达标先改索引/分片，不能直接扩量或宣称服务就绪。
- [ ] 由100,000条实际结果估算全量空间/时间，再在资源边界内逐文件续导至3,837,307来源记录。每批记录成功/错误/未处理及原因；源去重展示与来源记录数分开。无需逐批向用户重复索要处理授权，只有来源变化、不可恢复失败或资源不足才停在检查点。
- [ ] 核对13文件完整hash、重叠记录候选、缺失字段与截断线索；如有失败，状态清楚列出而不把缺口填成已覆盖。覆盖报告必须可从输入来源数追到每条处理结果。
- [ ] 全量索引就绪后真实重启、检索、打开原文、导出，再跑全部已知命中及10个并发客户端，记录冷/热P95与资源；不能沿用10万条的性能结论。保存恢复及性能证据。法规与案例分别显示覆盖数和待核验状态；原试点和原件hash保持可核对。
- [ ] 执行新目标测试、所有实际受影响回归及仓库要求的schema/default/source/runtime开发检查；范围包含domain与启动时按仓库要求跑完整回归。检查依赖和MCP源绑定变化，仅封证已验证文件；不把历史通过数量复用为本轮通过。
- [ ] WorkBuddy只接收代码、虚构测试和脱敏统计独立复核；Codex核对发现、修复并重测。保存操作说明、命令/退出码/数量/覆盖范围与剩余风险，更新Obsidian；不上传云端、不发布、不声称Windows安装交付已完成。

## 执行方法与完成判定

推荐延续用户指定统筹方式：Codex在本会话逐任务实施，WorkBuddy独立复核，重要恢复/来源边界追加独立审阅；用户确认本计划后使用`superpowers:executing-plans`。不新建用户聊天，不为每个小步骤重复询问。

LIB01—06完成表示软件能力具备，LIB07实际数量与检索回查通过才表示本机资料可用。未完成阶段必须在页面与状态记录中显示；只完成法规或一万条不能报告2025全量完成。百度网盘历史年份、官方出处逐份补核、阿里云实际部署和Windows安装包仍为后续明确任务。
