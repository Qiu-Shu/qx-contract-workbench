# T11 独立注册 / 执行证据 / 硬门审阅

独立工程审阅完成：当前源码上 64 项自有检查、37 项正式目标复验全部通过；固定147节点的真实 collection 316 项与原生 JUnit 316 项精确对应，全部通过。原84项完整能力只有5项 PASS，40份材料仅证工程流程，readiness 仍为 BLOCKED，不能称律师金标准验收或生产完成。

审阅者仅写 `.audit-local/t11-api-review/` 与本报告，未修改业务、正式测试、状态、锁、Vault 或 Git。根节点负责全量、有效suite的正式CLI、网络、Word 与提交；T10 的历史通过不继承为 T11 PASS。

## 范围与证据口径

已读 AGENTS、TASK_STATUS、T11-detail / preflight / current-preflight / execution、v2.0 §14 全部原始编号及场景，并读当前 registry、definitions、runner、sample_runner、domain、CLI 与正式目标。准备矩阵 `matrix-preparation.json` 保留当时 44 V1 +24 AUD +16 NEW=84 项 NOT_RUN；准备脚本只读文本与哈希，缺实现路径的 exit1 是历史诊断，未计功能 RED。

独立静态注册、可信路径/文件名/hash、客户端 PASS/entrypoint 注入拒绝、六状态分母、禁止任意 shell/eval/runpy/import、未批准模式先阻断、律师 gold pending/null、法律准确率等指标 null 与硬失败 NO_GO 使用真实应用函数核验。隔离技术状态夹具只用于聚合器检查，不能代表 84 项原场景执行。实际子 pytest、真实 JUnit、真实仓内 shadow 输入改变与子进程异常退出用于执行证据审计，没有伪造 subprocess 返回值或 XML。

`case.fixture` 是 catalog 参考/场景索引，注册节点可能自产不同虚构输入；40 份材料的实际 T02–T06 处理独立计分，不替代原 84 场景的完整能力。新材料是短工程片段，24 开发/16 预留盲测按完整框架家族隔离；作者已见全部材料，并无两位真实律师盲评。T06 旧五 raw 原字节保留。真实模型、QCC、付费、真实材料上传、Word、普通浏览器与全局网络抓包均未由本审阅者执行。

## 实际结果

所有外层命令使用 `.venv/Scripts/python.exe -X utf8 .audit-local/t11-api-review/run_review.py <label> <明确目标>`，脚本在同目录保存原始 `.log` / `.xml` / `.json`，记录完整 argv、UTC、退出码、实际 JUnit 数量及输入前后 hash。下表为真实历史，未覆盖旧记录。

| label / 目标 | 实际数量 | exit / 秒 | 输入前后 | 解释 |
|---|---:|---:|---|---|
| registry-first / 独立 registry | 40 PASS | 0 / 2.80 | 相同 | 两条自有 string-enum 序列化 warning，未计业务失败 |
| registry-adapted / 同组 enum oracle 校正 | 40 PASS，0 warning | 0 / 2.88 | 相同 | 只改自有 probe 使用真正 Enum |
| execution-first / snapshot、JUnit计数 | 2 FAILED | 1 / 0.83 | 相同 | 两项真实业务 RED，见下文 |
| gates-first / 阻断、聚合、固定节点、缺节点 | 14 PASS，0 warning | 0 / 4.65 | 相同 | 节点执行与参数化名称实际绑定；缺节点不是 PASS |
| execution-extended / 加真实 crash、helper 改变 | 1 PASS / 3 FAILED | 1 / 1.81 | 相同 | 新失败仍是 snapshot 缺输入同一缺陷；没有声称 shadow 节点误标 PASS |
| execution-fixed / 同4项修后 | 3 PASS / 1 FAILED | 1 / 25.79 | 相同 | 余项是自有 oracle 误要求新增技术夹具的生成 pyc；保留原日志 |
| independent-final / 排缓存后原58项 | 58 PASS，0 warning | 0 / 46.00 | 相同 | 原两项执行证据缺陷真实同 probe 关闭 |
| independent-stable / 加 server 硬门2项 | 58 PASS / 2 FAILED，0 warning | 1 / 53.73 | 相同 | NEW-04 / NEW-16 hard_gate 仍 False；作者先发现缺陷的独立佐证，尚未修复 |
| partial-interrupt-red / 真实参数中断 | 1 FAILED，0 warning | 1 / 0.93 | 相同 | child exit2 的原生空 testcase 使应用抛 KeyError，是真实未受控解析缺陷 |
| partial-interrupt-fixed-plus / 中断修后及相邻exit1 | 1 PASS / 1 FAILED，0 warning | 1 / 1.34 | 相同 | 原exit2 GREEN；exit1只跑首参数却整函数PASS仍真RED |
| partial-collection-red / 加原生导入错误 | 1 PASS / 2 FAILED，0 warning | 1 / 1.68 | 相同 | 另有实际collection ERROR1被漏记为0 |
| partial-exit-zero / 根请求同家族exit0 | 1 FAILED，0 warning | 1 / 0.91 | 相同 | 真exit0只跑首参数却整函数PASS，非oracle失败 |
| independent-final-current / 最新四自有文件 | 64 PASS，0 warning | 0 / 16.11 | 相同 | 40 registry +16 gates +4 executor +4 native异常；所有同probe闭合 |
| formal-final-current / 四个明确正式目标 | 37 PASS，0 warning | 0 / 24.90 | 相同 | case_registry / acceptance_evidence / acceptance gates / evaluation_cli |

首个独立147节点+40材料 function批次 exit1：原生JUnit316全部PASS，但自有输出根双UUID叠加导致Windows WinError206。DB matters / document_versions / review_runs实际全0，没有完成report；因此首轮 capability NOT_CERTIFIED、40 NOT_RUN_COMPLETE、全流程输入稳定性 NOT_MEASURED_COMPLETE。保留 `batch-first-diagnostic.json` 与原目录，不把自有输出选择问题算业务RED。

最终实际命令 `.venv/Scripts/python.exe -X utf8 .audit-local/t11-api-review/run_batch.py b1`，退出0；UTC 2026-10-03 09:21:14.898145 至09:23:38.567019，实际function流程143.67秒（是本机混合工程运行时间，未冒充人工复核用时）。自有短根b1保留start、完整stdout/stderr、退出码、应用JSON、原生JUnit、真实collection JSON及所有结果hash。

147个固定函数选择器实际展开316个参数用例；collection精确nodeids集合与全部316具名JUnit结果完全相同，316PASS、0FAIL / ERROR / SKIP、0warning。独立选定核心/测试/helpers/旧5raw/新40材料/16框架/manifest/规则/schema/prompt/锁/脚本与实际声明cache输入前后hash相同。根的CLI/full为独立来源，不合并成本审阅者数量；37回归中确实运行CLI help与非法输入拒绝，元数据 `actual_cli=NOT_RUN_BY_REVIEWER` 指未执行有效suite的正式完整CLI验收。

| 分母 | 当前实际结果 | 口径 |
|---|---|---|
| 原始84场景 | PASS5 / FAIL0 / NOT_RUN36 / NOT_IMPLEMENTED16 / NOT_SUPPORTED7 / BLOCKED20 | 完整PASS仅V1-D07、V1-Q08、V1-Q09、NEW-01、NEW-14；其它能力不因guard/partial转PASS |
| 注册guard行58 | 58 PASS | 可复用安全断言分母；部分复用同节点，不是58份独立法律样本 |
| 新虚构材料40 | 工程PASS39 / NOT_SUPPORTED1；40件真实T02–T06流程 | 各40 matter / document_version / review_run，120 durable mock attempts、全部18维；人工确认仅工程身份 |
| 原件与对外门 | 40 protected original.bin，实际hash集合=40登记hash | query_ledger / query_records / approvals / exports实际全0；真实模型、QCC默认关闭 |
| 律师gold与法律指标 | pending / 两位reviewer null / disagreements pending；全部指标null | 95/85/99为待批准目标；cost / human_review_minutes仍null；readiness BLOCKED |

报告：`.audit-local/t11-api-review/b1/independent-report.json`（SHA-256 `377dd763bc82bcac8c350203e445752cfbfa3447a60d48911c49b1faf21f0e44`）；逐材料JSON、DB原件及完整输入/产物验证为同目录 `independent-verification.json`。

## 已确认缺陷与修复

1. **P2：消耗输入漏入执行快照。** 首次实际 `_source_snapshot` 缺 16 个已消费路径：五个 helper、T06 五 raw、两把来源/运行依赖锁、requirements、pyproject 与两脚本。真实仓内 shadow 子 pytest 1 PASS，实际 helper 从 True 改 False，但 `source_stable=True`。此 shadow JUnit 的 classname 带隔离父目录前缀，其节点结果本来是 NOT_RUN；缺陷是稳定性声明错误，不能声称伪 PASS。作者补全固定输入/缓存字节、排生成 `__pycache__/pyc` 后，同真实 helper 变更探针和原16路径检查 GREEN。
2. **P2：JUnit error 混入 failed。** 可信自有技术 fixture 实际 6 用例 =3 PASS /1 assertion FAILURE /1 setup ERROR /1 SKIP，exit1；旧证据输出 failed2/errors0。作者分别记录原生 failed/errors 后同真实 child/JUnit 探针 GREEN。故意失败的内层 fixture 不属于原84，不把其 inner failure 说成应用业务失败。
3. **两原规格硬门遗漏已关闭。** 实际服务器返回 NEW-04（锚点错位）、NEW-16（未批准签发）曾均hard_gate=False，独立60组两项真RED与作者先发现一致。修后实际两行hard_gate=True，注入对应技术guard FAIL使真实聚合器NO_GO；最新64组同probe GREEN。技术状态注入不是宣称已发生现实错位/真实签发。
4. **P2：部分执行的原生证据已关闭。** 自有隔离pytest root三参数[0,1,2]仅参数0真实PASS后，KeyboardInterrupt exit2产生原生无classname/name空testcase，旧解析KeyError。首修后真实pytest.exit(1)及根请求pytest.exit(0)均曾把未跑两参数整函数标PASS；另真实模块导入ERROR缺classname曾漏计errors1为0。作者新增固定server pytest插件，保存真实收集精确nodeids及hash，逐节点参数集合必须与具名JUnit完全相等才能PASS；空元数据不加PASS，实际error/failure仍保留真实计数。最新64组四个原生异常同probe全部GREEN，最终batch316精确收集=316JUnit再次GREEN。普通assert exit1仍可让其它已充分完成节点PASS；不拿简单全批非0禁PASS掩盖缺陷。

DOCX hash验证后ZipFile读取同一BytesIO(raw)的实际40材料spy GREEN；作者在本独审执行前已改为BytesIO，未捕获旧ZipFile(path)功能RED，不能编造RED→GREEN。family/framework/危险ZIP额外测试由独立材料审阅者负责，其数量不冒充本报告自测。

## 当前封证与限制

`.audit-local/t11-api-review/review-freeze.json` 冻结最新64/37目标与最终316批次的当前输入、原件/DB/JSON/JUnit/collection及本报告；旧原日志/JSON与历史before哈希保留，不把历史快照当current-source PASS。复算作者最新644输入封证与自有共同输入必须0差异，详见本地seal实际数量。

有效suite正式CLI、最终全量、普通浏览器、Word验收归根节点；本审阅者均不声称完成。全局网络抓包NOT_RUN；局部应用/ledger/provider证据不是整机零外联证明。本独审实际仅固定本机虚构、批准的localhost SDK协议与mock流程，无外部供应商、账户、付费或真实材料发送。真实规则/律师gold/地区/模型/预算/许可/试点批准缺失继续明确BLOCKED。
