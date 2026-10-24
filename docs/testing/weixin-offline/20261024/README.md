# D1 官方微信协议离线预览证据（2026-10-24）

D1 已实现固定协议的离线预览与合成验证；真实微信尚未接通。本片不增加运行时网络入口、账号凭据或业务收件提交路径。实施范围见[计划](../../../plans/2026-10-24-weixin-offline-d1.md)，一手事实见[协议研究](../../../research/2026-10-24-weixin-protocol-d.md)。产品提交 `8c7db52` 已同步，远端 SHA/tree/5,009 项一致，见[同步回执](github-sync.md)。

## 实际实现

- 新增 `src/cn_contract/weixin_offline.py`；业务 DTO 仅在 `domain.py` 末尾追加 `WeixinOfflineScope`、`WeixinOfflinePlan`。复用当前数据库 principal、会话归属、案件 ACL、绑定与恢复隔离检查，不相信调用方 Actor 自述角色；本地 scope 不代表已经认证微信身份。
- 只预览精确 bot/peer 的 USER 私聊 TEXT 与 DOCX/PDF 文件待办。规范 uint64 字符串与 Python JSON 精确整数生成同一来源事件 ID，拒绝 bool/float/越界；同 ID 跨 bot/peer 隔离。上游 opaque cursor 与本地 task 整数 cursor 分开；未知、混合身份、未完成或不支持的消息拒绝整份 poll。
- 文件只形成 pending；AES key、CDN 参数/URL、context token 等能力数据只影响消息摘要，不进入返回内容。未得到受控明文字节与完整解析前不能冻结材料。256 KiB/100 条/20 items 等均为本地限制，不能当作平台限额。
- `preview_response` 不调用 `receive_batch`、不写任务、不推进或确认任一游标。现有鉴权拒绝可能追加不可覆盖审计，因此不宣称绝对数据库零写入。

上游固定为腾讯 `874637a0dbc24050f72d1385add4fc6170a2d726`（包 2.4.10，MIT），未引入其运行依赖。FINISH 与 `is_completed` 缺省/true 接纳、false 拒绝属于本项目保守策略；官方字段是 boolean，上游入站路径未见同样 gate。同 pin 官方源码和测试把 `ref_msg.svr_id` 与消息缓存 `message_id` 用作同范围可相等键，没有“不同 ID 空间”的证据，也未据此宣称服务端全局唯一保证。

## 最终实测与证据范围

原始回执保存在本机 `.local/weixin-offline-20261024/`。回读 `verification-summary.json`、四份 XML 及对应 `.exit.json`，按 `classname::name` 去重：**5 个测试文件、290 个唯一用例；失败/错误/跳过均为 0，四次命令均 exit 0**。XML 与摘要的四个 SHA256、两份产品源码 SHA256 均一致。此为相关回归，不是全仓通过。

下表命令统一以前缀 `.venv/Scripts/python.exe -B -X utf8` 执行；XML 路径均在上述本机证据目录。耗时为 XML 中 pytest 测试耗时，区别于进程总耗时。

| 实际命令后缀 | XML | 通过数 | pytest 耗时 |
| --- | --- | ---: | ---: |
| `-m pytest -q tests/unit/test_weixin_offline_protocol.py tests/integration/test_weixin_offline.py --junitxml=.local/weixin-offline-20261024/final-protocol-renamed.xml` | `final-protocol-renamed.xml` | 135（单元 123＋集成 12） | 10.461s |
| `-m pytest -q tests/unit/test_domain.py --junitxml=.local/weixin-offline-20261024/regression-domain.xml` | `regression-domain.xml` | 111 | 0.580s |
| `-m pytest -q tests/integration/test_task_drafts.py --junitxml=.local/weixin-offline-20261024/regression-core.xml` | `regression-core.xml` | 32 | 25.152s |
| `-m pytest -q tests/integration/test_task_draft_routes.py --junitxml=.local/weixin-offline-20261024/regression-routes.xml` | `regression-routes.xml` | 12 | 24.091s |

集成实际验证当前 owner/session、真实 principal 角色、ACL 撤权、绑定与材料修订、task cursor、归档和恢复 fence；预览的业务表/游标快照不变，socket 连接负控制未触发。两种文字/文件顺序的**测试代码**显式把合成预览 batch 送入原 synthetic Inbox，验证重放幂等、pending 阻断 freeze、无执行或模型 run；产品适配器没有这个提交路径。

四个开发门均 exit 0；原始 `gates-initial.json` 是五个结果的数组，首项是下节所述初次合跑 collection error，不能把数组整体称为“五项全绿”。

| 同一 Python 前缀后的命令 | 实际结果 |
| --- | --- |
| `-m cn_contract.cli schema --check` | exit 0，schema check ok |
| `scripts/verify_defaults.py` | exit 0，默认配置摘要一致 |
| `scripts/verify_sources.py --mode development` | exit 0，13 来源；保留 13 项 NOT_PRODUCTION_APPROVED 警告 |
| `scripts/verify_runtime_dependencies.py --mode development` | exit 0，55 runtime＋1 build；native_build_verified=false，network_calls=0 |

## 开发失败与独立复核

`backend-notes.md` 保留有效行为 RED→GREEN：缺模块时 89 failed/0 errors；numeric uint64、非零 ret/errcode 优先、boolean/metadata 类型分别新增反例并修复；Windows basename 与明确成功而缺省 msgs 的补充 RED 为 10 failed/113 passed，最终后端单元 123 passed。中间 89、95、97、111、123 不相加，也不替代最终合跑回执。

另有两类开发过程失败不算产品行为 RED：集成初次缺模块造成 setup error；旧测试假设助理可拥有律师会话，被现有 guard 403 拒绝，改为验证伪造 Actor 角色在 binding lookup 前被拒绝后，12 集成最终通过。初次 unit/integration 同名 `test_weixin_offline.py` 合跑触发 import mismatch、exit 1；单元文件改名为 `test_weixin_offline_protocol.py` 后，135 合跑通过，原日志保留。后端交接中的旧文件名仅对应改名前账本。

WorkBuddy 任务 `wb-bg-14372a3a19ed`（session `ee7479c7-61a8-43e9-ac27-61553955cd4f`）由根代理核实实际模型 `kimi-k3-2` 并核对六条建议；关于 svr_id 不同空间的猜测经官方源码反证后未盲采纳。独立 reviewer 的 P3 Windows 文件名问题已修并留行为反例，最终按下列冻结源码摘要定点复核无遗留发现。该审阅没有重跑全部测试或访问真实账号。

## 最终源码与未验事项

| 文件 | SHA256 |
| --- | --- |
| `src/cn_contract/weixin_offline.py` | `d76e22e9f0780284134a441d9dc79f8794269632855ac76b217f25f41527022a` |
| `src/cn_contract/domain.py` | `34fa75741893a431504bc964ed9aef5ab4cb3e52c602f4e33dae280629f409a6` |

NOT_RUN／未实施：真实微信账号与认证；HTTP/IPC 入口；真实微信身份绑定持久化；账号级 durable Inbox/上游 checkpoint 与崩溃重放；媒体下载解密；发送/Outbox/送达回执；E 真实模型；安装包；全仓、Node 与浏览器回归。安装版仍 0.4.1。D2 仍须让每个上游事件具有持久 accepted/blocked 结果后再确认账号游标，并处理撤权及备份兼容。既有原生长进程崩溃与 WIN-PATH-02 未因此关闭。
