# 任务实际状态

记录日期：2026-10-02，显示时区Asia/Shanghai；证据时间使用UTC。原仓库为空，用户已确认继续本目录。开发分支`codex/contract-review-v2`。

|任务|工程状态|实际完成|阻断/下一步|
|---|---|---|---|
|T00|ENGINEERING_PASS；PRODUCTION_BLOCKED|现状表、附件成员哈希核对、13来源51目标文件、许可全文证据、复用记录、来源校验器及28个用例|G11许可未批准；G05npm来源链未闭合；实际纳入的G10传递依赖/浏览器许可及生产批准待定；下一任务T01|
|新增Scrapling安装|LOCAL_TOOL_VERIFIED|0.4.15+fetchers，Chromium，CSS/XPath/HTTP/动态JS4项通过；28个wheel独立重算hash|仅开发工具，未集成业务流程，未测试真实网站|
|T01–T06|NOT_STARTED|尚无应用业务代码|下一阶段实现统一模型、权限、解析、事实、规则和四类虚构合同闭环；QCC保持关闭|
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

完整T00失败过程与范围见`docs/testing/T00.md`。安装原始日志、本地HTML运行证据和wheel缓存在被Git忽略的`.audit-local`，可提交的版本与hash记录在`requirements-scrapling-windows-py312.lock`及`sources/scrapling-wheel-hashes.json`。未上传真实材料、注册付费账户或调用企查查。

## 决策与未支持项

- 用户明确确认空仓库；采用新仓库默认架构，原地分支工作；无现有可用代码可替换。没有重建Git历史。
- 用户新增Scrapling安装要求覆盖规格对G10暂缓安装的默认建议；只安装为开发工具，未自动启用法源批量抓取、QCC或真实资料处理。
- source锁的read_verified表示选取文件与许可证据可读，不能替代依赖、实际效果或律师批准。G11根CC许可不能替代目标AGPL，GNU通用许可全文也不能替代授权。
- 许可指纹只能防已知完整副本和已登记片段进入常见运行目录；不能认定任意改写、短片段或未知来源已获许可。未来新增运行目录必须纳入扫描。
- 未实现：审查API/UI、18维业务审查、四类样本闭环、预算网关、Word报告与原生修订、OCR、真实MCP/QCC联调、法律样本测评和生产部署。
