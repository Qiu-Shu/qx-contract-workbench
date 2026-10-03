# T07 父节点实际验收

2026-10-03；workspace `D:\Documents\ChatGPT\律所项目`，分支 `codex/contract-review-v2`。状态 ENGINEERING_SYNTHETIC_PASS / BLOCKED_LIVE / PRODUCTION_BLOCKED。只有独立虚构本机协议和工程验证，没有真实QCC、模型、费用、私人材料上传或生产批准。

|命令/证据|退出码|实际结果|
|---|---:|---|
|`.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T07-results.xml`|0|557 passed，0 warnings，94.57秒；JUnit failures/errors/skipped均0|
|`scripts/verify_defaults.py --file config/defaults.json`|0|canonical SHA `0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887` 未变|
|`python -m cn_contract.cli schema --check`|0|唯一ReviewRun schema精确一致|
|`python -m pip check`|0|No broken requirements found|
|`scripts/verify_sources.py --mode development`|0|13来源，errors=[]，13条NOT_PRODUCTION_APPROVED警告|
|`scripts/verify_sources.py --mode release`|1|G06/G10/G13各DEPENDENCY_REVIEW_PENDING与PRODUCTION_APPROVAL_MISSING，共6个实际阻断|
|`git diff --check`|0|当前工程差异检查通过；原始来源/许可/锁按实际bytes保留|
|重算`.audit-local/t07-implementation-hashes.json`|0|81/81 frozen files bytes/SHA匹配，inventory SHA `c2eca758af2f50da68d5130503bdc50009c5c914916a02f2c27af91ccc2559e8`|
|独立冻结正式目标/攻击/必要授权回归|0/0/0|46/66/17 passed，分别14.11/38.43/7.15秒，均0 warnings，详见T07-review|
|独立依赖审计|0|51 wheel / 92主许可 / 76条件依赖边；3120 installed RECORD哈希；SDK源文件及许可匹配；原53环境版本保留，新增15实际安装，当前环境68|
|`.venv/Scripts/python.exe -X utf8 .audit-local/t07_parent_stage.py` 最终|0|81冻结文件/JUnit557先核验，明确97路径暂存；222受保护来源/锁/fixture索引bytes一致，5固定fixture及正式lock SHA匹配，工程cached diff通过|

依赖正式lock SHA为`50c19c2701a9609ed9afddcd3bf73c1a631df25711b2150f6255155d59de618a`，manifest SHA为`8acdae77590e638f3ea5e8c2aa8515a5d0a0d491782729fafff3fdfb0375cf9e`。build1包/17许可保持独立。安装只从本地已核验wheel通过file://及hash锁进行；pywin32普通启动自动bootstrap实际发生，不将“未手动postinstall”冒称未加载原生启动代码。生产及原生使用审批为空，未安装未来T09/T10候选。

T07的RED→GREEN和辅助失败分别保存在T07.md及T07-review.md。独立最终首轮时间篡改测试未保证新旧时戳不同，65pass/1辅助失败保留；改为原时戳加一天并assert不等后，同一冻结代码66项完整通过，没有业务修改。只有真实功能断言失败计RED，不把collection、错误fixture或shell quoting计功能缺失。

协议实际使用已安装mcp/mcp-types2.2.0、httpx2/httpcore2 2.13.1及独立本机MCPServer/uvicorn，initialize/list/call计数由真实本机服务记录。公开schema外部引用、任意endpoint、反射秘密、未批准binding、未知工具均零业务call。raw SHA是完整canonical安全响应的hash，不是wire原字节；没有响应/秘密保护拒绝时记录明确safe_error_summary。partial success仍保留pages不全；未知发送不能成为无风险。

本阶段raw/invoke随caller事务保存，caller rollback仍能撤销模拟收据；T08需显式Database工厂和短事务持久reserve/send marker，网络期间不持写事务。未声称已具备付费收据崩溃持久性。T06四份固定DOCX和实际demo已验收，没有重做或扩展真实材料入口。T08预算、T09原生修订/视觉验证、T10UI及T11–T13实际验收仍待逐任务执行。

提交前完整`git diff --cached --check`实际exit2：jsonschema METADATA的RST标题和PyJWT AUTHORS.rst标题的等号下划线被识别为leftover conflict marker，均与已核验第三方原始bytes一致，没有Git冲突。不能为使检查通过修改许可或证据。工程差异改用`git diff --cached --check -- . :(exclude)sources/**`；所有sources、锁与固定fixture另外逐一核对Git索引blob和本地原bytes，提交只在该组合检查成功后进行。初次失败保存在本地命令记录，不计功能RED或全范围diff PASS。

首次raw索引检查实际exit1，发现三份既有build/Scrapling锁仍是历史LF索引而本地为原CRLF；全部来源与fixture匹配，正式T07 requirements.lock也匹配。新增`requirements*.lock -text -whitespace`后对这三条明确路径使用`git add --renormalize`，不改内容/依赖版本/许可或安装；仅保存实际本地原锁bytes。这次失败后没有提交，重算所有protected索引必须exit0才提交。
