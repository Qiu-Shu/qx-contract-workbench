# 微信合同模拟响应协议回归

2026-11-02。本片在隔离修复副本完成，仅修改 tests/integration/test_weixin_personal_runtime.py；产品与共享 helper 未改。最终134个不同用例通过，两轴独审完成。本次用户另行明确授权上传 GitHub 并生成交接，上传作为独立候选快照处理，默认分支、主仓源码与既有暂存保持。

## 原因与修正

原4个场景为桌面选择主材料、附件优先、指令优先、重审与迟到材料。原定点运行4失败；保留的4个数据库中共有6份完整prepared及6份received回执，均因MODEL_OUTPUT_INVALID拒收，0份成果。费用与30 token/次记录仍在，拒收不是零费用。

旧测试Provider返回普通text/citations候选，缺少当前contract-review-v3要求的contract_review结构。产品拒绝降级响应符合约束。测试在manifest要求合同成果时复用现有contract_review.candidate和draft_for；其余业务继续原文本候选。preflight、hold与调用计数保持。桌面断言由旧固定文本改为读取实际保存候选、确认合同结构，并逐字检查经过bounded_reply的真实MockTransport消息恰好发送1次。原任务、补件版本、历史与调用次数断言保留。

## 实际验证

| 批次 | 结果 | 退出码 |
| --- | --- | --- |
| personal-contract-original-red | 4失败，原样保存 | 1 |
| personal-contract-target-green | 4通过 | 0 |
| personal-contract-related | 118通过 | 0 |
| personal-contract-indirect | 16通过 | 0 |

4条pytest命令。目标4项已包含于118项，最终去重118+16=134，不能写成138。关联含个人微信、桌面、指令顺序、服务台，以及合同decode/settle拒收保留费用且不重发的反例；间接覆盖统一意图控制和共享判断调用测试Provider的场景。最终批无pytest warning；原RED模型拒收警告保留。四开发门本片未重跑，因为只改测试；候选上传树验证另行记录，不混作本片测试。

Spec与Standards独审无本片待处置发现。固定990份源码，唯一变化为该测试文件；H346/Q113/S90/U212/V107及T12旧准备、主仓716保护文件和暂存一致。协调器曾误用Python脚本为可执行文件、误读汇总字段名及探索两个不存在的脚本路径，修正后检查通过，原失败命令保留，不计作产品用例失败。

## 原完整套件终端与后续

固定原N副本的90073于2026-11-02T07:32:00Z自然结束，退出1：8535通过、28失败、58设置错误、21跳过，12警告，7106.96秒；合计8642。58个设置错误已逐条核对，全部是test_workspace_upgrade.py:39旧夹具漏删扩展表导致精确schema不符，Q片已在R修正该夹具。28失败仍保留原记录，分别对应已定位的长路径、旧断言、案件容量、接待与本片微信场景。

以上完整套件运行的是原N983源码，不是当前修复R990；不能称修复后全仓通过。原90073与更早预算失败84461均已终端，禁止继续等待或重启它们。下一步先核修复后的统一回归范围与资源，再进行一次新的固定基线验证；WIN-PATH-02间歇rename访问拒绝仍开放，不能用其他长路径测试通过覆盖。

商标正式新材料仍0/4原答、0/8评分；E46准备不重做，历史失败分母不变。合同补发仍待既有确认；模型伙伴接口待办。客户接待继续超级销冠、家事本机新版与持衡适配；刑事维持synthetic-only-v1。没有真实微信/工作台付费模型调用、签发、安装或生产发布。当前候选不等于法律质量采用或生产验收。

本地证据：隔离修复副本 .audit-local/weixin-personal-contract-regression-20261102；入口为author-review-input.json、author-review.diff、author-source-snapshot.json、author-verification-summary.json、checks-summary.json、两轴final-review.json和original-full-terminal.json。原日志、XML、DB及旧失败保持本地，公开仓库只发布可共享源码和可读说明。上传回执与交接另见候选分支docs/handovers/2026-11-02-skill-integration.md。
