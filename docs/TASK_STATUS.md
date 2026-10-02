# 任务实际状态

记录日期：2026-10-02，显示时区Asia/Shanghai；证据时间使用UTC。原仓库为空，用户已确认继续本目录。开发分支`codex/contract-review-v2`。

|任务|工程状态|实际完成|阻断/下一步|
|---|---|---|---|
|T00|ENGINEERING_PASS；PRODUCTION_BLOCKED|现状表、附件成员哈希核对、13来源51目标文件、许可全文证据、复用记录、来源校验器及28个用例|G11许可未批准；G05npm来源链未闭合；实际纳入的G10传递依赖/浏览器许可及生产批准待定；下一任务T01|
|新增Scrapling安装|LOCAL_TOOL_VERIFIED|0.4.15+fetchers，Chromium，CSS/XPath/HTTP/动态JS4项通过；28个wheel独立重算hash|仅开发工具，未集成业务流程，未测试真实网站|
|T01|ENGINEERING_PASS；PRODUCTION_BLOCKED|83个领域/嵌套模型、精确类型与UTC、四角色、18维与四类型schema、默认hash和已安装CLI；全套158 passed，独立审阅缺陷全部修复|只是数据/工程入口；运行依赖与build使用范围/安全/源供应链未生产批准；下一任务T02|
|T02|ENGINEERING_PASS；PRODUCTION_BLOCKED|关系表/外键/事务、实际会话/角色/成员、CSRF、不可变原件/审计/快照、版本变化失效；42目标/200全套 passed|独立42目标及10组事务/缓存攻击复验通过；突然崩溃恢复/部署/正式认证与签发尚未完成|
|T03|PREPARED / NOT_STARTED|文档安全/锚点计划、35包候选闭包核验，仅开发缓存未集成|开始安全DOCX部件/PDF逐页及精确锚点；OCR未部署|
|T04–T06|NOT_STARTED|尚无事实/规则/审查闭环|实现四类虚构合同离线演示；QCC保持关闭|
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
