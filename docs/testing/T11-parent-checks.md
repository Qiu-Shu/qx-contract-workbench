# T11 根节点实际核验

当前评测机制 ENGINEERING_PASS，法律基准与生产仍 BLOCKED，记录UTC。T10本地提交c0e1fc2是开始基线，不把T10工程709项和Word/浏览器记录继承为T11通过。

## 首次评测诊断

根实际命令 `.venv/Scripts/python.exe -X utf8 -m cn_contract.cli evaluate --suite tests/acceptance/cases.json --offline --output .local/t11-parent-evaluation-20261003T085755Z.json`，08:57:37.887541–08:59:56.412939 UTC，退出1、138.525398秒。它确实运行147固定节点展开的316工程断言，JUnit全部PASS，再实际摄取/解析/确认40独立虚构DOCX并产生40条18维mock审查。

84原规格能力结果：5PASS、36NOT_RUN、16NOT_IMPLEMENTED、7NOT_SUPPORTED、20BLOCKED、0FAIL，总数84；58行guard通过单列。40材料工程结果39PASS/1NOT_SUPPORTED，家族16、开发24/预留blind16；作者已看全部材料，没有实际律师盲测。gold pending、两reviewer null，法律召回/精确/锚点/正确率、现实费用和人工分钟均unknown，readiness BLOCKED。退出1是明确拒绝发版的结果，不能把它写成全能力PASS。

根独立辅助核验 `.venv/Scripts/python.exe -X utf8 .audit-local/t11_parent_verify.py .local/t11-parent-evaluation-20261003T085755Z.json --output .audit-local/t11-root/first-diagnostic-verification.json` 实际退出0：84原编号/场景/预期/任务/来源相同，8项旧raw基线保持，40当前材料/framework/evidence hash匹配；底层SQLite integrity/FK正常，40review_runs，query_ledger0、正式approval0、model provider均mock。报告SHA256 `d54c9c9987063e1ab62fde17ed1dc5e5c6b06fc0b94f43b46c3dbbc7fbe8fe4e`。

首次runner source_stable仅覆盖当时子集：独审随后实际指出16个消费helpers/旧raw/scripts/locks等漏计、pytest error混入failure；另framework形状/duplicate physical路径/异常ZIP三组P2真实负测失败。因此首次制品保留为修复前诊断，不能作为最终封证；最后必须同probe复验与修复后新制品，不能覆盖首次结果。

## 其它真实命令

每条的argv、UTC开始结束、真实child退出码、原输出SHA在 `.audit-local/t11-root/commands/<name>/command.json`；wrapper按child实际退出码退出，没有把阻断包装为成功。

|命令|退出|实际结果|
|---|---:|---|
|`scripts/verify_defaults.py --file config/defaults.json`|0|默认hash保持0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887|
|`-m cn_contract.cli schema --check`|0|保存ReviewRun schema与当前唯一DTO一致，未重写schema|
|`-m pip check`|0|No broken requirements found，未安装新依赖|
|`scripts/verify_sources.py --mode development`|0|13来源、errors0、13未生产批准提示|
|`scripts/verify_sources.py --mode release`|1|9真实来源/批准阻断|
|`-B -S scripts/verify_runtime_dependencies.py --mode development`|0|55正式包+build1、native_build_verified=false、network_calls0|
|同runtime `--mode release`|1|59真实批准/生产阻断，未伪造approved字段|

runtime纯模式显式固定child PYTHONPATH到本项目site-packages，仅为pure packaging解析，未执行.pth或原生构建；此处与正常应用40sample流程的原生库导入范围分别记录。Word、普通浏览器、OS全局网络捕获、真实模型与QCC本T11评测未执行，真实金标准和生产仍阻断。

根memory_read首次limit6500被工具上限拒绝，改6000后实际读取成功；不是索引不可用或检索不到。读取尚未写出的作者文档只属只读路径诊断，未当功能RED。

## 同步诊断：真实硬门与输入漂移

09:07:12 UTC 根并行启动候选CLI与全套；作者此前新增NEW04/NEW16硬门测试已真实RED，登记表两标记仍False。同步后全部源保持不改直到检查完成；这些运行均是诊断，文件名包含final也不能改其实际含义。

全套命令 `pytest -q --tb=short --junitxml=docs/testing/T11-results.xml` 实际退出1，2 failed /738 passed /0 errors/0 skipped/0 warnings，280.76秒；两失败完全是NEW04/NEW16 guard FAIL被算BLOCKED而非NO_GO。原JUnit复制保存在`.audit-local/t11-root/full-hard-guards-diagnostic.xml`，日志/UTC/argv在commands/full；修复后的新全套另列，不能把已失败JUnit覆盖后当旧命令通过。

候选CLI真实退出1、183.107387秒，316注册断言正常完成且40run仍39PASS/1NS，但source_stable=false，故能力0PASS/41NOT_RUN/16NI/7NS/20BLOCKED。根独立diff实际634输入，仅README.md不同：泛扫上游manifest相对文件字符串把本仓README也纳入；作者仅写docs/README，没有业务漂移。这是报告正确保守降级，保留candidate-source-current-diff.json；最后要稳定全部列出输入，或按实际消费路径纠正范围，不可假称这次source_stable。

独立真实三参数pytest中断还产生exit2和无classname/name testcase，原runner KeyError；外层实际1 failed，不能把缺失参数认证为全函数PASS。作者将补正式RED、受控统计及中断策略，再同探针复验。独审首function batch40阶段因自身新输出根叠UUID超过Windows路径长度退出1，底层316断言实际完成、40创建0；这是自有环境诊断，不冒充40结果或能力RED，后续采用其自有短路径。

## 修复后最终真实执行

全部已发现缺陷由作者真实失败测试修复，正式目标37项与独审同探针闭合。根实际CLI使用新输出 `.local/t11-parent-evaluation-certified-20261003T092400Z.json`，09:23:17.066616–09:25:56.385548 UTC，真实exit1，159.318932秒；报告SHA256 `9edb88687463c4887e5b0a55952b2a4c530507b76dad43573f31da4363d5fe20`。固定147函数入口展开316参数，原生collection记录与JUnit节点逐项相等，316实际PASS、0失败/错误/跳过，source_stable=true。84能力仅5PASS/36NOT_RUN/16NOT_IMPLEMENTED/7NOT_SUPPORTED/20BLOCKED，58guard单独列，readiness仍BLOCKED。

40新材料实际摄取/解析/确认/18维mock run：39工程PASS/1NOT_SUPPORTED，底层40条review_runs、原件hash一致、SQLite integrity/FK正常、query_ledger0、formal approvals0。16家族/24dev16预留blind，不代表两位律师盲测。法律四指标、实际费用和人工分钟为空，真实模型/QCC请求0。根独立 `.audit-local/t11_parent_verify.py` 于09:30:13 UTC退出0，记录 `.audit-local/t11-root/certified-verification.json`，核对原规格84及8项不可变旧基线、全部当前fixture/framework/证据、collection/hash/SQLite。

根最终全套真实 `pytest -q --tb=short --junitxml=docs/testing/T11-results.xml` 于09:23:17.066616–09:27:25.196104 UTC执行，exit0：746 passed、0 failed/errors/skipped/warnings，pytest输出245.62秒（包装总248.129488秒）。JUnit SHA256 `b0211f500e6f30a4a89d5e5cd1ed00e8e3650856d054f6e2a97a0ae037740300`；只对本次最终结果生效。

作者冻结 `ce0e47206992f21e7838819182cb403e3781748fe1502171649d6a4e94737961` 中644个实际输入及15份独立RED/GREEN证据在最终执行前后均无漂移；后续追加最终文档另列明确delta，不冒称旧freeze覆盖更新文档。API独审seal `9932d19586e1c4caac81fea592b6a33f33de0d8c78ea591ac11af866a4f8268c`、材料seal `4fd93bd5c18219a30b26127c579fae1802e0598c94a35ccbe3b630988ae60283`。T12/T13预检仅NOT_RUN；本地提交不对外推送、不代表生产完成。

根09:31:45 UTC独立重算两seal：API当前660/自有631、材料当前173/自有4263全部零漂移，helper exit0，记录independent-seals-current.json。此前一次内联辅助脚本因PowerShell字符串引用退出1，未导入应用、未执行功能断言、不是功能RED；改为独立文件后实际重算通过。

提交整理明确delta：作者只追加T11.md最终实际结果，并去两个新测试的EOF空行（各1 byte，AST不含位置属性完全一致），不是业务修复；746全套不重复运行。原ce0/f9及两独审历史seal保留，不再宣称其raw范围覆盖新文档/空行；当前作者seal `d2cc7a580918ce11ec7e31861729b818753db8931852c47bdf71cff1fe6a7257` 保644输入/15 XML。首次Git check实际exit1指出这两空行，整理后的实际check结果及314受保护Git blob核对另随提交记录。

09:33:39 UTC最终stage helper exit0：87路径、314受保护raw实际index==working bytes、8旧基线==c0e、14工程Python按LF相等；私有目录/DB/secret环境文件入stage为0。随后git diff --cached --check实际exit0；当前作者644/15证据重算0差异。最后仅追加本条实际结果并暂存文档，没有重新修改受保护输入或代码。
