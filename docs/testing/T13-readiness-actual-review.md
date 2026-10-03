# T13 独立就绪门实际审阅

2026-10-03 UTC。独立审阅范围为 `restricted_engineering`；真实证据信任根与完整法律硬失败聚合仍为 `NOT_IMPLEMENTED`，生产与真实试点保持 `BLOCKED`。本记录新增于此前只读准备报告之后，不修改准备封证、T10–T12 封证或已执行历史。

## 当前实际结果与分母

最新作者 v2 的 622 项输入封证为 `.audit-local/t13-author-final-v2/business.freeze.json`，SHA256 `7e878014d0f6f66cc68f7a936e3af574da755a1d444d7585e1fc3f868eac3b66`。本角色最终包装命令执行前后分别重算全部 622 项，均为 0 漂移。

| 独立真实命令 | 实际结果 | 耗时 | 输入核对 |
| --- | --- | --- | --- |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t13-readiness-review/actual-probes.py --label f1` | exit 0，40 PASS / 0 FAIL | 35.782 秒 | 499 项，前后 0 漂移 |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t13-readiness-review/lexical-probes.py --label f1` | exit 0，3 PASS / 0 FAIL | 3.921 秒 | 9 项，前后 0 漂移 |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t13-readiness-review/final-run.py` | exit 0，总计 43 PASS / 0 FAIL | 41.546 秒 | 作者 622 项前后 0 漂移 |

40 项包括原 37 项同入口复验，加上固定后台来源/config 哈希、既有生产门实际计数、无事故且预算撤销的对照三项。另 3 项专测 UNC、ADS、URL 在文件系统动作之前被拒绝。包装命令结果为 `.audit-local/t13-readiness-review/final-result.json`；40 项原始结果 SHA256 `acae0582e19e18b0b8563041c32de447f5351b02f865de86eaf7fcf102648e7e`，词法 3 项原始结果 SHA256 `9d36f3f060bf35a94a56fcc93973d14d071c00498c0e2dec5a7e27a0c475fec0`。

`actual-f1/result.json` 内部保留通用 helper 的 `NOT_FINAL` 标签；最终包装结果以当前作者 v2 输入、命令退出、逐项原始结果及独立 final seal 关联确定本次审阅时点，未回写 helper 的历史标签。

## 验证出的受限行为

- 缺少六组来源、任意 UUID、重复 UUID、任意 JSON 的 PASS/FAIL、空 gold、同一人充当两名评审、虚构数据自称真实、旧 hash/scope/时间、伪影子成本/分钟、调用方 OS/TLS/地域布尔值，均不能产生 GO。此结论是拒绝未经登记的输入，不能证明真实批准、双人 gold 或地域证据验证已经实现。
- 受控文件只产生逐类别/序号的当前字节哈希诊断，状态明确为未登记、未批准、适用范围未知。输出不回显原始路径或正文；`.py` 输入仅作为数据，独立执行标记未产生。变更文件字节会改变诊断哈希，仍不能获得批准效力。
- 自有硬链接、符号链接、越界路径、空字符和危险 URL 被拒绝，不生成调用方证据哈希。UNC/ADS/URL 三项使用文件系统哨兵；对应 `resolve/stat/open`、调用方 `checked_file` 和调用方哈希数量全部为 0，未探测真实远程文件系统。
- 六个非空引用直接构造 GO 的 DTO 会受控拒绝。`real_provider_requests` 为 0，真实信任根缺失始终阻断。
- 固定后台配置实际调用既有发布门，未把调用方六组文件当作已批准组。独立读取的 `server/source_lock` 为 `ab9acd4bb9e65f3007a927d1887378df570c926d8c1e073a30a371be7f6b1cce`，`server/config` 为 `16dfd5c861b7269c49cf5e279a761334e580b4666ece9c80ab0ea3fa151affc1`。实际门计数为 source 9、runtime 59、total 77；total 含其他既有阻断项，不能解释为 77 项能力通过。
- 自有虚构数据库通过既有 T08 后台完成一次模拟 dispatch 与结算：预留 15、实际费用 25、剩余 -5（单位均为 `synthetic_credit`），生成不可覆盖的后台费用事故。当前案件授权后，实际事故产生 NO_GO；调用方 PASS 不能覆盖。撤销预算批准后事故引用/hash 保留，仍为 NO_GO。独立无事故世界撤销预算后为 BLOCKED，未把缺信任泛化为已确认事故。

最后一项是真实执行的工程负向证据；请求由内存模拟 transport 提供。它证明当前受保护账本事故保守否决的闭合，不证明所有法律、模型、许可或部署硬失败来源都已接入。

## 保留的失败与源码时点

| 历史 | 实际结果 | 正确解释 |
| --- | --- | --- |
| 初次 helper label 1 | exit 1，IndentationError，业务导入/探针均为 0 | 自有辅助脚本括号错误，保留失败脚本与 `auxiliary-command-history.json`，不算业务 RED |
| `actual-2/result.json` | exit 1，36 PASS / 1 FAIL，2.016 秒，80 项输入 0 漂移 | 独立实证 P2：费用事故已存在，但预算批准撤销后 readiness 变为 BLOCKED，错误遮蔽 NO_GO |
| `actual-3/result.json` | exit 0，40 PASS / 0 FAIL，28.546 秒，499 项输入 0 漂移 | 修复事故读取次序、加入固定后台门后的旧源码 GREEN；早于 gateway handoff 修复 |
| `lexical-1/result.json` | exit 0，3 PASS / 0 FAIL，3.422 秒，9 项输入 0 漂移 | 旧时点词法证据，最终同 3 项另执行于 f1 |
| 最新 `actual-f1` + `lexical-f1` | exit 0，40+3 PASS | 当前作者 v2 源码的独立最终复验 |
| 最终结果摘要读取 | exit 1，KeyError；随后修正读取 exit 0 | 只读摘要把作者字典误当列表，不执行业务、不影响已完成 43 项，新增 `postrun-auxiliary-read.json` 保留事实 |

独立 P2 的同一探针 `hard-incident-still-NO_GO-when-budget-missing` 在最新 f1 实际通过。调用方诊断输出后来加入 `server/*` 固定来源命名空间，独立 oracle 区分调用方六组与服务器两组；路径回显 oracle 使用已解码叶字符串，保留旧 helper。两者是自有判据改进，不制造额外业务失败计数。

作者/根节点另实证了单页批准计划在交接前被合法新版双页计划替换的 handoff 问题，并增加后台 `expected_plan_sha256` 交接门。这是作者/根节点的 RED，未计为本角色独立 RED。其 gateway 源码变更使旧 40 项不能自动代表新源码，因此本角色再次执行最终 40+3，实际消费新 gateway，记录当前 hash。

## 明确未完成与未运行

真实保护登记、批准角色与有效期闭包、真实法律 gold、四类准确率/召回率、当前 84 项能力生产验收、模型账户/官方 schema/价格账单适配、真实影子成本与律师分钟、国内主机/OS 隔离/TLS/密钥托管/数据政策、完整法律硬失败聚合，均未由本独审实现或验证为 PASS。真实许可/律师批准与实际 gold 仍缺，法律分数为 null；模拟结果不能授权真实请求或生产 GO。

历史 96 引用观察只记录同一小文件在六组共 96 次检查/96 个哈希、0.813 秒、BLOCKED。没有已批准的总引用预算，资源上限状态为 `NOT_ESTABLISHED`，该观察不算 PASS/P2，本次最终未重复资源循环。

本角色未运行全量 suite、当前 84 CLI、T11 样本、浏览器、Word、真实外查、账户/密钥搜索、安装、OS 配置、Vault 或 Git 操作；未生成真实 key，未改业务/正式 tests/config/status。根节点的全量、CLI、实际批准及提交证据按独立范围记录，不并入本 43 项分母。

最终封证仅新增 `.audit-local/t13-readiness-review/final-seal.json`，逐项记录当前输入与自有证据。旧准备 seal SHA256 `47a729cf721e8a830ee9576237a1288540e5be7a6e3ca708b526bb2afd6205b5` 与既有 T10–T12 封证保持原始字节；准备的旧源码 hash 不被冒称为当前源码未变化。
