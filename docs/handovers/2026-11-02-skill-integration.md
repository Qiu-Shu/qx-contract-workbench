# 群兴 Skill 融合：2026-11-02 开发交接

这是分阶段整合的开发候选快照。它保留现有统一工作台、合同/案件方法、来源校验和本地回归修复，不是生产发布、安装包或法律质量采用结论。用户已明确要求上传 GitHub；默认分支不变。

## 接手入口

先读 [任务状态](../TASK_STATUS.md)、[规格](../../sources/specification-v2.0.md)、[来源锁](../../sources/upstream.lock.json)，再读 [阶段进度](../plans/2026-11-01-unified-progress.md) 与 [商标新材料计划](../plans/2026-11-02-trademark-v56-content-comparison.md)。既有总体方案与法律 Skill 取舍方案均保留在 docs/plans。不要根据旧报告的“未提交”推断本候选不存在：旧报告记录各片当时状态。

候选分支：codex/skill-integration-checkpoint-20261102；父提交：15acd84546616f8c44dc394e04bf7753cad72739。提交由隔离修复副本构建，保留主仓未提交修改及暂存，不切换主仓/修复工作树。

## 最近已确认工作

最新 [微信合同回归](../testing/unified-plan/20261102/weixin-personal-contract-regression.md) 仅修测试Provider协议：原4失败保留，最终134不同关联通过，产品合同结构校验不变。四次pytest分别4失败、4通过、118通过、16通过；目标4属于118，不能重复计数。Spec/Standards独立审阅完成。

此前 [超长目录首次创建](../testing/unified-plan/20261102/long-path-initialization.md) 最终80不同用例及四开发门通过；[接待续办](../testing/unified-plan/20261102/reception-continuity-regression.md)、[案件容量](../testing/unified-plan/20261102/case-input-capacity-regression.md)、[升级恢复](../testing/unified-plan/20261102/long-path-upgrade-recovery.md) 和 [较早回归](../testing/unified-plan/20261102/trademark-regression-repair.md) 记录各自独立证据。不得跨批简单相加为全仓通过数。

原固定基线完整套件已自然结束：8535通过、28失败、58设置错误、21跳过，退出1，12警告，7106.96秒。58设置错误均为旧升级夹具漏删扩展表造成精确schema不符，此前升级恢复片已修其隔离副本。28失败原件保留并由各片定位。这个结果属于原983文件基线，不能称当前990文件修复候选已经全仓通过。

## 下一步

1. 核对本候选及来源边界，先拟定一次修复后固定基线的全仓验证，检查独立临时目录和磁盘预算；原终端任务不可重启或继续轮询。
2. WIN-PATH-02最终目录rename间歇访问拒绝仍开放，先做首次错误现场诊断，不能加入盲目重试或放宽权限掩盖。
3. 商标v5/v6新材料准备已完成，正式实验仍0/4原答、0/8评分。不要重做准备或用新结果覆盖旧失败。工程基线清楚后再按既有冻结协议推进。
4. 合同补发仍待既有明确批准；模型伙伴接口未完成，继续待办。案件v5保留40计划/32有效/8失败；商标v4/v5保留4原答、6/8有效评分，采用未建立。

客户接待复用超级销冠，家事复用本机新版，持衡通过适配器接入。外部Skill/法库原文、私有配置和本地路径依赖未随此分支打包；新机器须按既有配置说明准备合法来源，不能把本分支称为完整可移植安装版。保留第三方许可及来源，刑事维持synthetic-only-v1，禁止让模型补造刑事内容。

## 发布与证据边界

公开仓库仅上传选定源码、测试、配置、许可与可读Markdown报告。4个浏览器用户资料目录及本轮原始DB、缓存、回执、图片/二进制证据保留本地，未加入此候选。部分历史报告链接指向本机证据，在其他机器不可访问，这是明确限制；不伪造公开证据链接。依赖开发门需要固定本地缓存，来源/依赖通过不等于生产批准或原生安装可复现。没有执行真实微信、QCC、工作台付费模型、外发签发、安装、合并默认分支或发布。

## suggested skills

下一代理按任务读取并使用 ponytail（最小充分改动）、diagnosing-bugs（失败诊断）、code-review（两轴独审）、superpowers:verification-before-completion（实际验证）和 handoff（续接）。已有计划、失败记录、评分协议优先，避免重复访谈或重构整仓。
