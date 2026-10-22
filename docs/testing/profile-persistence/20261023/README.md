# CH-07B 本地档案保存与恢复

基线 `2b72c9a02a25607761705811550323fa9fcfce00`，Windows / Python 3.12，独立合成材料。沿用 [v2.1](../../../plans/chat-first-architecture-v2.1.md) 和 [本片执行合同](../../../plans/2026-10-23-profile-persistence.md)。

## 实现范围

- 新增 `assistant/profile_store.py`，复用既有来源读取、纯合并和接待服务。来源字节检查在写事务外；短事务再检查当前会话、权限、恢复栅栏、作用域、档案和接待版本。
- 同一 savepoint 保存档案修订、接待修订、首次关联和内部回执。故障注入覆盖五个写入位置，包括调用方捕获异常后提交外层事务。相同请求找回原回执；无实际变化只保留一份该请求回执，不增业务修订。
- `assistant-profiles-v1` 只增加两张不可变表，十种旧结构分别验证原生/非原生升级。旧结构摘要冻结；部分结构、DDL故障、升级标记故障可拒绝和回滚。
- 提供经过当前鉴权的档案、指定修订、按请求找回和显式提交接口。恢复副本只读。所有业务 DTO 在 `domain.py`；无新增运行依赖。
- 接待页和内部 Word 区分“接待摘要”与“咨询原话”。只改标题保留摘要来源；一旦人工改正文就打断继承，即使后来改回同样文字。客户导出继续只允许客户回复字段。
- 历史验证从固定版本的消息和选片重放，验证摘要、关系、时序、人工保护、投影及无孤立修订。现时撤权/归档/重新解析不会把原来有效的历史误判为损坏。qxbak 包含新记录和原文；旧范围 cnbak 不允许夹带档案记录。

## 已执行的定向验证

| 范围 | 最后定向结果 | 原始记录 |
| --- | --- | --- |
| 保存、幂等、故障回滚、人工保护、跨会话与派生键碰撞 | 32 passed | [store/review-fixes.xml](store/review-fixes.xml) |
| 新 schema 与全部旧版本升级 | 71 passed | [migration/profile-schema.xml](migration/profile-schema.xml) |
| 原生升级及失败恢复 | 53 passed | [migration/upgrade.xml](migration/upgrade.xml) |
| 历史完整性、篡改、qxbak、独立读取边界探针 | 31 passed（28正式测试＋3独立探针） | [integrity/review-final.xml](integrity/review-final.xml) |
| HTTP鉴权、命令限制、恢复和接待来源 | 15 passed | [http/target-2.xml](http/target-2.xml) |
| 既有接待/入口/导入边界 | 32 passed | [http/regression-1.xml](http/regression-1.xml) |
| 本机 Chromium 合成界面 | 1 passed | [http/browser-2.xml](http/browser-2.xml)、[截图](http/intake-history.png) |

上述为开发过程的不同定向运行，含重叠用例，不相加冒充完整套件结果。

## 完整回归与开放项

完整 `tests` 实际 **3,816 passed / 3 failed / 0 errors / 0 skipped**（3,819项，2948.97秒，exit1），四项开发门均exit0，532份输入前后摘要一致。见 [原始日志](target.log)、[JUnit](target.xml)、[命令/数量/摘要](target-verification.json)。未重写失败记录，也未重复启动49分钟全套。

1. 外部资料目录用例的临时根实际在项目`.local`内，与默认允许范围重叠。已将合成安装根与用户资料目录明确分开，补错误父目录拒绝断言；9项定向通过，产品守卫未改。[诊断与6项路径探针](desktop-boundary/diagnosis.json)、[复验](desktop-boundary/green.xml)。
2. Jev协议旧替身缺少真实主模型服务已有的`authorize_context`。只补立即拒绝调用的方法；36项协议测试通过。故意把Jev路由到主模型或上下文，两项负控制均按预期失败，没有用放行替身隐藏越权。[诊断](judge-fixture/report.json)、[复验](judge-fixture/target.xml)。
3. 长路径恢复在最终发布目录`rename`报WinError5。结构/摘要/隔离标记已校验返回，首次发布未完成；原件与合成归档保留。先前独立复跑通过，但不能替代原始失败。此处没有确认文件锁、杀软、ACL或长路径本身为根因，也不能套用旧WorkBuddy回收站shim的Errno53。**WIN-PATH-02继续开放，整体Windows恢复验收未完成。**

完整回归后只有上述两个测试文件变动，产品源码保持一致。按原全套顺序重放截至故障的前79项，79 passed（122.89秒），400份Python输入稳定；3次发布前累计跟踪15个原生SQLite连接均已关闭，未观察到自有SQLite连接遗留。探针会影响时序，且不覆盖所有原生目录句柄或外部占用；通过不能证明原始问题已修复。[顺序/连接探针](path-order-probe.json)、[独立只读复核](path-diagnostic-review.json)、[最终输入与结果汇总](final-verification.json)。

## 失败与独立复核

- 有效初始失败：保存模块缺失、HTTP 404、迁移仍返回旧结构、完整性模块缺失。
- 开发夹具错误均保留：恢复栅栏用了不存在的表、null值漏填、历史读取签名不符、旧原生夹具未剔除新表。原日志中失败不会改写成通过。
- 独立探针复现并修复：历史档案读取未对照行内会话/版本；找回回执未核对所指接待摘要；可预知派生请求键可能连到既有接待。修复后 3 个反例通过。
- 交叉复核另发现：仅改标题导致摘要误标原话；篡改 no-op 回执时间后仍接受过期接待修订。已修复并分别通过来源继承和时序反例。
- Spec 与 Standards 分开记录，各代理编写的自身模块不作为独立审阅范围；由其他作者交叉覆盖。非稳定源码窗口保留，不能作为最终结论。

## 复现与边界

使用项目 `.venv/Scripts/python.exe`。最终运行器为 [verify.py](verify.py) 与 [target_runner.py](target_runner.py)，在新的 `.local/pp-*` 合成目录执行完整 `tests` 和四项开发门，保存前后源码/测试摘要、命令、数量及退出码。目录中的探针原来在 `.local/profile-persistence-20261023/` 执行；脚本的相对位置按该目录解析。

WorkBuddy 本轮实测 `native_unavailable`、专用会话无活动端点，未派发，未把旧回执当成本轮结果。此片没有真实模型调用、自动提炼钩子、新档案侧栏、真实资料或 F: 法库改动、云部署、安装器更新。安装版仍为 0.4.1；不能把源码合成检查称为真实法律质量或整机性能验收。

下一片 CH-07C 将复用同一次已获准模型调用接结构化提案和固定钩子，再贯通档案面板；不得隐藏增加付费抽取调用。
