# CH-07A 自动档案纯合并内核：Windows 源码证据

2026-10-23（北京时间），基线 `a6d20edf8663222ce6469bae80edfc92c02627b2`；现有分支 `codex/contract-review-v2`。只用独立合成材料，无真实模型、客户资料或法库处理。

## 已实现

`assistant/profiles.py::merge_profile` 接收严格模型提案、受信来源快照和可选人工编辑，返回档案候选快照及可选 `IntakeDraft` 投影；DTO 仍统一在 domain.py。没有数据库、Web、解析器或供应商依赖；没有时间获取、随机标识、自动客户合并或持久化副作用。

- 消息引用绑定对话、消息、版本、精确字符范围及摘要；文档引用绑定选中附件、原件摘要、解析版本/结果摘要和完整 Anchor。历史引用也校验原对话及历史版本上限。来源定位不代表事实核实或当前权限有效。
- 未提供、unknown 和受保护的人工清空分开处理；同值合并来源，异值并列待核。本金、利息、付款分别保存精确金额和币种，不选最新/最大值，不进行换汇。
- 律师编辑、旧接待字段（包括空字段）受保护；有投影基线时比较当前接待改动。客户回复与内部意见分字段；状态沿用，材料不自动 checked；超限拒绝、不截断。
- 明确受信开关才产生投影；普通写作/空提案不建立接待。冲突字段不任选候选。模型不能填写已知联系方式，本片 contact 仅受信人工编辑，自动本地识别仍待接入。
- 输入语义确定性；使用当前 base revision 重放相同提案不新建修订，同值新增真实来源算有效变化。过期 base revision 拒绝；请求级幂等回执留给 CH-07B。

## 实测

| 项目 | 实际结果 | 证据 |
| --- | --- | --- |
| 最终关联回归，12个文件 | **400 passed，0失败/错误/跳过，exit 0**；其中45项为新内核测试 | [目标清单](target-nodeids.txt)、[日志](target.log)、[JUnit](target.xml) |
| 四项开发门 | schema/defaults/sources/runtime-dependencies 均 exit 0 | gate-1.log 至 gate-4.log |
| 验证输入 | **522** 源码、配置、测试、脚本摘要前后一致；目标进程108.282秒 | [完整运行记录](target-verification.json) |
| Spec 独立复核 | 6/6，exit 0，4输入稳定；2发现关闭 | [报告](spec-review.md)、[命令与摘要](spec-command.json) |
| Standards 独立复核 | 9/9，exit 0，3输入稳定；2发现关闭 | [报告](standards-review.md)、[命令与摘要](standards-final.json) |
| 依赖边界 | 独立解释器拒绝加载Web/数据库/文档处理/模型供应商模块仍可导入内核；旧domain定义前缀兼容 | 新单测及Standards探针；不等同启动/RSS/包体实测 |
| WorkBuddy | 本轮实际status为native_unavailable、无活动端点；未派发或重试 | [连接记录](workbuddy-status.json) |

sources 检查仍报告13项 NOT_PRODUCTION_APPROVED；通过的是开发门，不是生产来源批准。最终400项不能与历史393项或独立探针相加冒充一次全套。

## 失败及修复记录

- 最初缺少新DTO的导入失败只证明入口未实现；其包装命令未保留pytest退出码，见 `red-message.log`。`red-merge.log` 为1失败/2通过的有效合并行为失败。
- `red-protection.log` 含一处测试夹具错误；修正 anchor 类型和长度后，`red-document-protection.log` 保留3处尚未实现行为失败。`red-boundaries.log` 是测试语法错误，不算产品RED；修正后 `red-boundaries-valid.log` 复现零金额两种写法被误判冲突（1失败/37通过），已修。
- 独立Spec复现联系方式补造和旧快照核验状态不一致；Standards复现环境Decimal精度绕过及旧引用跨会话。主测试 `red-review-findings.log`、`red-history-scope.log` 保留失败，最终均关闭。
- 金额验证改为与环境上下文无关的精确数字/指数边界，最多16整数位、8小数位，零先归一化；修复后的测试曾用Decimal显示写法而非数值比较，`green-review-findings.log` 保留这处测试断言失败，随后改为精确数值比较。
- 修复前393项关联回归和四门也曾通过，证据保留在 `pre-review-fix/`；它不包含后补反例，不作为最终结论。最终增加7项反例后400项通过。

所有原始证据的字节数/摘要列于 [manifest](evidence-manifest.json)。未执行整仓全套、桌面、冻结后端、安装器、真实模型、当前权限或法律质量验收；安装版仍0.4.1，真实资料/F盘/云未操作。

## 下一阶段

按 [实施计划](../../../plans/2026-10-23-profile-merge-core.md) 与 [设计复核](../../../plans/2026-10-23-profile-draft-readiness.md)，CH-07B 将来源/权限与版本重核、档案修订、现有接待create/save、投影回执及成功事件放在同一短事务/savepoint，并同步迁移、备份与只读恢复。CH-07C 再接主模型结构化输出及固定钩子。纯内核完成不代表自动建档已可用。
