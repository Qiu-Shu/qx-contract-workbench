# TODO — 群兴法律工作台协作清单

2026-10-26 D2g5g待收件列表服务与HTTP完成：198项不同Python、4项独立探针及四开发门通过，Spec目标归属P2已修复并复验，双轴0遗留。[实测](docs/testing/weixin-pending-list/20261026/README.md)。原未提交待收件服务/DTO已纳入本片；后续待UI列表入口、可信微信身份与下载解密、E模型有限期许可。WIN-PATH-02/原生AV、安装版0.4.1及真实账号验收状态不变；用户AGENTS改动保留。提交推送以[同步回执](docs/testing/weixin-pending-list/20261026/github-sync.md)为准。

`dhb_law`合并与同步已完成，源码`042b9d3`远端SHA/树一致，原待收件WIP恢复后57项补验通过；[回执](docs/testing/dhb-law-integration/20261026/github-sync.md)。下一步继续D2g5g HTTP接线，不重做本轮合并或已通过的夹具修复。

2026-10-26 `dhb_law` 集成修复已验证：历史升级夹具、精确迁移差集和UTF-8测试修复，572不同Python/388前端/369桌面逻辑及四门通过；[本轮记录](docs/testing/dhb-law-integration/20261026/README.md)。此前“缺依赖清单”为错误归因：清单存在，隔离副本缺本机缓存，复用已核缓存后通过。D2g5g待收件WIP保留未提交且HTTP仍待接线；WIN-PATH-02/原生崩溃、安装及真实微信模型仍待。合并/远端状态以同步回执为准。

2026-10-26 待补材料与跟进清单首片在 `dhb_law` 本地实现：每项关联固定事实/材料版本，记录原因/影响/下一步/期限/状态/结果；来源变化显示重核、已处理回待办而明确取消不复活，重开干净清单读新提醒；旧记录/未知回执/跨绑定草稿保护保留。23后端专项、70schema专项、444关联/342兼容Python、40前端专项/388关联、369桌面通过（重叠）；独立HTTP8/Node6及真实合成浏览器/qxbak通过，旧40结构不变。扩展历史526通过/8失败/6错误，与基线相同14项异常已复现仍OPEN；运行依赖门仍缺清单。本片源码与提交前记录随当前提交交接，服务器/安装版未更新。[实测](docs/testing/followup-worksheet/20261026/README.md)。

2026-10-26 材料目录与事实证据底稿首片已在 `dhb_law` 本地实现：顶部“事实与材料”按原话/解析锚点/人工摘录登记事实，日期/核对/相反说法分别保存，更正与移出保留历史，来源变动提示重核，未知只查回执。新增独立不可变表与assistant-evidence-v1，旧38份结构指纹保留；59专项/349关联Python、250兼容、348前端、369桌面通过（组间重叠），真实合成浏览器、原位升级/qxbak及独立复核通过。运行依赖清单仍缺失；本片源码和提交前验证记录随当前提交交接，安装版或服务器未更新，待补任务/争点/对练仍后续。[实测](docs/testing/evidence-worksheet/20261026/README.md)。

2026-10-26 “接待追问与事项底稿”首片在 `dhb_law` 实现：对话页“接待底稿”保存原始陈述、五项内部提纲、追问/材料和独立客户回复；本地候选带理由/原话，准备AI任务沿原发送入口且不自动调用。连续保存人工值保留、完整意图晚结果隔离、断ACK查回执及恢复只读已验。专项17/关联235 Python、专项15/关联336前端、369桌面通过；实际Chromium、客户Word包/渲染、真实qxbak及独立复核通过。运行依赖门仍因清单缺失退出1，未提交/推送/更新服务器或0.4.1，真实外部模型、Windows及法律验收未覆盖。[本轮实测](docs/testing/reception-worksheet/20261026/README.md)。

2026-10-25 D2g5f已接待收件附件明确选择本对话已上传DOCX/PDF，沿原resolution保存、原收件不覆盖，丢ACK只GET；材料旧通知回退缺陷经独立RED→GREEN修复。根4短组237不同Python：236PASS/1既有WIN-PATH-02 FAIL（含22新），293Node（60新）/四门/真实本机合成浏览器通过，交叉独审0遗留，[实际证据](docs/testing/weixin-media-selection/20261025/README.md)。可信微信/下载解密/pending列表/E许可待，0.4.1未更新，全仓长进程/安装版/真实账号模型等NOT_RUN，WIN-PATH-02和原生AV仍OPEN。产品`958b8e6`已正常推送，远端SHA/tree及5,761条目一致，[同步回执](docs/testing/weixin-media-selection/20261025/github-sync.md)。

2026-10-25 D2g5e已接根CID固定descriptor明确分发/精确找回HTTP：最终事务核root归属，固定目标当前ACL、9字段脱敏回执、精确恢复GET与丢ACK只查；旧guard/schema19保留。7短组23模块701不同Python（含64新）/四门通过，整体独审0确认及5独立HTTP探针通过；[实际证据](docs/testing/weixin-dispatch-http/20261025/README.md)保留首次不稳定61/3、夹具修正及64整组重跑、未用HTTP测试模块的摘要差异。无新UI/列表/真实微信；可信绑定、下载解密、pending附件选择/E许可仍待。0.4.1未更新，全仓/Node/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV仍OPEN。产品`dd46b6a`已正常推送，远端SHA/tree及5,688条目一致，[同步回执](docs/testing/weixin-dispatch-http/20261025/github-sync.md)。

2026-10-25 D2g5d已实施v19固定历史代际合成分发：复用receipt/TaskInbox/TaskDraft、逐固定binding顺序/当前ACL及完整父链，旧pending不阻新代，恢复只查。13关联短组1329不同Python（含100新）/四门通过，交叉独审0遗留，额外精确v18拒绝升级探针PASS；[实际证据](docs/testing/weixin-generation-dispatch/20261025/README.md)明确5项旧fixture/oracle失败及受影响组完整重跑、两文件test-body快照例外。36前驱指纹不变，真实可信微信/下载解密/外发/E许可待；0.4.1未更新，全仓/Node/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV开放。产品`2a4cca8`已正常推送，远端SHA/tree及5,630条目一致，[同步回执](docs/testing/weixin-generation-dispatch/20261025/github-sync.md)。

2026-10-25 已补齐原生升级前历史语义校验：只读复用现有完整来源校验，在升级写入前和DDL写锁内按原版本核验，pending恢复同时核旧备份与current；真实v17→v18非法poll洗白反例已RED→GREEN。15模块427不同Python（含9新）/四开发门通过，两名独立审查0遗留及2独立快照/释放探针通过，[实际证据](docs/testing/upgrade-preflight/20261025/README.md)。schema18/旧guard保留，v19代际分发为下一片；真实微信/模型关闭，0.4.1未更新，全仓/Node/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV开放。产品`619c898`已正常推送，SHA/tree及5,538条目一致，[同步回执](docs/testing/upgrade-preflight/20261025/github-sync.md)。

D2g5c产品`71802a6`已正常同步GitHub，远端SHA/tree及5,496条目一致；[同步回执](docs/testing/weixin-generation-ingress/20261025/github-sync.md)。

2026-10-25 D2g5c专用schema18合成代际收件已实施：原逐条去重/回执/游标CAS与固定目标sidecar原子提交，正反跨代reply整批回滚，丢ACK按固定目标权限只查；恢复继续只读。34模块886不同关联Python全部PASS（含52新增，非历史累计），233Node/四开发门通过，两名独立代理分别Spec/Standards0遗留，[实际证据](docs/testing/weixin-generation-ingress/20261025/README.md)。旧收件/绑定刷新/实际分发guard保持；下一片按代际分发及版本化来源校验，可信微信/E许可仍待。无新HTTP/UI/真实微信模型；0.4.1未更新，全仓/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV开放。

SQLite路径修复产品`7f27f4b`已正常同步GitHub，远端SHA/tree及5,444条目一致；[同步回执](docs/testing/long-sqlite/20261025/github-sync.md)。

2026-10-25 已修复SQLite精确只读路径与长路径恢复后再次备份：共享8处URI入口、局部快照DBAPI文件名，保留原件/引用/权限/结构守卫。新25已含于20模块289不同Python全部PASS，233 Node/四开发门通过；旧升级夹具漏表先基线复现再单处修正，58独立/88根回归通过。同一独立审查者双轴0遗留，[实际证据](docs/testing/long-sqlite/20261025/README.md)。原A—C和D离线底座保留；按代际实际收件分发/可信微信/E许可仍待。0.4.1未更新，全仓/浏览器/安装版/真实微信模型等NOT_RUN，原生崩溃及WIN-PATH-02保持OPEN。GitHub按后附实际回执核对。

D2g5b 产品 `0738989` 已正常同步GitHub，远端SHA/tree及5,385条目一致；[同步回执](docs/testing/weixin-provenance/20261025/github-sync.md)。

2026-10-25 D2g5b 已完成消息代际来源存档：schema18追加7字段不可变来源，按完整poll前缀和UTC固定历史目标；34前驱冻结、公共完整父链及两代真实qxbak/原件/恢复隔离已验。根33模块1094不同Python：1093PASS/1基线长路径FAIL（142新增全PASS），233 Node和四开发门通过，独审同人双轴本片0遗留、范围外故障OPEN；[实测](docs/testing/weixin-provenance/20261025/README.md)。旧收件/分发guard仍暂停，下一片实际按代际接收/分发及可信微信/E许可；0.4.1未更新，全仓/浏览器/安装版/真实微信模型等NOT_RUN，原生崩溃/WIN-PATH-02保持OPEN。

D2g5a 产品 `6c0b26a` 已正常同步GitHub，远端SHA/tree及5,297条目一致；[同步回执](docs/testing/weixin-generation-preview/20261025/github-sync.md)。

2026-10-25 D2g5a 已完成按持久代际的合成离线预览：同一事务核当前身份/root/latest权限、完整head/scope及当前两类cursor，预览不推进游标或写业务；安全拒绝保留原审计。根14模块361不同Python（50新＋135协议＋100服务＋76head/guard）、233 Node及四门通过，独立7例含真实锁竞争和权限审计；真实qxbak核旧session401/重新登录409，[实测](docs/testing/weixin-generation-preview/20261025/README.md)。旧收件/分发guard仍暂停；下一片持久消息代际来源/完整性与实际合成接收分发，可信微信/E许可仍待。0.4.1未更新，浏览器/全仓/安装版/真实微信模型等NOT_RUN，原生崩溃/WIN-PATH-02保持OPEN。

D2g4 产品 `b3f204d` 已正常同步GitHub，远端SHA/tree及5,244条目一致；[同步回执](docs/testing/weixin-generation-ui/20261025/github-sync.md)。

2026-10-25 D2g4 已将明确目标历史登记接入原对话页：预览零写、缺绑定才在明确保存时创建、两阶段丢回执只查、版本变化/迟到响应/撤权及导航守卫已验；真实qxbak恢复继续只读。根12模块229不同Python、15脚本233 Node、两组本机浏览器、四开发门均通过；同一独立审查者Spec/Standards两轴0遗留（非两名代理），[实测](docs/testing/weixin-generation-ui/20261025/README.md)。D2g3欠缺的独立Standards已在本轮补完0确认违规，旧阶段记录保留。当前账号仍暂停，按代际接收/分发、可信微信及E许可待接；安装版0.4.1未更新，全仓/安装版/真实微信模型等NOT_RUN，原生崩溃和WIN-PATH-02保持OPEN。

D2g3 产品 `d6627de` 已正常同步GitHub，远端SHA/tree及5,197条目一致；[同步回执](docs/testing/weixin-generation-head/20261025/github-sync.md)。

最新接续（2026-10-25，D2g3）：七字段history_only head、根CID精确GET和同事务root/latest ACL/历史/checkpoint已接，HTTP head→两代POST、旧CAS、真实锁竞争、坏历史/schema、恢复和零写均实测；298不同Python、192 Node及四门通过，独立Spec复核完成，[证据](docs/testing/weixin-generation-head/20261025/README.md)。下一片明确桌面操作，再接按代际接收分发；当前仍暂停。宿主thread limit和WorkBuddy Bash拒绝使独立Standards未完成，不称双独立审查；可信微信/E许可、0.4.1、原生崩溃/WIN-PATH-02状态不变。

D2g2 产品 `00f17bb` 已正常同步GitHub，远端SHA/tree及5,152条目一致；[同步回执](docs/testing/weixin-generation-http/20261025/github-sync.md)。

最新接续（2026-10-25，D2g2）：根CID受保护的代际POST/固定GET及11字段history_only回执已接，解析前后权限/CSRF/同源、二代/幂等/CAS、恢复/历史ACL与丢ACK只查询已验；241不同Python、192 Node、四门及独立双轴审阅通过，[实测](docs/testing/weixin-generation-http/20261025/README.md)。下一片最新CAS head/明确桌面操作与按代际接收分发；当前账号继续暂停，不称运行切换。可信微信身份/资格与E限期许可待办；0.4.1、原生崩溃和WIN-PATH-02保持开放，浏览器UI/真实微信/模型NOT_RUN。

恢复诊断工具提交 `9c2acd2` 已正常同步GitHub，远端SHA/tree与5,117条目一致；[同步回执](docs/testing/restore-publication/20261025/github-sync.md)。

最新接续（2026-10-25，恢复诊断）：开发观察器与默认scanner实际校准完成，根70不同Python、默认/诊断浏览器和四门通过，[证据](docs/testing/restore-publication/20261025/README.md)。原WinError5未自然复现，未猜测修补，WIN-PATH-02/原生崩溃保持OPEN；下一步用显式诊断捕获实际失败，继续D2g按代际接收/分发与明确HTTP/桌面操作，真实微信/模型保持关闭。

D2g1 产品 `40be816` 已同步 GitHub，远端SHA/tree及5,082条目一致；[同步回执](docs/testing/weixin-generation-service/20261025/github-sync.md)。

最新接续（2026-10-25，D2g1）：八字段输入、当前root/前代/新目标权限、完整scope与gen/hash/checkpoint CAS、原子追加/固定查询及真实故障/丢ACK/竞争/新进程/两代恢复已验；310不同Python、192 Node和四门通过，[证据](docs/testing/weixin-generation-service/20261025/README.md)。下一片按代际恢复接收/分发与明确HTTP/桌面操作；当前仍暂停收件，不称可运行切换。可信微信身份/资格与E限期许可仍待，0.4.1、原生崩溃及上轮WIN-PATH-02失败开放，本片浏览器NOT_RUN。

D2f 产品 `6e36cb5` 已同步 GitHub，远端 SHA、tree 及5,073个受控条目一致；[同步回执](docs/testing/weixin-generations/20261024/github-sync.md)。

最新接续（2026-10-24 UTC，D2f）：跨对话generation的14字段不可变存储/升级/历史校验/两代qxbak及账号级暂停已实现，32前驱指纹不变；814不同Python、192 Node与四开发检查通过，[实测](docs/testing/weixin-generations/20261024/README.md)。独立发现未来目标revision漏洞已RED→GREEN。下一片D2g：显式追加/切换服务、当前桌面权限/CAS/未知结果恢复，再接页面和按代际收件；当前无公开追加服务，不称可转案。额外浏览器回归在恢复目录rename复现WinError5，该组FAIL，WIN-PATH-02仍开放；原生崩溃、真实微信/模型、E限期许可和安装版状态不变。

D2e 产品 `a42c415` 已同步 GitHub，远端 SHA、tree 及 5,061 个受控条目一致；[同步回执](docs/testing/weixin-desktop/20261024/github-sync.md)。

最新接续（2026-10-24，D2e）：现有任务卡的本机收件授权投影/显式refresh/未知结果查询已接，当前CID/CSRF/同源/权限及真实recovery精确两GET入口已验；255不同Python、192 Node及三组浏览器通过、四门exit0。[实测](docs/testing/weixin-desktop/20261024/README.md)。跨目标/转案generation及可信远端身份仍待；真实微信/模型、新安装包、原生崩溃与WIN-PATH-02状态不变。

D2d 产品 `ba03b02` 已同步 GitHub，远端 SHA、tree 及 5,051 个受控条目一致；[同步回执](docs/testing/weixin-reauthorization/20261024/github-sync.md)。

最新接续（2026-10-24，D2d）：同目标input/material scope显式refresh、不可变grant链、CAS/未知结果找回及历史生效边界已实现；925不同Python用例最终通过、四门exit0，[实测](docs/testing/weixin-reauthorization/20261024/README.md)。独立发现UTC表示排序反例已RED→GREEN并重跑受影响链路。下一片跨目标/转案generation及可信transport入口；E有限期模型许可仍待。真实微信/模型、新安装包及原生崩溃/WIN-PATH-02状态不变。

D2c 产品 `64a435e` 已同步 GitHub，远端 SHA、tree 及 5,040 个受控条目一致；[同步回执](docs/testing/weixin-dispatch/20261024/github-sync.md)。

最新接续（2026-10-24，D2c）：合成accepted描述至共享TaskInbox/TaskDraft的受控分发及不可变回执已实施；同事务/来源碰撞/顺序/当前权限/恢复、两种聚合顺序、歧义待分配、冻结补充、同UTC刻度因果时间均有证据，679不同关联Python用例最终通过、四开发门退出0。[实测](docs/testing/weixin-dispatch/20261024/README.md)。下一片：过期scope映射在当前桌面身份下的显式重新授权，保留历史、不隐式复活撤销映射；再接可信transport入口和E有限期合同模型许可。真实账号/模型、下载发送、新安装包仍关闭/NOT_RUN，原生崩溃和WIN-PATH-02开放。

D2b 产品 `f161660` 已同步 GitHub，远端 SHA、tree 及 5,029 个受控条目一致；[同步回执](docs/testing/weixin-ingress/20261024/github-sync.md)。

最新接续（2026-10-24，D2b）：合成账号/精确 peer 服务、原子完整收件/checkpoint CAS、固定回执幂等及未知结果查询恢复已实现；444 个不同关联 Python 用例最终通过、四开发门退出 0。[实测](docs/testing/weixin-ingress/20261024/README.md)。下一片 D2c：accepted_pending_dispatch 至共享 TaskDraft 的受控分发及持久回执/恢复，使用时再次核验当前身份、权限、版本与 fence；另须显式设计过期映射刷新，当前明确阻断。真实微信/模型、下载发送、E 有限期许可和安装包仍关闭/NOT_RUN，原生崩溃与 WIN-PATH-02 保持开放。

D2a 产品 `41874db` 已同步 GitHub，远端 SHA、tree 及 5,020 个受控条目一致；[同步回执](docs/testing/weixin-inbox/20261024/github-sync.md)。

最新接续（2026-10-24，D2a）：合成账号/精确 peer 映射/完整 poll 回执的存储底座、历史校验、前驱升级和 qxbak 恢复已完成；587 个不同关联 Python 用例最终通过、四开发门退出 0，[实际证据及原失败](docs/testing/weixin-inbox/20261024/README.md)。下一片 D2b：当前桌面 principal 下的合成账号/映射服务和原子 record_synthetic_poll，先完整持久化逐条结果，再 revision CAS 提交账号 opaque 游标；幂等回读、未知结果恢复、撤权及分类失败事务边界须真实验证。D2c 再分发到共享 TaskDraft。真实认证、网络、下载解密、发送/Outbox、E 有限期模型许可仍未实施/NOT_RUN，安装版 0.4.1、原生崩溃和 WIN-PATH-02 保持开放。

D1 产品 `8c7db52` 已同步 GitHub，本地/远端 SHA、tree 及 5,009 个受控条目一致；[D1 同步回执](docs/testing/weixin-offline/20261024/github-sync.md)。

最新接续（2026-10-24，D1）：官方微信离线预览完成，123 项协议单元＋12 项作用域集成及155项关联回归通过，合计290个不同用例；四开发检查通过，[D1 证据](docs/testing/weixin-offline/20261024/README.md)。下一片 D2：可信身份映射、账号级完整 Inbox/checkpoint 与撤权/恢复，先保证上游事件持久处理后才推进账号游标。真实账号、下载解密、发送/Outbox 和 E 模型仍关闭。本聊天持续开发 heartbeat 已开启，每30分钟接续可执行切片并在有完成变更时正常推送；HumanLayer五分钟轮询保持暂停，按轮收尾。

C 产品提交 `4b62f06` 已同步 GitHub，本地/远端 SHA、tree 及 5,002 个受控条目一致；[C 同步回执](docs/testing/task-pdf/20261024/github-sync.md)。

最新接续（2026-10-24，持久合同任务 A＋B）：Inbox/TaskDraft、合成 DOCX→案件→人工事实确认→Mock 结果、任务列表、迁移及恢复隔离已实施；最终实际命令和范围见 [本片证据](docs/testing/task-drafts/20261024/README.md)。C 合成 PDF 桥接现已完成，130 项关联 Python、170 项 Node、三组浏览器和原生 qxbak 恢复验证通过；[C 实测](docs/testing/task-pdf/20261024/README.md)。后续 D：官方微信适配与可信账号绑定；E：真实合同模型与原生限期授权。本片未连接真实微信或产品模型，未发布安装包。 功能关联382项以独立模块/短组方式通过；单进程原生访问冲突仍待专项复现，未更新安装版。

A＋B 产品提交 `0178859` 已同步 GitHub，远端 SHA、tree 及递归 4,992 个受控条目与本地一致；[同步回执](docs/testing/task-drafts/20261024/github-sync.md)。长进程崩溃已有匹配 Windows 事件及本机转储元数据，两个紧密合成探针未复现，后续优先符号化分析；[诊断记录](docs/testing/task-drafts/20261024/native-crash.md)。

2026-10-24：默认桌面连续文字上下文及CH-07C3b人工维护已接通，含一次真实虚构内容模型验证；安装版与Windows恢复开放项保持独立。[本次验证](docs/testing/conversation-maintenance/20261024/README.md)。

2026-10-22：RECEPTION-01 私有资料与法律服务接待融合已完成源码及服务器试运行验证；真实模型与完整专项模块仍按原排期。[证据](docs/testing/reception-plugin/20261022/README.md)。

CH-07C3a源码与合成证据 `1a03d89` 已同步GitHub，远端SHA及4,949项文件树一致；[同步回执](docs/testing/GITHUB-PROFILE-UI-20261023.md)。

2026-10-23 CH-07C3a已贯通桌面普通文字的统一发送、同次待核档案/接待保存及只读档案侧栏；既有请求和丢失回执只查询找回，不重复调用。保存状态依据真实回执，来源、版本、冲突及律师保护值可回查。相关Python去重265、桌面366、前端141及四门通过；Windows合成6组通过，恰好一次回环调用、档案与接待各保存一次，627份输入稳定。人工修改/联系方式、附件自动建档与导出仍待，安装版0.4.1和WIN-PATH-02状态未变。 [本片实测](docs/testing/profile-ui/20261023/README.md)。GitHub产品同步已核验，见上方回执。

CH-07C2d源码及合成证据 `2dd5392` 已同步GitHub，远端SHA与4,832项文件树一致；[同步回执](docs/testing/GITHUB-PROFILE-DESKTOP-20261023.md)。

2026-10-23 CH-07C2d完成可信桌面档案用途确认入口：复用原生窗口和私有管道，展示完整文字、本机保存目标及接待同步意图；保留authorized/existing区别，不把确认当成已保存。实机发现并修复既有聊天模块静态白名单遗漏。桌面366、前端68、相关Python19通过，四门通过；Windows原生5组、621份输入稳定，模型调用与业务记录均0。统一对话自动归档及档案侧栏仍待CH-07C3，安装版0.4.1和WIN-PATH-02开放状态不变。 [本片实测](docs/testing/profile-desktop/20261023/README.md)。GitHub产品同步已核验，见上方回执。

2026-10-23 CH-07C2c已完成档案用途的后端应用入口：预览重建当前草稿及保存计划，私有管道许可固定一次调用，HTTP登记与原任务队列复用；已登记请求只找回，许可失效后用GET读取，不重发。完整Python回归4,393项通过、0失败/错误/跳过，四开发门通过，558份输入稳定；独立Spec9项、Standards10项通过。实际本机子进程/管道/HTTP合成链验证恰好一次回环调用。桌面用途确认与档案侧栏待接，安装版0.4.1及WIN-PATH-02开放状态不变。 [本片实测](docs/testing/profile-application/20261023/README.md)。GitHub产品同步已核验，见下方回执。

2026-10-23 CH-07C2b2b-B完成内部档案执行与历史恢复闭合：复用单次调用账本和预算，同次回答、费用、待核档案/接待及固定保存回执原子提交；撤权弃候选保费用，恢复不重发。23文件首轮667/668通过，1项旧断言更正后原文件53项通过；产品源码未变，四开发门通过。原生许可窗口、HTTP/任务调度和档案面板仍待接入；安装版0.4.1及WIN-PATH-02开放状态不变。 [本片实测](docs/testing/profile-execution/20261023/README.md)。GitHub产品同步已核验，见下方回执。

2026-10-23 CH-07C2b2b-A完成档案用途许可内核：完整保存计划绑定许可，普通聊天/资料回答/档案用途互相隔离，发送前后检查到期、撤权及配置变化，晚到候选丢弃而保留已收到用量。一次13文件379项关联通过（新增文件58项已包含），四开发门通过，546份工作区输入稳定。只修改现有registry，应用自动归档仍关闭；持久调用消费、费用和原子保存/历史恢复继续接线。 [本片实测](docs/testing/profile-authorization/20261023/README.md)。GitHub产品同步已核验，见下方回执。

2026-10-23 CH-07C2b2a已完成可信数据库装配：读取实际消息、原请求摘要及档案/接待基线，拒绝跨会话、旧绑定和版本变化，同时隔离发送后新草稿；共用附件选择校验拒绝损坏快照。单次13文件源码回归393项通过（可信装配49项、附件解码22项已包含），四开发门通过、545份输入稳定，独立复核见证据。发送、费用与原子保存仍由C2b2b闭合，自动归档入口继续关闭；安装版0.4.1及WIN-PATH-02状态未变。 [实测](docs/testing/profile-trusted-preparation/20261023/README.md)。GitHub产品同步已核验，见下方回执。

CH-07C2c源码与合成证据 `63f48c6` 已同步，远端SHA及4,758文件树一致；[同步回执](docs/testing/GITHUB-PROFILE-APPLICATION-20261023.md)。

2026-10-23 CH-07C2b1：自动建档的存储前置切片完成。新命名schema及固定保存回执保留旧11版44摘要，三迁移通道与五族旧完整性校验接续；新格式/新回执仍fail-closed，未启用自动归档。20文件初轮630/632通过，2项旧测试预期修正后两个文件54通过；四开发门通过，542份输入稳定、产品源码未变，Spec6/Standards30独立通过。修复新摘要CHECK的NUL尾缀漏洞。安装版0.4.1和WIN-PATH-02开放项不变；未碰真实资料/模型/云。[证据](docs/testing/profile-model-schema/20261023/README.md)。

最新接续（2026-10-23，CH-07C2a）：离线发送内容/保存计划绑定完成；380关联、四开发门、Spec12/Standards9通过。C2b仍须闭合原生用途许可、版本化账本、固定原子钩子及迁移恢复，自动保存尚未启用；以[本片证据](docs/testing/profile-basis/20261023/README.md)为准。`a84a156`已正常同步，远端SHA及4,370文件树一致；[回执](docs/testing/GITHUB-PROFILE-BASIS-20261023.md)。

最新接续（2026-10-23，CH-07C1）：协议切片及577项关联验证完成，自动保存仍待C2/C3；以[本片证据](docs/testing/profile-output/20261023/README.md)为准。后续同步结果见下方回执。
已同步：CH-07C1协议源码与证据 `bcc5013`，远端SHA及4,331文件树一致；自动建档接线和Windows恢复开放项继续推进。[同步回执](docs/testing/GITHUB-PROFILE-OUTPUT-20261023.md)。

此前CH-07B阶段记录（2026-10-23）：CH-07B本地档案/接待原子保存、历史接口、迁移恢复已实现并独立复核。完整回归3816通过/3失败，两个旧测试夹具已修正、定向9/36通过；最终目录rename WinError5仍待定位，保留开放验收项，不称全套全绿。自动钩子与档案侧栏尚未接通；先核对本片诊断证据，再推进CH-07C。WorkBuddy本轮无活动端点未派发，安装版0.4.1不变。[本片证据](docs/testing/profile-persistence/20261023/README.md)。同步状态以独立回执为准。

更新：2026-10-22。对话页模型 UX 小片从 `8c609ac` 完成（所有者直接指令）：排查并修复"API 已配置但发送按钮灰色"（模型启用是进程内存态，重启即失效；capability 需已保存草稿触发）——①持久化所选模型并在后端就绪时自动用本机已存密钥恢复配置（取消每次手动"配置本次运行"，显式停用才清除，换密钥不清除，恢复副本永不自动配置，Jev 不参与）；②对话页「保存草稿」左侧新增「切换模型」按钮（Flash↔Pro 互切、仅对话页主 frame 可调的新 IPC 桥、切换后自动重算 capability）；③窗口焦点回来时自动重拉生成条件。每次发送的原生确认窗逐次核对不变。此前记录已核对模型名、参数与价格文档；这不构成真实供应商连通或端到端验收，CH-04真实冒烟仍待。安装版仍为0.4.1。此表用于协作排期；完成事实以 [TASK_STATUS](docs/TASK_STATUS.md) 与对应证据为准，完整验收条件以 [v2.1](docs/plans/chat-first-architecture-v2.1.md) 为准。

`[x]` 只表示写明范围的工程切片完成，不表示整个 CH 阶段、真实法律效果或生产完成。`[ ]` 表示仍有工作。未认领不代表可跳过依赖；协作者在自己的 PR 中写明任务 ID、改动范围和依赖，再更新本表的负责人/状态，避免重复实施。当前未指定具体协作者姓名。

## 当前及下一步

| 任务 ID | 优先级 / 状态 | 负责人 | 交付与验收边界 | 依赖 |
| --- | --- | --- | --- | --- |
| CH-05C | 已完成本机配置切片 | Codex | 独立凭据、日常配置/停用、能力声明和关闭双清理；190桌面/119关联Python通过，源码/冻结Windows各9组；未接发送许可 | [本片证据](docs/testing/jev-native/20261020/README.md) |
| CH-05D1 | 已完成后端接线切片 | Codex | 独立逐请求许可、单槽保护和同主任务可选辅助；201桌面与157/83/32分组后端检查、源码10组/冻结控制7组通过；未接日常发送确认UI | [本片证据](docs/testing/jev-request/20261020/README.md) |
| CH-05D2 | 已完成同窗独立确认切片 | Codex | 240桌面、4开发检查、源码默认关闭6组/双选8组/冻结授权停用5组；辅助不选仍继续主流程，末检查失败清理闭合许可；真实预算未配仍关闭 | [本片证据](docs/testing/jev-confirmation/20261020/README.md) |
| CH-00A-续 | P0 · 持续推进 | 待认领 | 结合下一功能继续收窄入口职责及既有接待依赖；保持旧路由/DTO/权限兼容，不为拆文件增加空壳 | 先确定模块和关联测试 |
| CH-00A3 | 已完成接待依赖切片 | Codex | 建案/记录编码下移应用层、旧Web别名兼容、接待Word按需导入；147关联、4开发门、双轴各4探针通过；模块与跟踪分配实测不等于整机/安装包收益 | [实测](docs/testing/intake-decoupling/20261023/README.md) |
| CH-00B-续 | P0 · 可并行测量 | 待认领 | 复用既有基线，报告同能力包体、可输入时间、空闲/峰值占用和退出清理；区分安装器/未压缩目录/进程数据，不反复重建不变产物 | [首片测量](docs/testing/chat-first/20261016/README.md) |
| CH-00B2 | 已完成检索内存切片 | Codex | 长文原文定位去掉整篇映射；同合成样本Python峰值约-87.7%、耗时中位数约+6–8%；183通过加2项DuckDB补验通过，同代码分两批覆盖185项，不是整机资源验收 | [本片实测](docs/testing/library-memory/20261020/README.md) |
| CH-03-续 | P1 · 部分完成 | 待认领 | 补齐当前 DOCX 之外经批准的附件范围、衍生脱敏版本和跨模块映射；无可靠映射不外发 | 现有建案前附件/来源接口 |
| CH-04-续 | P1 · 部分完成 | 待认领 | 补第二主供应商及更广材料范围；真实合成联网验证需实际账号、数据许可及费用条件，缺条件如实记录 | 现有普通文字链；官方协议重新核对 |
| CH-06A | 已完成内部法库底座 | Codex | 最多8条/1200字符精确引用及当前权限重核；341关联通过、2旧DuckDB跳过；没有HTTP/UI/模型入口 | [本片证据](docs/testing/library-adapter/20261020/README.md) |
| CH-06B1 | 已完成内部持久化切片 | Codex | 持久引用、固定回执、8次工具额度、当前授权及schema/升级/恢复同片；完整回归3222通过，0跳过；未接UI/多轮模型 | [本片证据](docs/testing/library-ledger/20261020/README.md) |
| CH-06B2a | 已完成本机检索与引用面板 | Codex | 一次关键词查询与历史原文片段；Python同输入分两批覆盖3271通过（首轮3233+原38项换盘补验），55顶层Node/8组源码浏览器通过；归档与旧记录误判已修，无真实模型/安装器验收 | [本片证据](docs/testing/library-chat/20261020/README.md) |
| CH-06B2b1 | 已完成本机预览接口 | Codex | 服务器重建选定历史片段和问题，完整JSON/UTF-8预算，超限保留；无新许可/账本/模型调用/选片UI；644关联Python、4开发门、Windows HTTP9组通过 | [本片证据](docs/testing/context-preview/20261020/README.md) |
| CH-06B2b2a | 已完成适配基础切片 | Codex | 独立上下文DTO/codec与共享传输；542关联、4开发门、双轴各6项通过；应用资料发送仍关闭，无新schema/账本 | [本片证据](docs/testing/context-provider/20261021/README.md) |
| CH-06B2b2 | 已完成资料发送闭合切片 | WorkBuddy | 新输入格式列、有序来源关联、原生一次许可（服务端重建核对、max_calls=1）、同 attempt 执行/撤销/费用、升级与备份恢复同片闭合；一次资料辅助回答经回环 HTTP 字节核验；旧V1字节和权限保持；选片GUI与真实供应商不在本片 | [本片证据](docs/testing/context-send/20261021/README.md) |
| CH-06B2c1 | 已完成轮次账本底座切片 | WorkBuddy | attempts 重建支持 round_no（1–4、UNIQUE(run_id,round_no)、不可变触发器纳入新列）；FK OFF 重建窗口在三条迁移通道同序语句保证字节一致；完整性 fail-closed 拒绝多轮归档；行为不变恒 round 1；无 runner 循环/协议/授权变更 | [本片证据](docs/testing/bounded-rounds/20261021/README.md)；[执行合同](docs/plans/2026-10-21-bounded-rounds.md) |
| CH-06B2c2 | 已完成受限串行循环切片 | WorkBuddy | `library-context-v2` 工具计划协议（≤4轮/≤8工具、DTO 层拒陌生 tool）；max_rounds 显式授权形状与 registry lease generate_rounds 分支；`assistant-rounds-v2` CHECK 加宽（12 步重建、v1 冻结摘要固化）；runner 主循环与 rounds_exhausted/budget_exhausted/tool_limit/tool_rejected 四停止；撤权走 claim-abandon 闭合、恢复封存 interrupted 不重发；完整性开放 v2 多轮全绑定；v1 字节与行为不变；真实供应商不在本片 | [本片证据](docs/testing/bounded-rounds/20261021/README.md)；[执行合同](docs/plans/2026-10-21-bounded-rounds.md) |
| CH-06B3 | 已完成律师选片 GUI 切片 | WorkBuddy | 选片面板（本会话已保存引用 1–8 条保序勾选、编辑/换对话/撤选即失效）；预览扩展 send_basis（request_id 惰性铸造、DTO 逐字段一致性校验）；桌面 `authorize_context` 新通道（桌面自行 CSRF POST 预览重建 basis、六键确认窗片段清单、单次 lease）；前端三向互斥与发送分派、NETWORK_UNKNOWN 只找回不重发；无 schema/依赖变更，v1 单轮锁定，真实供应商不在本片 | [本片证据](docs/testing/selection-gui/20261021/README.md)；[执行合同](docs/plans/2026-10-21-selection-gui.md) |
| UX-01 | 已完成对话页模型 UX 小片 | WorkBuddy | 排查修复"已配置但发送按钮灰色"（启用为进程内存态+capability 需已保存草稿）；所有者指令取消每次手动配置——所选模型持久化、后端就绪自动用已存密钥恢复（停用才清除、换密钥不清除、恢复副本不自动配、Jev 不参与）；对话页「保存草稿」左侧新增「切换模型」按钮（新 IPC 桥仅对话页主 frame 可调）；焦点回来自动重拉 capability；每次发送原生确认窗不变；桌面 270/270、前端 68/68、四开发门 exit 0 | [本片证据](docs/testing/model-ux/20261022/README.md)；[执行合同](docs/plans/2026-10-22-model-ux.md) |
| UX-02 | 已完成材料拖拽与多文件切片 | WorkBuddy | 所有者指令+GitHub 复用评估（Dropzone/FilePond/Uppy 无法对接回执协议与伪 DOM 夹具，不引入，复用交互模式）；后端格式扩为 DOCX/DOC/XLSX/PDF/PNG/JPG/CSV（mime 六值枚举+后缀映射+内容嗅探，xlsx 校验 ZIP 结构，csv 须 UTF-8，案件侧 _type 不变）；policy 放宽 v1 存量兼容+v2 新上传；parse 仍仅 DOCX；下载原件后缀按实际；前端多文件待传队列 chips（×单删+清空）、一次同意顺序上传（独立回执、i/N 进度、失败保留剩余、NETWORK_UNKNOWN 重试退役 inflight）、整页拖拽蒙层入队并前端预筛点名拒绝；非 DOCX 行显示格式标签、预览仅原件不出读取按钮；已上传原件不物理删除（账本引用约束，另立片）；Python 新增 5 项+关联 109 过/2 基线复现环境失败、前端 146/146、四门 exit 0、桌面零改动 | [本片证据](docs/testing/material-files/20261023/README.md)；[执行合同](docs/plans/2026-10-23-material-files.md) |
| WIN-PATH-01 | 已完成原件/qxbak源码切片 | Codex | 创建/读取/回滚统一I/O路径，逻辑引用不变；424关联、4开发门、16真实HTTP请求及双轴复核通过；原件父目录279→282字符。UNC/超长SQLite/任意长cnbak目标及新安装包未验 | [本片证据](docs/testing/contract-long-path/20261020/README.md)；CH-10仍需安装验收 |
| WIN-PATH-02 | P2 · 开放，发布阶段新现场 | Codex | 本轮全套首次长路径restore在最终目录rename报WinError5；孤立复跑通过，根因未定。与旧nlink/回收站shim错误不能混同，不猜测加重试或放宽守卫；保留前序复验及新顺序/句柄探针 | [本轮证据](docs/testing/profile-persistence/20261023/README.md) · [旧复验](docs/testing/intake-decoupling/20261023/README.md) |
| CH-07A | 已完成纯内核切片 | Codex | 来源/合并/人工保护/合法投影；400关联、4开发门、双轴6/9探针；无持久化或模型接线 | [本片证据](docs/testing/profile-merge/20261023/README.md) |
| CH-07B1 | 已完成来源前置切片 | Codex | 当前授权下有界重建真实存储来源；事务外核对原件后再次检查，存量损坏拒绝；186关联、4开发门、双轴7/8探针，无业务写入/模型接线 | [本片证据](docs/testing/profile-sources/20261023/README.md) |
| CH-07B | P1 · 后端已实现，整体验收未关闭 | Codex接续 | 原子档案/接待/回执、历史与人工接口、迁移恢复完成代码和定向验证；全套3816/3819，两个旧夹具修正后9/36通过，长路径发布WinError5根因未定。保留原失败，勿将补验算成一次全绿 | [执行合同](docs/plans/2026-10-23-profile-persistence.md) · [证据](docs/testing/profile-persistence/20261023/README.md) |
| CH-07C1 | 已完成协议切片 | Codex | 当前文字同次回答/提案、出处由服务器填充、撤权保留用量；577关联、4门、Spec13/Standards8+4通过；未启用应用自动建档 | [实测](docs/testing/profile-output/20261023/README.md) |
| CH-07C2a | 已完成离线准备切片 | Codex | 同wire不同保存计划使用不同basis摘要；实际saved views身份/版本桥接；380关联、4门、Spec12/Standards9；无运行许可或自动存档 | [合同](docs/plans/2026-10-23-profile-send-basis.md) · [证据](docs/testing/profile-basis/20261023/README.md) |
| CH-07C2b1 | 已完成存储前置切片 | Codex | 630/632初轮、旧断言修正后54补验/4门/Spec6/Standards30；旧签名与旧校验保留，新格式和handler记录仍禁止验收，自动归档未启用 | [合同](docs/plans/2026-10-23-profile-model-schema.md) · [证据](docs/testing/profile-model-schema/20261023/README.md) |
| CH-07C2b2a | 已完成内部核验 | Codex | 393关联/四门通过；实际消息与原请求摘要绑定，当前版本重建；发送和自动保存仍封闭 | [合同](docs/plans/2026-10-23-profile-trusted-preparation.md) · [证据](docs/testing/profile-trusted-preparation/20261023/README.md) |
| CH-07C2b2b-A | 已完成内部许可 | Codex | 379关联及四门通过；完整保存计划用途隔离、发送前后失效检查；持久claim/费用/保存未接通 | [合同](docs/plans/2026-10-23-profile-authorization.md) · [证据](docs/testing/profile-authorization/20261023/README.md) |
| CH-07C2b2b-B | 已完成内部执行及恢复 | Codex | 667/668首轮、旧断言更正后原文件53项通过，产品未变；四门及独立复核通过。同次回答/费用/待核档案/固定回执原子保存，恢复无重发；原生/HTTP/UI待接 | [合同](docs/plans/2026-10-23-profile-execution.md) · [证据](docs/testing/profile-execution/20261023/README.md) |
| CH-07C2c | 已完成后端应用入口 | Codex | 4,393全套Python/四门/独立9及10通过；私有许可、预览与同队列HTTP接线，实际子进程恰好一次回环；未接桌面UI | [合同](docs/plans/2026-10-23-profile-application.md) · [证据](docs/testing/profile-application/20261023/README.md) |
| CH-07C2d | 已完成源码与实机入口 | Codex | 366桌面/68前端/19相关Python、四门、独审与原生5组通过；0模型/0业务写入，未接统一自动归档页面 | [合同](docs/plans/2026-10-23-profile-desktop.md) · [证据](docs/testing/profile-desktop/20261023/README.md) |
| CH-07C3a | 已完成文字页面闭合 | Codex | 265相关Python/366桌面/141前端、四门、独审及Windows6组通过；同次待核草稿保存与只读侧栏，未知请求GET找回 | [合同](docs/plans/2026-10-23-profile-ui.md) · [证据](docs/testing/profile-ui/20261023/README.md) |
| CH-07C3b | 已完成本次源码/浏览器范围 | Codex | 12字段人工编辑、联系方式、材料状态、精确金额、UTC跟进时间及受保护清空；旧版本/恢复副本/归档只读，未知提交仅找回；后续自动提案保留人工值。安装交付待CH-10 | [本次实测](docs/testing/conversation-maintenance/20261024/README.md) |
| CH-07C3c | P1 · 后续材料范围 | 待认领 | 附件/技能范围的受控建档及原文跳转联动；不由普通文字许可扩权，Jev需独立许可 | CH-07C3b |
| CH-08 | P1 · 首片在 dhb_law 验证 | dhb_law | 已保存回答/档案版本的分受众预览、复制与 Word 下载贯通；客户仅 client_reply，内部回答不能换标；技能/附件成果及安装版待后续 | [源码与实际验证](docs/testing/chat-output-export/20261025/README.md) |
| CH-09-续 | P1 · 随新增表同步 | 对应模块作者 | 现有对话/附件/调用账本恢复已覆盖；新增档案/成果仍需完整备份、旧版本兼容、只读拒写和不重发 | 与 CH-07/08 同片实施 |
| CH-10 | P1 · 待整体验收 | 待认领 | 新安装候选贯通聊天→收件→生成→档案→引用→导出；断网/Jev缺席、中文路径/输入/缩放、升级与资源实测；不覆盖本机真实资料 | 核心链具备可测范围 |
| CH-11 | P1 · 待统一接入 | 待认领 | 持衡固定四动作、材料映射、角色/阶段隔离和同请求幂等；两仓独立环境、失败可恢复 | 公共材料与权限接口 |

CH-05C/D1/D2 是协作细分标识，不替换 v2.1 中 CH-05 的总体验收；[架构交接](docs/plans/2026-10-20-jev-native-handoff.md)第一片已由CH-05C实现，第二片后端由[CH-05D1](docs/plans/2026-10-20-jev-request-backend.md)落实，同窗确认由[CH-05D2](docs/plans/2026-10-20-jev-confirmation.md)完成。Jev当前账本只接受完整普通文字意图判断；材料分类、运营风险须另建来源映射。预算预留不等于供应商收费上限或已付费用。

## 已完成的可复用切片

- [x] CH-00A 首片：公共存储初始化、HTTP 请求上下文及对话服务解耦；更广拆分仍在上表。
- [x] CH-00B 首片：PDF 延迟加载和 Electron 语言资源筛选；[同后端构建减少 46.62 MiB](docs/testing/chat-first/20261016/README.md)，不代表整体资源目标完成。
- [x] CH-01：对话存储、作用域、幂等、草稿、事件、迁移及受控恢复基础。
- [x] CH-02 首页切片：草稿、技能卡选择、历史、中文输入保护、取消/续读和生成历史呈现；技能卡不等于业务执行已经全接通。
- [x] CH-03A：建案前 DOCX 收件、原文版本、权限与恢复；未声称所有格式可读。
- [x] CH-04A—I：普通文字主生成、账本、会话授权、系统保护凭据、原生设置/具体发送确认及旧 provider 引用释放；真实调用保持未验，详见 [接线记录](docs/plans/2026-10-19-post-home-readiness.md)。
- [x] CH-05A：Jev 薄提供器/严格响应解析/纯路由，367 个关联用例；[证据](docs/testing/jev-adapter/20261020/README.md)。
- [x] CH-05B：独立辅助账本、升级与恢复，703 个关联用例；[证据](docs/testing/jev-ledger/20261020/README.md)。这些与前项为各阶段回归，不累加为总测试数。

- [x] CH-05C：Jev 原生独立配置生命周期；[190/119测试及Windows各9组实测](docs/testing/jev-native/20261020/README.md)，不代表辅助发送已经贯通。
- [x] CH-05D1：逐请求后端许可、固定私有协议和同任务可选辅助；[源码与冻结控制验证](docs/testing/jev-request/20261020/README.md)，不代表D2确认UI或真实调用已完成。

- [x] CH-05D2：同窗独立许可、可选辅助与失效清理；[Windows实测与独立复核](docs/testing/jev-confirmation/20261020/README.md)。真实辅助未启用。

- [x] CH-06A：独立法库引用及前后权限检查；[Windows合成库实测与独审](docs/testing/library-adapter/20261020/README.md)，内部接口不代表自动查库/法律判断已贯通。

- [x] CH-00B2：检索共用按区间定位；[同源前后内存/耗时、183项加2项补验通过及独审](docs/testing/library-memory/20261020/README.md)。未覆盖Electron/RSS/冷启动。

- [x] CH-06B1：固定调用事件、持久引用、不可变回执、历史授权与完整备份迁移；[全套及独立复核证据](docs/testing/library-ledger/20261020/README.md)。HTTP/UI、4轮模型和自动档案仍未完成。

- [x] CH-06B2a：本机检索、持久引用面板、未知请求找回、取消与只读恢复；[源码分批回归与浏览器证据](docs/testing/library-chat/20261020/README.md)。资料辅助生成与自动档案仍待。

- [x] CH-06B2b1：独立完整上下文预览接口、旧文字协议不变、无外发及恢复副本拒新预览；[关联回归和实际HTTP证据](docs/testing/context-preview/20261020/README.md)。未完成资料发送或新选片UI。

- [x] CH-06B2b2：`assistant-context-v1` 不可变输入格式、有序来源关联、原生一次许可与备份恢复同片闭合，一次资料辅助回答链路接通；[关联回归、原生回环字节与升级恢复证据](docs/testing/context-send/20261021/README.md)。律师选片GUI、真实供应商与有界多轮仍待。

- [x] CH-06B2c1：`assistant-rounds-v1` 重建 attempts 表支持有界轮次（round_no 1–4 不可变、UNIQUE(run_id,round_no)），三条迁移通道 FK OFF 窗口同序闭合、新建与升级字节一致、数据行保留；完整性校验对多轮归档 fail-closed；[结构/迁移/损坏矩阵与关联回归证据](docs/testing/bounded-rounds/20261021/README.md)。行为不变（恒 round 1），循环 runner、工具计划协议与轮间授权仍待 B2c2。

- [x] CH-06B2c2：`library-context-v2` 工具计划响应协议与同 run 受限串行循环 runner（model round→固定 library handler→下轮/final，≤4 轮模型/≤8 工具）；轮间授权显式形状 max_rounds；结构版本 `assistant-rounds-v2`（CHECK 加宽含 v2，复用 12 步重建、三条通道同片闭合）；四种有界停止原因与恢复封存不重发；完整性开放 v2 多轮语义（plan↔tool.before↔receipt↔下轮 exchanges 精确绑定，篡改矩阵全拒）；[runner/schema/授权/完整性矩阵与广域回归证据](docs/testing/bounded-rounds/20261021/README.md)。v1 字节与行为完全不变；真实供应商接入、律师选片 GUI 仍待排期。

- [x] CH-06B3：律师选片 GUI 三层落地——网页选片面板（`assistant-context.mjs` 控制器：savedCitations 汇集、保序≤8、request_id 惰性铸造、点选/编辑/换对话即失效、与 generation/research 三向互斥）；预览扩展（`MainContextSelection.request_id` + `MainContextPreview.send_basis`，ready 且给 request_id 时服务器组装 v1/v2 basis，DTO 校验逐字段一致且 source_bindings 与 manifest.sources 同序）；桌面授权链（preload `authorizeContext` → `desktop:approve-context` 处理器自行 GET 草稿/材料 + CSRF POST context-preview 全量比对 → 确认窗六键 library_context 变体渲染片段清单 → 单次 lease → Python `_OPERATIONS` 分发既有 `authorize_context`）；发送走 context-generations，NETWORK_UNKNOWN 只经 by-request 找回；[前端/桌面/Python 关联回归与端到端合成走通证据](docs/testing/selection-gui/20261021/README.md)。无 schema/依赖变更；v1 单轮锁定（max_rounds 锁 1），真实供应商接入与 v2 多轮界面仍待排期。

- [x] UX-01：对话页模型 UX 小片（所有者直接指令）——排查"API 已配置但发送按钮灰色"：模型启用为后端进程内存态（重启即失效）、capability 需已保存草稿触发，设置页「返回」整页重载本就缓解，本片补窗口焦点回来自动重拉 capability。取消每次手动「配置本次运行」（所有者明确指令的安全姿态变更）：所选模型持久化于 desktop-settings.json（严格校验），后端就绪自动用本机已存密钥恢复配置；显式停用才清除、换密钥不清除、恢复副本永不自动配置、Jev 不参与；每次发送的原生确认窗/单次 lease/会话绑定/120 秒有效期全部不变，密钥仍只在 OS 保护存储。对话页「保存草稿」左侧新增「切换模型」按钮：新 model-bridge.cjs 两 IPC（仅对话页主 frame、ready、非恢复副本），Flash↔Pro 互切并持久化，切换后自动重算 capability，无桥时按钮隐藏。桌面全套件 270/270（新 model-bridge 5 项、导航 2 项旧语义按新行为更新+2 项新增、桥键断言同步）、前端全套件 68/68（新增渲染 2 项）、四开发门 exit 0；Python 后端零改动。推送后真实启动回归（当日修复）：settings 的 model 键泄漏进 backend.start 参数触发 desktop_entry 白名单 BACKEND_REJECTED，已改为传参前剔除该桌面侧键并加防回归断言，复跑桌面 270/270、真实启动后端拉起验证通过。[证据](docs/testing/model-ux/20261022/README.md)、[执行合同](docs/plans/2026-10-22-model-ux.md)。
- [x] UX-02：材料拖拽与多文件切片（所有者直接指令）——拖文件到对话页任意位置入队（整页虚线高亮蒙层、drop 展开面板、扩展名+mime 前端预筛并点名拒绝不支持格式）；格式扩为 DOCX/DOC/XLSX/PDF/PNG/JPG/CSV：domain 六值 mime 枚举+后缀映射 model_validator，attachments 新增 _assistant_type 内容嗅探（docx 维持 read_package、xlsx 校验 ZIP 结构、pdf/png/jpg 魔数、csv UTF-8 非空），案件侧 _type 不变；policy_id 放宽为 v1（存量兼容）+v2（新上传）；parse 仍仅 DOCX（非 DOCX 400）；下载原件后缀按实际文件名。多文件待传队列 chips（文件名+大小+× 单删+清空待传），一次同意顺序上传（独立 request_id 回执、i/N 进度、失败即停保留剩余、NETWORK_UNKNOWN 重试经 inflight 跟踪退役队列项）；非 DOCX 行显示格式标签、预览仅原件+下载不出读取按钮。**已上传原件不物理删除**（attachment_integrity 账本要求历史快照引用存在，物理删除需账本版本化另立片）。GitHub 复用评估：Dropzone/FilePond/Uppy/file-type 均因无法对接回执协议与伪 DOM 测试夹具而不采用（执行合同附对照表）。Python 新增 5 项全过、关联回归 109 过+2 基线复现环境失败（safe-delete shim 超深路径 Errno 53 家族）、前端全套件 146/146（新增 4 项）、四开发门 exit 0、桌面零改动。[证据](docs/testing/material-files/20261023/README.md)、[执行合同](docs/plans/2026-10-23-material-files.md)。

## 数据及交付前提

- [ ] 继续复用本地案例/法规索引成果；增量清洗、失败恢复和来源回查以既有导入记录为依据，禁止重复覆盖原件。
- [ ] 1985—2024 年数据目前在用户百度网盘、尚未下载；不能把年份范围当作本机入库数量。
- [ ] 阿里云在线资料库：服务器、访问权限、部署与迁移验收尚未完成；本机可查不代表多人在线可用。
- [ ] 受邀注册、验证码/密码登录、找回密码、设备会话与在线更新仍需独立交付，不由本机密码登录替代。
- [ ] 法律规则/材料使用许可、真实模型有限调用、律师质量验收及生产批准分别落实；不增加收费系统。

## 每次完成任务时

1. 更新本表的真实范围和剩余项，在 TASK_STATUS 添加结果、限制及证据链接；README 更新协作者需要知道的能力变化。
2. 记录实际目标检查与独立复核。没有运行的写未运行；相同输入和已完成验证不反复重跑。
3. 获取远端更新、检查协作者改动和待推送文件/历史。仅提交任务相关文件；真实材料、密钥、运行库及安装产物留本机。
4. 按 [协作约定](CONTRIBUTING.md) 正常推送到对应分支，再核对远端 SHA；遇到分叉先整合复核，不强制覆盖。同步失败保留本地提交，记录原因，不写已同步。
