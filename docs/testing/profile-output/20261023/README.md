# CH-07C1：同次回答与档案提案协议

Windows源码，基线 `1a7072bb905568a24292a53f3f3133c7c9fbb4f6`，2026-10-23北京时间。仅独立合成文字、随机回环HTTP；当前桌面后端及其资料未操作。

## 已实现范围

新增明确的 `profile-text-v1` 请求与独立codec，同一个模型响应可返回回答和结构化档案提案，复用既有DeepSeek传输、严格JSON封套、用量处理和ProfilePatch纯合并。当前仅包含已保存的本次用户文字；身份、来源修订、作用域与摘要由服务器补齐，模型不提供。quote逐字按Unicode码点定位；金额采用十进制字符串、日期必须显式ISO时区。未知保留null，冲突并列待核，非空联系方式及已收到/已核对材料被拒。

新入口默认不发送；密钥读取前后及有效候选返回后复核。撤权丢弃候选，但保留received状态、请求ID和实际usage。没有第二次抽取调用、修复重发或新网络客户端。新codec懒导入，旧MainRequest/MainCandidate与三个既有生成入口保持原行为。

**本片没有启用应用自动建档。** 未增加registry许可、数据库表、HTTP路由、原生确认或保存钩子；没有用旧普通回答许可发送新协议。C2须同时闭合用途确认、完整字节绑定、版本化登记与历史验证、受信工作流投影选择、固定原子保存钩子和恢复；C3接档案面板及本地联系方式处理。纯codec不能证明当前权限或资料客观真实。

## 最终实测

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| 关联Python（21文件） | 577通过，0失败/错误/跳过，exit0；186.14秒 | [清单](target-nodeids.txt)、[日志](target.log)、[XML](target.xml) |
| 固定输入 | 535份src/config/tests/scripts/锁定输入运行前后相同 | [命令、退出码及摘要](target-verification.json) |
| 四开发门 | schema、默认开关、开发来源、运行依赖均exit0 | [1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |
| 旧协议兼容 | 324个旧DTO类AST未变；旧builder/decoder/生成方法AST未变；4组wire与20组响应逐字相同 | [对照](compat.json)、[脚本](compat.py) |
| 冷进程导入 | main导入不加载profile_codec、httpx2或duckdb | [同一对照报告](compat.json) |
| 独立Spec/Standards | 修复后Spec13组、Standards8+4项通过，退出均0；原P2/P3关闭 | [独审与处理](review-summary.md) |
| WorkBuddy | 本轮状态native_unavailable，没有活动端点，未派发 | [实际状态摘要](workbuddy-status.json) |

最终关联数含新增76项；不是全项目全套，独审及早期测试不累加。Windows回环HTTP实测证明单次POST同时返回回答与提案、默认零请求、撤权保留用量、未知不重试、取消向上传递。未据此认定真实模型提炼质量或事实与引文的法律相关性。

## 失败与修复轨迹

- 原始RED为codec未实现：1失败。[原始日志](red.log)。首轮实现后仅金额断言错误（Decimal规范化为科学记数法），改为精确数值比较；独立.NET计算的引文SHA已固定。原先未验证的SHA文字在首次GREEN前更正，不作为产品缺陷。
- 边界扩展51通过/2失败：待补材料误写为missing而非既有needed、provider入口尚缺；实现后53通过。网络测试首轮66通过/1失败源于夹具使用小数超时而配置只接受整数；改为1秒超时后67通过。
- 修复前关联568通过、535输入稳定、四门通过，保留在[原批次](before-review-fix/target-verification.json)。独审随后发现数字日期隐式epoch及金额非字符串问题，这说明该批次没有覆盖这些边界。
- 新增正式负例时5失败/11通过（45未选）：其中4项复现两类缺陷，另1项是正例quote末尾位置写29而实际30的夹具错误。仅收紧新wire类型和日期校验、修正该位置；本片76通过。原始[失败](review-red.xml)与[修复结果](review-green.xml)均保留；最终关联回归已含这些新例。

## 继续工作

按[C1执行合同](../../../plans/2026-10-23-profile-output.md)推进C2，源消息修订须从保存的消息核对，不能拿后来的会话版本代替。勿从回答正文截取JSON、暗增付费提炼或让模型决定权限/投影目的。

既有WIN-PATH-02长路径恢复发布WinError5继续开放，本片未改备份或重复上轮全套；上轮3816通过/3失败及补验事实不变。安装版仍0.4.1，没有重建安装器/GUI、没有本片整体包体/RSS/启动收益实测。真实材料、F盘库、未下载年份及阿里云均无变化。GitHub结果以单独同步回执为准。

证据字节摘要见[evidence-manifest.json](evidence-manifest.json)。复现使用项目解释器、目标清单和全新短D盘临时目录；不可覆盖本轮原证据。
