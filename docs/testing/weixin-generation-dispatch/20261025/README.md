# D2g5d — v19固定历史代际合成分发（2026-10-25）

基线`86daac9c6d13dae49dc30eac60113bda711625a9`，Windows实际仓库D:/Documents/ChatGPT/律所项目。仅专用Python合成服务；不是微信账号接通或桌面自动poll开关。

## 源码已实现

[新generation_dispatch.py](../../../../src/cn_contract/weixin_inbox/generation_dispatch.py)提供dispatch_generation_descriptor/find_generation_dispatch_receipt：native v19、实际principal/owner/workspace、active/fence/撤权与root当前ACL/归档、固定历史target完整scope/当前ACL。sidecar解析固定目标，不以latest代替；同账号零代旧pending与其他peer继续用root binding/current effective grant。已存回执按固定目标当前ACL只读找回，恢复/逻辑撤销/会话归档可查；新写/重放仍受恢复和撤权阻断。未知descriptor不泄漏归属，未分发原始描述只查返回None，无任务写入。

[dispatch.py](../../../../src/cn_contract/weixin_inbox/dispatch.py)只提取共享私有_deliver与_verified固定binding参数，旧公开guard/旧顺序保持。沿用13字段immutable receipt、TaskInbox/TaskDraft聚合与cursor CAS；每(root mapping,fixed binding)顺序分发，旧root pending不阻新代，不比较不同binding的cursor。来源namespace不变，不自动冻结/审查/外发。receipt时间严格排在poll/generation/task event和既有活动之后；task event本身可因时钟回拨早于poll。

[schema19](../../../../src/cn_contract/weixin_inbox/generation_dispatch_schema.py)仅新增精确UNIQUE(task_binding_id,expected_task_cursor)，无重复delivery表/DTO。18前驱36组native/non-native raw/normalized指纹保留，前34与旧fixture逐项相同；fresh/repeated bootstrap与升级一致，错列/非unique/多余index仍拒绝。旧family所有版本门接续，包括model五处、TaskDraft、inbox/grant/provenance/生成服务/代际收件，不以新版本跳过旧校验。

[dispatch_integrity](../../../../src/cn_contract/weixin_inbox/dispatch_integrity.py)和[generation_integrity](../../../../src/cn_contract/weixin_inbox/generation_integrity.py)仅v19分支允许固定非零代/后代分发。root与后出生target因果分开，逐流前缀、相同binding不重叠、payload/TaskInbox实际来源、poll/代际/事件时间、grant/撤权继续核；public dispatch直接验证完整代际父链，私有纯校验避免公共递归。v17/v18旧规则保留。上轮原生升级旧语义预检继续阻止非法旧历史被新语义洗白。

## 本轮实际验证与已有测试

[机器回执](verification-summary.json)列完整argv/UTC/退出码/全部不同ID及564输入摘要。13个关联短组45个模块/筛选切片共 **1329不同Python全部PASS**，含100新增（schema52/runtime29/integrity11/atomic8），0FAIL/ERROR/SKIP；不是历史累计/单次全仓。native组用-k native，另213 deselected，不称三个旧schema文件整文件全跑。四开发门exit0；来源13个NOT_PRODUCTION_APPROVED、native_build_verified=false及legacy组1条故意伪造输入的Pydantic warning保留。Node/前端未改，本轮NOT_RUN。

| 根最终组 | 不同Python | 结果 |
|---|---:|---|
| final-new | 48 | PASS |
| final-schema | 151 | PASS |
| final-native | 60 | PASS |
| final-migration | 176 | PASS |
| final-legacy | 110 | PASS |
| final-dispatch | 38 | PASS |
| final-integrity | 232 | PASS |
| final-targets | 101 | PASS |
| final-ingress | 52 | PASS |
| final-provenance | 108 | PASS |
| final-routes | 87 | PASS |
| final-task | 98 | PASS |
| final-preview | 68 | PASS |

根新增真实入口覆盖两代及指令/附件两种聚合顺序、零代旧pending/其他peer、顺序/CAS/碰撞/当前权限/固定find、SQL及commit故障回滚、实际commit后丢ACK只查、同/异descriptor线程、append竞争、新Python进程。两次真实合成qxbak验证旧session401、重新login固定回执可查、新写BLOCKED_LIVE、各enable/egress位false，独立DOCX原件/源与归档字节保持。没有通过SQL fixture代替该新入口的运行验收；11个独立来源反例另使用真实TaskInbox接收后构造归档receipt，仅作校验fixture。

所有产品输入跨组同一最终SHA且每组before=after。完整测试树另有两文件在未受影响组结束后各改一个test函数体；AST证明其imports/helpers/fixtures完全不变、无其他模块name/import引用，旧组未执行这些case，两个受影响组已在新摘要完整重跑。[精确差异证明](test-only-correction-proof.json)及各组unused_test_snapshot_deltas明确列出，不能冒称全部564输入在所有组都同一哈希。

## 独立复核与失败历史

[运行/完整性交叉审查](runtime-integrity-review.md)由未写该产品部分的存储代理完成；[存储/完整性交叉审查](runtime-cross-review.md)由运行代理完成；作者排除范围明确，两者最终0确认遗留。根新增atomic/旧夹具经[独立复核](test-compatibility-review.md)。独审实证的无generation旧回执查询漏父链，先RED后在专用入口显式核inbox/dispatch/grant/provenance闭合，再由原探针GREEN复验，未改旧入口。

额外[精确v18非法非零回执升级探针](independent-v18-upgrade-proof.json)1PASS：先证v19合法，再drop唯一index+更新marker精确成v18；实际原生upgrade按v18语义拒绝，DB/marker/目录/原件零变更，不创建备份/升级回执。此独立探针不加入上面的根总数/100新增。

存储初始15FAIL/37PASS为缺v19/新模块；运行初始2FAIL为缺入口；空gen父链2FAIL/1PASS后3GREEN。根完整性正式RED8FAIL/3PASS，之前两次测试列名/FK/UUID返回值夹具失误日志保留，不能算产品失败证据；根RED前后SHA未捕获标NOT_CAPTURED。初步2/26/29/11/8重复不累计；最终计数仅取13根XML。

旧版本夹具首compat3FAIL/1PASS/1ERROR因后继index/sidecar残留和硬最终版本，修精确构造后5PASS，完整关联153PASS。保留历史fingerprint及旧拒绝oracle；v17→v18 marker-gap显式冻结，不用未知结构误报旧版本保护。

首次final-provenance为105PASS/3FAIL：坏档案被新v19更早的dispatch父链校验拒绝，旧GEN错误码断言失败。只改当前v19创建/恢复两处精确DISPATCH断言，损坏payload/不得创建/零出版/字节不变不变，完整108关联重跑覆盖此前未到的恢复半段。首次final-integrity为230PASS/2FAIL：新UNIQUE在构造binding/overlap坏数据时先拒绝；binding删除冲突peer回执仍测v19错误目标，overlap明确构造精确v18保留旧归档拒绝，新v19 SQL约束另有独立测试。完整232关联重跑。[独立诊断](backup-oracle-review.md)及原始失败日志/XML保留；未为这些断言修改产品或放宽regex。

WorkBuddy由宿主native ACP核实kimi-k3-2；只读辅助任务请求Bash被bridge拒绝取消，retry_safe=false，无报告/代码采用、不重试。[实际状态](workbuddy-result.json)。本聊天代理独立完成实施/验收，不将WorkBuddy启动称完成协作。

## 尚未实现及NOT_RUN

真实微信可信身份、账号资格/数据政策、transport/下载解密/外发及E有限期模型许可仍待；无新HTTP/UI或自动收件分发开关。真实微信/合同/产品模型/付费调用、全仓长单进程、Node、浏览器/Electron/安装版0.4.1均NOT_RUN，0.4.1未更新。WIN-PATH-02/原生长进程AV保持OPEN。

GitHub按后续实际回执核对，用户AGENTS保持未暂存。HumanLayer旧摘要因Windows argv限长仍待同步；Obsidian/本轮HumanLayer结果按收尾实际回执，TencentDB沿正常Stop，不预报保存成功。

最终[证据独审](final-evidence-review.md)重新核算计数、来源SHA、两处test-body例外及发布字节，0确认问题；不含后续Git同步回执修改，也未重跑测试。
