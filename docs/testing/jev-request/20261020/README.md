# CH-05D1：逐请求许可与主任务内 Jev 辅助

2026-10-20，基线 `27f224c6568fcfdd4c16f49c6533cf9741dbb464`。本片完成后端与桌面私有管道接线，**日常发送确认界面留 CH-05D2**。真实 TypeSafe 账户许可、价目来源和可接受预算尚未落实；未启用真实模型、替换安装版或发送真实材料。

## 实现

- 后端从当前草稿、版本和来源构造独立单次许可，精确绑定保存后的完整请求；DeepSeek 许可不授予 Jev 权限。
- 同一个主任务事务保存两类预留，提交成功才执行；先运行可选辅助，再使用原主模型授权。缺配置、许可、预算或辅助失败可跳过；存储错误、取消和主权限失效不会被当成正常降级。
- 当前辅助只有一个授权槽。持久 `reserved/sending` 未收尾时，即使过期、撤权或重配也不能由新许可覆盖。无未收尾辅助且原许可过期可以释放槽，旧 Main 不会事后补建辅助。
- 沿用现有运行时、账本与队列；增加固定 `authorize_judge/revoke_judge` 私有操作及独立能力声明。未新增 HTTP 授权入口、renderer 授权 IPC、数据库表、SDK 或队列。
- 授权发布返回固定身份并立即记录短墓碑，避免发布后到期使同意图再次获得新许可。独立审阅复现后修复，保留同一探针 RED→GREEN。

## 实际验证

| 组别 | 实际结果 | 证据 |
| --- | --- | --- |
| 桌面 Node 全部测试文件 | 201 passed，exit 0 | [日志](parent/node-final.log)；命令 `node --test desktop/tests/*.test.cjs` |
| 可选阶段、账本、任务、HTTP 与启动 | 157 passed，exit 0；含36新增场景 | [命令与过程](stage/implementation.md)、[最终日志](stage/final-green.log) |
| 原生许可、配置及 runtime | 83 passed，exit 0；含52新许可场景 | [命令/输入/数量](native/publication-final.json)、[JUnit](native/publication-final.xml) |
| Python 私有协议 | 32 passed，exit 0 | [JUnit](parent/protocol-final.xml)；`pytest tests/unit/test_judge_authorization_protocol.py tests/unit/test_desktop_control_protocol.py -q` |
| schema/defaults/sources/runtime 开发检查 | 四项均 exit 0 | [汇总](summary.json)、parent/gate-1…4.json |
| Windows 源码进程 | 10组检查通过，两个独立 loopback 各1次 POST，顺序 Jev→Main | [报告](native-source/report.json)、[命令和285输入摘要](parent/native-source.json) |
| Windows 新冻结后端 | 7组控制检查通过，双授权→撤权并停用→生成拒绝，EOF/重启不恢复授权 | [报告](native-frozen/report.json)、[命令和输入](parent/native-frozen.json) |
| 独立 Spec / Standards | 无未解决发现；1项 P2 修复且独立复验 | [Spec](spec-review.md)、[Standards](standards-review.md)、[RED](standards-expiry-red.log)、[GREEN](standards-expiry-green.log) |

这些是分组目标回归，不是单次全套；较早 RED/中间回归不相加。157项执行在最后“grant 返回身份”窄修前，该修正由83项及最终源码完整链验证，阶段文件摘要未变。未重跑历史 CH-05B 的703项。

源码使用实际 Electron safeStorage、父子私有管道、FastAPI HTTP、原生授权和两个独立合成供应商。相同 run 下消息、两类 attempts/receipts、主候选与辅助建议各1条，原文与 codec 摘要一致。未知辅助费用保留 `.02` 合成预留，建议仍是内部待核验；这个值不是 TypeSafe 报价或收费上限。重放与重启不重发，独立凭据及会话 token 未进入检查到的 ACK/日志/数据库。

冻结程序不注入 loopback。该验收只证明私有控制、撤权并停用后的拒发与重启空授权，**不能称冻结模型执行通过或单独撤权条件已经实测**。两个模式各启动后端2次；使用同一285个仓库输入，执行前后及构建摘要一致。这不是第三方依赖全闭包证明。

源码子进程 httpx/httpx2 send tripwire 观察到 Main=1/Jev=1、其他=0，重启均0。冻结未装网络计数器；不声称全进程外网审计。driver 无 renderer，IPC隔离由独立固定入口/导航测试覆盖，不能把 HTTP拒绝当作实际 renderer IPC验收。

## 构建与仍待工作

新后端547文件、96,267,372字节，比 CH-05C 增9,426字节；EXE SHA256 `564a347488b4930f5928851c44571e2e8ecaa5f1ebefdbe2b195654a07271f07`。这是未压缩后端目录，未重建安装器、测受控冷启动或总体内存。[构建观察](build-observation.json)

CH-05D2继续复用原生确认窗，独立展示收件方、用途、具体输入和预算语义，辅助默认未选；真实费用条件不明时保持关闭。CH-06业务技能编排、自动档案、持衡统一接入等仍按TODO推进。安装版0.4.1、本地真实法库、未下载年份与阿里云状态不变。

本轮两次 WorkBuddy 状态均为 busy/unknown，未派发任务；独立审查来自子智能体。证据只白名单复制合成工程日志、摘要和报告，数据库、凭据密文、安装产物与本机缓存留本机；[manifest](manifest.json)覆盖本目录除manifest自身的字节。
