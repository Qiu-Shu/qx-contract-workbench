# 任务实际状态

记录日期：2026-10-03，显示时区Asia/Shanghai；历史阶段记录保持原日期，证据时间使用UTC。原仓库为空，用户已确认继续本目录。开发分支`codex/contract-review-v2`。

|任务|工程状态|实际完成|阻断/下一步|
|---|---|---|---|
|T00|ENGINEERING_PASS；PRODUCTION_BLOCKED|现状表、附件成员哈希核对、13来源51目标文件、许可全文证据、复用记录、来源校验器及28个用例|G11许可未批准；G05npm来源链未闭合；实际纳入的G10传递依赖/浏览器许可及生产批准待定；下一任务T01|
|新增Scrapling安装|LOCAL_TOOL_VERIFIED|0.4.15+fetchers，Chromium，CSS/XPath/HTTP/动态JS4项通过；28个wheel独立重算hash|仅开发工具，未集成业务流程，未测试真实网站|
|T01|ENGINEERING_PASS；PRODUCTION_BLOCKED|83个领域/嵌套模型、精确类型与UTC、四角色、18维与四类型schema、默认hash和已安装CLI；全套158 passed，独立审阅缺陷全部修复|只是数据/工程入口；运行依赖与build使用范围/安全/源供应链未生产批准；下一任务T02|
|T02|ENGINEERING_PASS；PRODUCTION_BLOCKED|关系表/外键/事务、实际会话/角色/成员、CSRF、不可变原件/审计/快照、版本变化失效；42目标/200全套 passed|独立42目标及10组事务/缓存攻击复验通过；突然崩溃恢复/部署/正式认证与签发尚未完成|
|T03|ENGINEERING_PASS；PRODUCTION_BLOCKED|安全DOCX/PDF摄取、受限XML、部件/逐页盘点、精确版本锚点；69目标/269全套 passed；独立69目标+14攻击探针 passed|OCR/全面视觉等价/PDF解码进程沙箱未部署；G06运行采用已登记；G06/G10生产门禁仍阻断；下一任务T04|
|T04|ENGINEERING_PASS；PRODUCTION_BLOCKED|事实候选/原件信任核验、完整版本确认、Decimal AST/单位/真步长计算、主体明确选择；76目标/345全套 passed|独立76目标/31探针/181回归通过；来源污染P2闭合；模型/外部收据/正式签发仍未支持；下一任务T05|
|T05–T06|NOT_STARTED|只读接口/测试预检和细化计划就绪，尚无规则/审查闭环|T04完成后继续四类虚构合同离线演示；QCC保持关闭；真实规则批准缺失|
|T07–T10|NOT_STARTED|候选来源可读，不代表接口已实现|真实外查缺账户、工具、价格、许可；修订和UI未实现|
|T11–T12|NOT_STARTED|已核对规格含84个唯一编号，不是84项测试通过|实际回归映射、律师金标准、部署/恢复未实现|
|T13|BLOCKED_LIVE / NOT_STARTED|没有真实联调或上线决定|账户/许可/规则批准/金标准/模型数据政策/环境与预算缺失|

## T00实际执行

|命令|退出码|实际结果|
|---|---|---|
|`git status --short --branch` 初始|0|No commits yet on master，业务文件0|
|`rg --files` 初始|1|没有可列出业务文件，非应用测试失败|
|`python .audit-local/reference_inspect.py inventory/consistency`|0|附件两个zip共6文件哈希匹配；配置哈希匹配；84唯一规格编号|
|公开来源审计及hash重算|0|13来源、51选取目标，51 hash匹配；未取得任何production批准|
|`.venv/Scripts/python.exe -m pytest tests/unit/test_sources.py -q` RED|1|12 failed，实现缺失的明确断言|
|同目标补强RED|1|3 failed/12 passed：指纹证据与运行标记行为缺失|
|审阅修复RED|1|11 failed/15 passed：等价路径、虚假批准、类型、许可文件及改名复制等|
|`.venv/Scripts/python.exe -m pytest tests/unit/test_sources.py -q --tb=short` GREEN|0|26 passed，0 failed|
|G11畸形文件记录RED→GREEN|1→0|先2 failed/26 passed，再28 passed，非字典文件记录返回FILES_INVALID而非崩溃|
|`.venv/Scripts/python.exe -m pytest -q --tb=short` 全套最终|0|28 passed；当前只有T00用例，不代表后续任务验收|
|`python scripts/verify_sources.py --mode development`|0|checked_sources=13，errors=[]；13条NOT_PRODUCTION_APPROVED警告|
|`python scripts/verify_sources.py --mode release`|1|真实锁返回DEPENDENCY_REVIEW_PENDING:G10、PRODUCTION_APPROVAL_MISSING:G10，符合预期门禁|
|`.venv/Scripts/python.exe -m pip check`|0|No broken requirements found|
|`python scripts/scrapling_smoke.py --output .audit-local/scrapling-smoke-parent.json`|0|父独立复跑4/4通过，2次本地/sample请求，QCC0|
|28个实际wheel独立SHA-256重算|0|28/28与审计hash一致|
|`pip install --dry-run --ignore-installed --require-hashes --no-index --find-links .audit-local/scrapling-wheelhouse -r requirements-scrapling-windows-py312.lock`|0|本地wheel解析28项安装计划；哈希锁可被pip接受；非完整重装或生产恢复演练|
|Git索引blob独立hash检查|0|51个来源目标+指纹文件，共52/52匹配；`.gitattributes`禁止证据换行转换，保持原始字节|

完整T00失败过程与范围见`docs/testing/T00.md`。安装原始日志、本地HTML运行证据和wheel缓存在被Git忽略的`.audit-local`，可提交的版本与hash记录在`requirements-scrapling-windows-py312.lock`及`sources/scrapling-wheel-hashes.json`。未上传真实材料、注册付费账户或调用企查查。

## 决策与未支持项

- 用户明确确认空仓库；采用新仓库默认架构，原地分支工作；无现有可用代码可替换。没有重建Git历史。
- 用户新增Scrapling安装要求覆盖规格对G10暂缓安装的默认建议；只安装为开发工具，未自动启用法源批量抓取、QCC或真实资料处理。
- source锁的read_verified表示选取文件与许可证据可读，不能替代依赖、实际效果或律师批准。G11根CC许可不能替代目标AGPL，GNU通用许可全文也不能替代授权。
- 许可指纹只能防已知完整副本和已登记片段进入常见运行目录；不能认定任意改写、短片段或未知来源已获许可。未来新增运行目录必须纳入扫描。
- T01的Pydantic类型校验不能替代实际权限、来源批准、费用或签发；标准JSON往返保持事实Decimal/日期类型。全部默认参数来自同一JSON，并生成实测配置hash。
- 未实现：审查API/UI、18维业务审查、四类样本闭环、预算网关、Word报告与原生修订、OCR、真实MCP/QCC联调、法律样本测评和生产部署。

## T01实际执行

|命令/验证|退出码|实际结果|
|---|---:|---|
|领域/配置/CLI首次RED|1|领域56 failed；配置/CLI14 failed，功能缺失断言|
|独立审阅修正RED→GREEN|1→0|修复--file被忽略、非规范角色、事实JSON丢类型/单位、ModelRequest别名往返；逐轮失败与通过记录在T01-domain/config/review|
|`python -m pytest -q --tb=short --junitxml=docs/testing/T01-results.xml`|0|158 passed；111领域、19配置/CLI、28来源门|
|`python -m cn_contract.cli schema`及`schema --check`|0/0|保存schema来自唯一ReviewRun模型，实际核对一致|
|`scripts/verify_defaults.py --file config/defaults.json`|0|hash与v2.0完全一致|
|可编辑安装、控制台help/config、pip check|0|实际安装qx-contract-workbench0.1.0，console及模块入口可用|
|两个锁本地wheelhouse dry-run hash验证|0/0|应用/测试11包与build1包分别可解析；没有称完整重装|
|独立定向审阅|0|50 passed/61 deselected；4规范角色、7类值/Decision16次往返、Decimal单位、alias、schema修正均核对|

运行依赖的12个wheel、32份许可/NOTICE已保留证据，全部development/read_verified；这不构成生产批准。83个模型能生成schema不等于83项业务功能已实现。详细记录见`docs/testing/T01-domain.md`、`T01-config.md`、`T01-review.md`及`docs/reuse/RUNTIME-dependencies.md`。

## T02实际执行

已按本地hash锁安装SQLAlchemy2.0.54、FastAPI0.142.2、pwdlib0.3.1/Argon2及完整28包闭包；安装退出0，pip check退出0，重新editable安装退出0。测试工具升级pytest9.0.3后，T00/T01的原158项独立复跑退出0；记录旧8.4.2公开告警，保留原阶段历史分母。父节点本地wheelhouse ignore-installed hash dry-run实际28包退出0，详见`docs/reuse/T02-dependencies.md`。

T02最终父节点实际`pytest -q --tb=short --junitxml=docs/testing/T02-results.xml`退出0：200 passed、1条Starlette对httpx TestClient的弃用警告；未隐藏该警告。独立审阅42目标测试/10组攻击探针退出0，发现的Session.close/保存点清理与缓存归档状态缺陷已真实RED→GREEN并独立复验关闭。细节见`docs/testing/T02.md`、`T02-review.md`。DB技术权限与测试中的虚构审批不能替代正式签发；进入approved仍明确NOT_IMPLEMENTED。

本阶段已本地提交：`ef8b5ac`（T00与Scrapling工具），`a0d7ec4`（Windows检出保留证据字节）；提交作者为Codex，不改全局Git身份，不推送或对外发布。第三方原始证据中的尾随空格保持原样，不清理而破坏来源hash。

后续本地阶段提交：`ca230d6`（T01）、`f30ea73`（T02）、`15c7a6a`（T03）。各阶段保留自己的实际测试分母；未推送。当前沿同一分支增量执行 T04。

## T03 实际执行

先实际 56 failed/0 errors（功能缺失断言），补最小解析后通过；随后为资源限制和独立审阅的漏读缺口补真实失败测试。父节点最终 `.venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=docs/testing/T03-results.xml` 退出 0：269 passed，1 条既有 Starlette/httpx 弃用警告，21.06 秒。独立审阅 69 目标和 14 攻击探针退出 0；四组 P2 的表格容器、PDF 注释、DOCX 缩略图和不可见文字已修复并关闭。全部使用独立虚构材料。失败过程、收集错误及具体边界分别见 `docs/testing/T03.md`、`T03-review.md`、`T03-parent-checks.md`，不把辅助或收集错误计作有效功能 RED。

35 包应用/测试完整闭包已正式合并并实际安装核验，旧 T02 28 版本及构建证据保留；35 wheel/60 许可/40 依赖边与安装元数据一致，新增 7 安装 hash 一致，离线 hash-lock dry-run 与 pip check 退出 0。G06 两份已读源文件与实际 wheel 字节一致；这不证明整个源构建。来源开发门 13 项退出 0，发布门退出 1，实际阻断 G06/G10 的依赖审查与生产批准。默认 hash、schema 均核对通过。

PDF read 仅指已提取文字层；扫描页、图片、交互注释、不可见渲染和其他未读对象有明确 manual/unsupported。原件不可覆盖，parse 另存快照；baseline、错案及锚点由实际会话和后端原件核验。没有 OCR、全面视觉语义、独立 PDF 解码沙箱、真实试点或生产完成。继续 T04–T06 构建事实确认与四类 QCC-off/mock 审查流程。

## T04 实际执行

最终76目标中的首批56先真实RED（56 failed/0 errors），实现后逐项补来源、事务、百分比换算、期间证据和Decimal环境边界RED→GREEN。独立审阅实际助手会话追加伪quote解析仍被信任，两个攻击测试先失败；现复用T03 pure adapter从T02授权只读原件重算完整ParseResult，quote、全部anchor和未读/质量标记均核对，两个入口实际阻断。不重写T02/T03或修改原件。

父节点最终 `.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T04-results.xml` 退出0：345 passed、1条既有Starlette/httpx弃用警告、32.59秒。独立76目标/31攻击探针/181受影响回归退出0，原文信任根P2关闭。defaults、schema、pipcheck及13项来源开发门退出0；来源release仍因G06/G10审批/依赖使用范围待审退出1。实际失败历史和边界在 `docs/testing/T04.md`、`T04-review.md`、`T04-parent-checks.md`。

确认快照以expected current→new+1完整追加，保序hash和历史确认人不变，决定reason仅受保护记录；服务保存点在caller捕获错误继续提交时也无半写。主体候选不会根据排序确认或作为企业entity ID，变化使批准/制品失效。计算白名单AST/Decimal，前月实付及期间需确认，不用年费/12猜测；数学和历史回放明确限制。

用户新增本地Obsidian工作流已更新AGENTS。检索没有本项目已有状态；结构化memory_record当前未提供，实际obsidian_local新增本地摘要/索引/链接并成功读回，不冒称API成功或索引缓存同步。没有私人笔记进入Git或运行prompt。法律规则、业务审查闭环、真实外查、律师验收和生产批准继续分别登记。
