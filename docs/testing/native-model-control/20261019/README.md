# CH-04F 原生模型控制与单次授权：本机证据

2026-10-19，基线 `0ff926d`，沿 `codex/contract-review-v2`。本片完成可信主进程到实际桌面后端的私有控制通道及单次文本授权；没有把配置/授权入口开放给日常页面。本机 WorkBuddy 检测为 busy/unknown，未派发，独立复核由子智能体执行。

## 实现与边界

- 复用已有子进程 stdin/stdout，新增独立 `desktop/model-control.cjs`、`desktop_control.py` 和 `assistant/native_model_control.py`；现有 main/preload/UI 未扩写，无新依赖、无授权 HTTP 端点、无新队列或数据库迁移。
- 可信代码通过原生加密存储 `withSecret` 回调传递凭据，只返回固定状态；回调不向 renderer 返回密钥。配置成功有独立版本；授权绑定当前用户/会话、具体对话及完整 scope、草稿 revision、正文摘要和 request ID，最多一次调用。能力查询、入队及执行前后分别核对。
- 相同意图幂等但不续期，不增加费用上限；撤销或改配置不能恢复旧意图。费用账本、原文引用和待核候选沿用既有实现。重启初始为空注册表：历史 GET 可读，未重新授权的 POST 拒绝，不补发。
- 协议有 nonce、严格递增序号、一个在途命令和固定字段，UTF-8 字节有界；错误不反射正文/凭据。坏帧或超时终止自有子进程。引导和控制共用无缓冲二进制输入，输出固定 LF；正常 EOF 与维护完成均保留可验证退出。

## 最终验证

| 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| 最终关联 Python 回归 | **406/406 PASS**，0失败/错误/跳过，exit 0；JUnit 223.387 秒；收集清单逐项一致，483 份输入摘要不变 | `regression-summary.json`、`regression.xml`、`regression.log`、源码前后摘要 |
| 桌面 Node 回归 | **73/73 PASS**，exit 0；新增38项包含其中，既有35项继续通过 | `node-current-final.log`、`node-current-final.exit` |
| 独立复核 | 独立 Python 11项、实际 Node→Python 管道2项通过；维护修复后另复核2项正式测试，不能重复相加 | `review-final.md`、`review-*.log/xml`、16份最终产品摘要 |
| 实际 Windows Electron | **6组通过**；真实 safeStorage→私有管道→实际 desktop_entry→随机回环模拟供应商；1次POST、1个attempt/receipt/output；483份输入稳定 | `native-verification.json`、`native-current.exit`、源码前后摘要 |
| 新冻结生产后端 | **4组通过**；默认空配置、登录、私有配置/授权、先关闭授权再拒绝POST、正常EOF、SQLite完整性与零模型记录 | `frozen-backend-smoke.json`、`frozen-smoke.exit` |
| 既有维护适配器→新冻结EXE | **2组通过**；实际加密备份与恢复，两个进程均exit 0，恢复副本quarantined | `frozen-maintenance.json`、`frozen-maintenance-final.exit` |
| 开发检查 | 默认、来源、依赖、schema四项exit 0；来源仍有非生产批准提示 | 对应日志及退出码 |
| 构建来源 | 212份构建输入前后完全一致；控制台保留4条hidden-import警告，完整模块警告另存 | `build-source-*.json`、`frozen-build.log`、`pyinstaller-warnings.txt` |

上述数量不是全项目测试总数，未重跑历史2,350项。独立复核、目标回归和中间轮结果不与最终406相加。没有实测包体/RSS下降；单次启动观察不等于性能基准。本轮没有重测新安装器或改已安装0.4.1。

Electron实测用的是跟随实际入口的测试专用 provider 工厂，只允许随机本机回环；生产配置没有接收方URL参数。冻结生产EXE在授权之后先disable，再测试POST拒绝，模型记录均为0；它没有向官方供应商发请求。所有资料、账号、密钥标记及返回内容都是独立合成数据，**真实模型调用0**。

## 失败与修复记录

1. 首次缺失模块/方法的RED用于确认新能力尚不存在。Python超长自动参数ID一度超过Windows环境变量限额，属测试工具错误；改短ID后执行，原日志保留本机，不计产品故障或通过。服务测试一度试图修改不可变run ID，被既有约束正确拒绝；改为独立请求准备反例。
2. Node边界测试关闭了同块ready后坏帧过早宣告启动、UTF-8 BOM被隐去、stop后start悬挂、系统stdout/stderr错误未收敛等问题。另有一个测试fixture误用stdout.end模拟Windows管道关闭，单独标明为fixture修正。见 `node-verification.json`。
3. 独立复核发现中文控制帧超字节但无换行时不立即拒绝，以及另一对话/新composer仍误显示ready。均保留原RED、修复及同反例GREEN；入队原本已拒绝，未发现该提示问题导致越权发送。
4. 实际Windows默认stdout CRLF不能通过严格规范JSON行校验。`native-lf-red.*`先复现，再固定LF，真实父子进程验证通过。第一次Electron控制联调因此未通过。
5. Electron试验第二次模拟供应商漏填既有协议要求的object/created；第三次测试错误地期待重启空注册表还能重放POST。两处均是fixture/预期错误；修正为完整合成回复、重启GET查历史且POST拒绝。没有放松产品校验。
6. 提交前追加维护验收发现：发出complete并不代表进程成功结束。BufferedReader等待输入的daemon在解释器退出时触发锁错误，exit 3221225477。正式源进程先复现1个RED；改为自boot开始使用同一无缓冲FileIO，26目标通过，独立2项复核通过。随后重新冻结构建，实际Maintenance→EXE备份/恢复通过，并最终重新运行406关联测试。修复前405通过与旧冻结摘要仅是中间结果，`before-maintenance-*`明确保留。

## 重现与后续

正式测试在仓库中；本目录原始验证脚本、日志和命令来自 `.local/native-model-control-20261019`。要复现阶段脚本，应先复制到该独立目录运行，保持其工作目录约定；不要在资料库或真实工作区运行测试入口。`manifest.json`保留证据字节摘要，原数据库、qxbak、加密凭据文件和EXE均未加入Git。

下一片只需由独立原生协调模块接已有设置和明确发送确认，身份从所属窗口的真实登录状态获取，不能信任renderer自报权限。重新核验实际供应商模型与价格，继续区分保存凭据、配置和一次外发批准。之后按CH计划接Jev与自动档案，详见[接续契约](../../../plans/2026-10-19-native-model-control.md)。

非阻断后续项：当前内存意图记录保留旧lease/provider引用直到进程退出；失效授权不能执行，但未声称字符串可靠擦除。后续可保留fingerprint和失效标记、释放不再使用的provider，不能直接清空记录而让撤销的request ID复活。真实资料外发、云部署、未下载年份、商业法库和生产批准都未在本片完成。
