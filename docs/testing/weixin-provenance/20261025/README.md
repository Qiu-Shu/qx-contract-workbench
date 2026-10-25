# D2g5b 消息代际来源与存档完整性（2026-10-25）

基线`9c04b4d40a51435106d774d71afa46934917e0cc`，当前分支`codex/contract-review-v2`。本片仅持久来源结构和历史存档校验；运行接收/分发仍暂停。所有样本独立虚构，SQL seed不代表公开接收入口可用。

## 源码已实现

- schema18 `weixin-target-provenance-v1`只追加7字段不可变`weixin_descriptor_generations`；DTO集中domain.py。34个前驱native/non-native结构冻结，既有32个条目逐项不改。
- accepted original非零代消息按poll的完整账号checkpoint前缀和UTC因果位置选择当时最新generation，固定目标binding、scope和payload摘要；零代保持原mapping/grant语义。缺失/额外/blocked/duplicate/零代sidecar及已知accepted跨代reply均拒绝，source event全局namespace不加generation后缀。
- 公共来源校验也核完整父链；独审实际重算摘要反例曾仅被备份门拒绝，已补公共校验并用有/无sidecar两项永久回归证明。
- v18允许合法后代poll前缀；冻结v17继续拒绝后代poll。后代grant/dispatch仍拒绝；旧family gates完整接入18。accounts/ingress/dispatch运行源码与基线逐字节一致。
- 原生备份接入来源校验；普通cnbak不可携入非空来源。恢复继续隔离，不新增权限位、不恢复运行。

## 本轮实际验证

根最终9个短组，33模块**1094个不同Python**，1093 PASS、1 FAIL、0 errors/skip；142个新增全部PASS。唯一失败为下述基线长路径开放项；不是历史累计或全仓一次运行。15脚本233 Node通过，schema/defaults/sources/dependencies四开发门exit0。命令、退出码、JUnit及各组前后散列见[结构摘要](verification-summary.json)。

| 组 | 不同用例 | 退出码 | 失败/错误/跳过 |
|---|---:|---:|---:|
| final-schema | 208 | 0 | 0/0/0 |
| final-provenance | 41 | 0 | 0/0/0 |
| final-generations | 83 | 0 | 0/0/0 |
| final-inbox | 226 | 0 | 0/0/0 |
| final-services | 101 | 0 | 0/0/0 |
| final-head-preview | 126 | 0 | 0/0/0 |
| final-attachments-model | 133 | 1 | 1/0/0 |
| final-judge-library | 78 | 0 | 0/0/0 |
| final-task | 98 | 0 | 0/0/0 |

真实qxbak双往返保留消息来源及独立合成DOCX原件，旧源目录字节不变；恢复后session重新登录，所有既有enable/egress/approval位false，接收/分发/refresh/追加四写路径均BLOCKED_LIVE，无任务执行。认证但重算过去/未来归属的qxbak和带来源的普通cnbak不发布恢复目录。真实16→17→18工作区升级逐份核两份backup/receipt，旧17和新18各自中断恢复及损坏回执测试保留。

同一独立审查者分别做Spec/Standards两轴，本片源码0遗留，明确保留范围外基线阻断；不是两名独立代理。独立105项是跨纠正运行去重，已纳入根最终回归，不重复相加。[独审](independent-review.json)、[冻结摘要](review.md)。

## 实际失败与纠正

- 主初始RED：34 FAIL、0 errors，缺DTO/module；随后34 PASS。
- 独立schema初始99：36 PASS/63 FAIL、0 errors。首GREEN尝试93 PASS/6 FAIL为合成密码超过既有长度，改fixture后6 PASS；根最终完整复验99。
- 独立父链探针exit1：完整备份正确拒绝，公共校验漏查；补完整父链后两项永久回归均通过。[原反例](independent-parent-red.log)。
- 独立新增6首次4 PASS/2 FAIL：完整备份提前在inbox正确拒绝，测试错误码预期过窄；分开精确验证公共来源/完整备份错误，最终同次6 PASS。
- 首旧回归193：152 PASS/35 FAIL/6 setup errors。34项和6夹具为tip/多余新表预期；另1项后代空poll在v18应允许，改为明确冻结v17反例并加v18正例，未放宽运行guard。
- revised226：220 PASS/6 FAIL；新增空poll夹具字段误写cursor（实际upstream_cursor），精确复跑1 PASS；其余5为分步升级回执取错版本。首次最终schema207同样202 PASS/5 FAIL，保留schema-tip-first日志。
- 首服务组100：98 PASS/2 FAIL，旧pre-inbox夹具漏删新增来源表而不能识别为目标版本。仅修夹具并精确断言13/16，另加冻结17的public append/find成功且无自动升级；最终完整101服务用例复验。
- 纠正后旧native测试明确限定16→17历史边界，新增schema测试验17→18，另加无patch的真实16→17→18两步升级。所有实际原始失败记录保留，未因测试报错放宽产品保护。

## 当前回归1项FAIL与基线反证

旧长路径用例在第二次备份的SQLite只读打开临时快照时报unable to open database file；当前133项为132 PASS/1 FAIL，不改称全绿。独立新进程载入9c04b4d冻结234源码，144个实际导入产品模块全部来自基线；旧测试与备份模块字节相同、basetemp同长87字符，同一单例同阶段1 FAIL。冻结函数去掉扩展路径前缀后实际数据库应用路径263字符、文件存在，之前6次验证成功；[独立归因](baseline-attribution.json)、[原始元数据与源码散列](baseline-long-path.json)、[基线日志](baseline-long-path.log)。基线重复单例不累计为本轮第二失败。首次baseline harness缺仓库根导致导入错误exit4，也保留日志。此SQLite URI长路径问题OPEN，与已有WinError5发布目录失败及原生崩溃分别记录；本片未改其产品代码，不能称生产验收完成。

## 尚未实现 / NOT_RUN

按代际实际接收的descriptor/sidecar/checkpoint原子提交和分发待下一片；本片不提供相应写API。可信微信身份、账户资格、真实transport、E有限期模型授权仍待。WorkBuddy本轮NOT_RUN，未重试先前Bash被拒任务。全仓单进程、浏览器、安装版Electron0.4.1、真实微信/合同/产品模型/付费调用/签发/外发/新安装包均NOT_RUN。原生长进程崩溃与WIN-PATH-02保持OPEN，未自然复现也未标修复。

已有A—C和D2a—D2g5a证据仍在[任务状态](../../../TASK_STATUS.md)；本片结果不能代替生产或法律试点验收。

验证SHA256对应实际Windows工作区；单个JSON fixture经Git既有规则转LF，JSON与34前驱内容相同，其余授权文件暂存字节与工作区相同，见[换行核验](git-normalization.json)。
