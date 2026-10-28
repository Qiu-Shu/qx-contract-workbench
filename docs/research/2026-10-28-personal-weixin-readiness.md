# 律师本人个人微信接入：现成能力、实际缺口与扫码条件

核验日期：2026-10-28，公开源码读取约 08:45–08:55 UTC。工作目录：`D:/Documents/ChatGPT/律所项目`。本次是研究，不是接入完成；只新增此报告，未安装或执行上游项目、申请二维码、登录微信、发送消息、上传材料、修改产品、提交或推送。研究采用 GitHub 连接器读取固定提交；没有用企业微信演示替代个人微信。

范围依据：用户本轮明确首版为“律师本人个人微信”，允许针对缺口复用 GitHub 项目；所给《最小可用产品收敛与改造实施方案》第 6、7 节要求先验证收文字、取附件、回结果，复用同一任务和材料，返回当前已绑定会话，不再建另一套业务系统。旧协议细节复用 [2026-10-24 研究](2026-10-24-weixin-protocol-d.md)，本报告仅补当前版本、候选选择与落地差距。

## 结论

**个人微信技术路径已经存在，当前产品尚未接通。** Tencent 官方插件提供扫码授权、文字长轮询、文件下载解密、文字及文件回复；可以据此补工作台的薄适配层。现有项目已有相当完整的离线收件、固定会话归属、去重、游标事务、任务归集、附件关联，值得直接复用。真正缺的不是更多待收件页面，而是真实账号身份绑定、实际 HTTP 收件、受控附件下载、会话回复凭据和发送记录。[官方协议][o-protocol]、[本地协议转换](../../src/cn_contract/weixin_offline.py)、[本地收件事务](../../src/cn_contract/weixin_inbox/ingress.py)

**不需要先申请企业微信机器人或重建 OpenClaw 业务系统。** 此处证实的是个人微信中与已连接 bot 的私聊通道；没有证据证明能接管律师全部好友聊天、读取历史聊天或代律师给任意联系人发送消息。首版采用律师本人扫码后向该 bot 发指令，成果按同一 bot＋同一 peer 回传即可。官方声明私聊能力，鉴权采用配对、群聊禁用；这恰好符合本轮本人使用范围。[官方 README][o-readme]、[鉴权源码][o-authz]、[既有固定 pin 能力核验](2026-10-24-weixin-protocol-d.md)

**建议以腾讯固定协议为准，局部复用 CoreSpeed 的 Python 协议/解密实现作为候选，不整套引入其 Bot、存储或轮询器。** CoreSpeed 的 SDK 本体较贴合现有 Python 后端，具有 MIT 正文；但源码存在与工作台约束不相容的部分，必须适配。Photon、Epiral 两个更小候选无法减少本次关键差距，暂不采用。以下都是源码层判断，不是实际账号联调结果。

## 当前固定来源与许可

| 来源 | 本次重新取得的 main HEAD | 核验结论 |
| --- | --- | --- |
| Tencent/openclaw-weixin | `874637a0dbc24050f72d1385add4fc6170a2d726`，提交 2026-10-13 03:31:48 UTC，包 2.4.10 | 与 10-24 已核验 pin 相同。LICENSE 正文与 package 声明 MIT；继续沿用原研究，不重新做一套协议。[提交][o-commit]、[许可][o-license]、[包][o-package] |
| corespeed-io/wechatbot | `6914de4e4cae966b1a3f4c6531711c9dffd84fee`，提交 2026-07-02 12:08:44 UTC，Python 包 0.3.0 | MIT 正文存在，Python >=3.9，依赖 aiohttp>=3.9、cryptography>=42.0。可作为薄层实现参考；不是官方 SDK，不采纳 README 的“生产就绪”作为验收结论。[提交][c-commit]、[许可][c-license]、[包][c-package] |
| photon-hq/wechat-ilink-client | `b3e59440e90da344667b5d38af122fdd77a8d2a3`，提交 2026-03-22 05:51:37 UTC，包 0.1.0 | README/package 标 MIT，固定树未见 LICENSE 正文，直接读取 LICENSE 返回 404。独立 TypeScript 库仍需修旧登录、ID 精度及许可材料，不适合当前直接引入。[提交][p-commit]、[树][p-tree]、[包][p-package] |
| epiral/weixin-bot | `da0e1db9a2d23a588b1cbed2cc73092887f51049`，提交 2026-03-22 06:05:56 UTC | README/Python package 标 MIT，固定树未见 LICENSE 正文，LICENSE 首次网络错误后重查 404。有文本收发，但未提供本次所需的文件下载解密实现。[提交][e-commit]、[树][e-tree]、[Python 客户端][e-client] |

提交时间用于说明本次可见维护状态，不推断项目停更或未来支持承诺。MIT 版权与许可通知需要随实际复制部分保留；本次未复制源码或升级 `sources/upstream.lock.json` 的批准状态。软件许可不等于服务端账号可用性证明。

官方 README 此 pin 有一处过时信息：写运行时下限 `2026.3.22`，但实际 `src/compat.ts:11` 与 package peer dependency 均为 `2026.5.12`；整装插件应按源码下限处理。Node 下限为 `22.13.0`。这些是运行完整官方插件的要求，不是用 Python 实现 HTTP 协议必须安装 OpenClaw 的理由。[兼容检查][o-compat]、[包][o-package]

## 三项通道能力的证据

| 用户需要 | 官方固定源码已具备 | 当前工作台实际情况 |
| --- | --- | --- |
| 收文字指令 | `api.ts` 的 `getUpdates` POST `/ilink/bot/getupdates`，携带 token、opaque cursor；文字位于 `item_list[].text_item.text` | `weixin_offline._event` 已保真转换消息 ID、精确核 bot/peer、解析文字；但输入是调用方提供的 bytes，没有真实网络拉取入口。[官方 API][o-api]、[本地转换](../../src/cn_contract/weixin_offline.py) |
| 取得 DOCX/PDF | FILE 项带 `file_name` 与 media 引用；优先 `full_url`，否则 CDN query URL；AES-128-ECB＋PKCS7 解密，兼容两类 base64 key 编码 | `_file` 仅核文件名/声明长度并产出 `status='pending'`，没有下载/解密；`full_url`、query、key 经过字段校验后不进入任务 payload。[官方媒体协议][o-protocol-media]、[解密][o-decrypt]、[本地 `_file`](../../src/cn_contract/weixin_offline.py) |
| 回当前会话结果 | `sendMessageWeixin` 指定 `to_user_id` 和 `context_token`；`sendFileMessageWeixin` 组 FILE 消息，上传另走加密 CDN 流程 | 无 `sendmessage` 调用、微信 Outbox 或受控回复 token 存储；当前 `_event` 不把 `context_token` 带到持久任务。不能只把现有结果直接传给一个 sender 就宣称完整接通。[官方发送][o-send]、[上下文存储][o-inbound] |

官方回复 `context_token` 是会话关联数据，不能替代本地案件权限、身份绑定或决定收件人。官方 helper 缺 token 时仍尝试发送，协议文档明确不能据此推断服务器接受；工作台应在缺失/不匹配时停止并提示重新建立当前会话。发送响应及客户端 ID 不证明送达、已读或重复发送幂等；超时结果未知时不能盲目重发。[官方协议发送说明][o-protocol-send]、[既有错误/重试核验](2026-10-24-weixin-protocol-d.md)

## 必须由本人完成的条件与可先完成的代码

1. **本人用手机微信扫码并确认授权。** 官方登录首先 POST `get_bot_qrcode?bot_type=3`；之后轮询二维码状态。`need_verifycode` 时需要输入手机微信显示的配对数字，过期需重取；`confirmed` 后才返回 bot token、bot ID、扫码用户 ID 与 API base URL。不能在开发中虚构这些值，也不能由桌面登录推导微信身份。[登录源码][o-login]
2. **服务端接受该实际账号的连接。** 公开源码没有给出所有账号/地区/客户端版本的准入保证，也没有在此流程要求企业微信企业 ID、bot secret、公众号或付费 API 账号。是否出现额外服务条件或拒绝，由本人实际扫码时的界面/服务端结果确认；不能把尚未核实的账号门槛扩写为开发阻断，也不能预先保证所有个人账号可用。[官方 README][o-readme]、[登录状态][o-login]
3. **本机运行并能访问微信 API/CDN。** 长轮询为出站 HTTP；此接法无需先搭公网 webhook 或全天候云服务器。电脑睡眠、关机或程序退出期间无法承诺继续处理，这是本机执行方式的条件。[官方 API][o-api]、用户方案第 6.3 节
4. **由本人发一条文字和一份虚构 DOCX/PDF 做真实通道验收。** 用扫码确认的 `ilink_user_id` 精确绑定已登录工作台律师；首次消息取得当前 peer/context，验证下载后的字节与原虚构文件一致，再将固定文本/文件成果回同一会话。账号 token、下载凭据不得写报告或普通日志。此项需要本人参与，但网络适配、数据契约、状态显示及虚构测试可以预先完成，不必等扫码才开始写代码。[登录][o-login]、[发送][o-send]

扫码仅完成远端身份和通道授权，不代表允许向第三方模型发送所有真实案件材料。模型处理沿工作台本轮 M2 的既定模型/范围/预算设置；不在微信入口另建逐次审批系统，也不允许微信正文改变供应商或费用边界。

## 本地可复用链与真正阻断

核验本地 HEAD：`154ec105e95fc647c394950cac75ecc47dac490a`。工作区存在其他未提交工作，本次仅读取相关源码；下列源文件核验时无自身未提交修改。调用关系先经现有 CodeGraph 索引定位，再读取图未覆盖的精确片段。

现有链为：`weixin_offline._event` → `ingress._record_poll`（收件描述与微信游标同事务）→ `generation_dispatch._dispatch` → `dispatch._deliver` → `task_drafts.service.receive_batch` → 同一 conversation 的 TaskDraft/材料关联。不是从零开始。[转换](../../src/cn_contract/weixin_offline.py)、[收件](../../src/cn_contract/weixin_inbox/ingress.py)、[分发](../../src/cn_contract/weixin_inbox/generation_dispatch.py)、[任务服务](../../src/cn_contract/task_drafts/service.py)

| 可复用部分 | 精确缺口与最小补法（建议，未实施） |
| --- | --- |
| 消息 ID、bot/peer 校验、同范围引用 | `weixin_offline.py:61–87,142–198` 已处理，继续复用。身份真实性必须由可信拉取连接和扫码结果提供，不能将 JSON 内字段当登录证明。 |
| 持久收件与游标 CAS | `ingress.py:184–233` 同事务存回执、描述及游标；`generation_ingress.py:80–92` 固定历史目标。以此为落盘边界，网络成功不等于业务提交成功，不能采用 SDK 自己先前进游标的循环。 |
| 同一会话的任务归集、去重、附件关联 | `task_drafts/service.py:290–363` 已有归属/重复/CAS；`TaskMediaResolutionInput` 已有 ready replacement。下载验证后接既有附件上传解析与 resolution，保留原始 pending 描述，不另建微信材料库。 |
| 律师/工作区/会话权限 | `accounts.py:28–43,82–123` 已有 current principal、owner、workspace、目标 ACL 校验。补远端扫码凭据与本地 owner 的可信绑定，不能用消息文本指定另一律师/案件。 |
| 现有合成通道数据结构 | `domain.py:4443` 的 `channel`、`:4681` 的 account `mode` 都只允许 `synthetic`；对应 `task_drafts/schema.py:9`、`weixin_inbox/schema.py:9` 也有 CHECK。真实接入需要小范围来源类型/迁移设计，不能只把常量或 UI 文案改成“已连接”。DTO 继续集中在 domain.py，旧合成记录保留原义。 |
| 文件下载引用与回复 context | 现有 `TaskInboxEventInput` 输出不带 media 下载凭据、context；poll 存摘要和净化 payload，不能从已保存摘要恢复 token。需要本地受保护的通道凭据/消息传输元数据，与账号、peer、消息、绑定版本精确关联；该私密通道数据不混入模型正文、导出或普通日志。 |
| 真实网络生命周期 | 源码搜索没有微信 token 存取、二维码、getupdates、sendmessage 实现。需要一个可停止的本机账号 worker：登录状态、单账号单拉取、收件事务提交、过期停用、重连/扫码提示。群聊、客户直接接入保持范围外。 |
| 结果回送 | 需要固定同一已绑定会话的发送记录，发送前复核当前绑定和任务权限，保存准备/已提交/结果未知/失败状态；持久固定 client_id 只是本地追踪，不宣称平台去重。不得让模型选择联系人。 |
| 业务实际执行 | `task_drafts/bridge.py:84–88,126–149` 仍按 synthetic case 和 `synthetic_task=True` 运行。真实消息不能冒充 synthetic 绕进旧桥接。应接正在实施的统一聊天业务调度/模型入口，复用 task/material identity；“能回固定文本”与“真实合同模型闭环”分开验收。 |

`web/weixin_authorization.py` 现在暴露本机合成授权/代际/待收件/分发接口；它没有扫码入口或远端身份认证。继续扩展这些管理页面无法补上真实收发。[当前 HTTP 层](../../src/cn_contract/web/weixin_authorization.py)、[合成 scope 查询](../../src/cn_contract/weixin_inbox/conversation.py)

## 轻量组件取舍：只补缺口

### CoreSpeed：保留为首选局部参考

Python `ILinkApi` 已有新版 POST QR、`verify_code`、getupdates、sendmessage；`auth.py` 校验 token/bot/user 三者齐全，处理 `need_verifycode`、`binded_redirect`、IDC redirect；`crypto.py` 有 AES-128-ECB/PKCS7 与 key 解码。这些可减少协议适配重复工作；其用途是替代尚不存在的传输/解密薄层，不替代工作台任务、存储或身份权限。[协议][c-protocol]、[登录][c-auth]、[解密][c-crypto]

直接整装存在以下源码级差距：

- `client.py:276–285` 先推进内存 `_cursor` 再调用处理器；`:592–599` 捕获处理器错误只报告；不符合工作台“描述持久保存后才提交游标”的事务语义。SDK 的内存 context/cursor 也不能替代本地持久状态。[客户端][c-client]
- `_cdn_download:434–450` 只拼 CDN query URL，忽略 DTO 已有 `full_url`，并一次 `resp.read()` 读完整密文；没有工作台所需的下载中限额/受控 URL 与重定向处理。官方反而优先 full_url，需按官方合同适配，不能照抄此 downloader。[客户端][c-client]、[官方媒体协议][o-protocol-media]
- `auth.py:41–52` 直接把 token 写 JSON 再 chmod；不能因此宣称 Windows 下已加密或完成工作台账户隔离。应复用本项目桌面秘密存储边界。默认打印、错误正文和自动重登录也需由工作台控制。[登录][c-auth]
- README 的跨语言能力表不等于 Python 每项能力均实现；应依本次读取的 Python 函数逐项验收。现有项目已使用 `cryptography` 的备份加密代码，但这不等于已有 iLink ECB 解密。引入前核对本项目实际运行依赖锁，避免为了两个 HTTP 方法平行引入整套 aiohttp 栈。[包][c-package]、[本地依赖](../../pyproject.toml)

### Photon：不采用当前 pin

它确实是独立 TypeScript API/CDN 库，具有收文件/发文件 API，且没有 OpenClaw 框架依赖。但固定源码的 `message_id?: number` 与 `JSON.parse` 会把大 uint64 ID 置于 JS 精度风险；QR 仍为 GET，状态类型只含 wait/scaned/confirmed/expired，没有本次官方已支持的配对码/IDC/已绑定状态。再加未见许可正文，需要修的基础问题比直接对齐官方协议更多；还会增加 Python↔Node 边界。[说明][p-readme]、[API][p-api]、[类型][p-types]、[登录][p-auth]、[树][p-tree]

### Epiral：不采用当前 pin

Python client 支持文本 reply/send，但把 file 项提取为文件名文本；固定目录没有 CDN 下载/解密模块。它能帮助验证文字原型，不能补“取得真实附件”这一首版核心缺口。许可正文仍待补，维护提交也早于本次官方扫码流程；不因包名简洁就增加第二个 SDK。[客户端][e-client]、[树][e-tree]

## 最小交付顺序与验收状态

1. **先做薄适配与虚构通道夹具。** 固定腾讯 pin 和选定复用文件/许可，定义真实连接身份；添加受保护传输元数据、bounded download 和固定会话发送记录。复用既有收件事务/材料服务/统一调度。此步无需用户扫码，不新增业务台或审批中心。
2. **再让本人扫码完成一个最小真实通道闭环。** 同一已绑定律师发文字＋一份虚构 DOCX/PDF，工作台取得原文件并核实摘要，回固定文本与一份生成的虚构成果文件。记录 API 返回和用户实际收到，区别“提交成功”和“送达验证”；不把 SDK echo 当工作台业务完成。
3. **最后接统一业务成果。** 复用 M2 的真实模型、任务和成果身份，验证桌面看到同一文件/同一任务、重启后历史可见、重复收件不重复执行、发送未知不盲重试、撤销/换绑不串案。不要把旧 synthetic bridge 的通过记录计为真实微信模型验收。

当前状态：公开协议源码核验完成；本地差距定位完成；真实扫码、收文字、下载解密、微信回送、真实业务端到端均 **NOT_RUN**。本次没有运行上游测试或项目测试；文档读取/源码定位不是功能 PASS。

## 核验记录与来源边界

- GitHub 连接器成功读取 4 个仓库固定提交、README、包声明、相关源码与候选目录；未安装依赖或执行 README 中命令。首轮候选 LICENSE 网络错误按工具错误记录，随后 404 与固定树共同支持“该 pin 未见正文”，不是把一次网络失败当无许可证。
- 本地 `git rev-parse HEAD`、最终精确源码搜索与 `Get-FileHash` 退出 0。早期几次带文件系统通配路径的 `rg` 在 Windows 返回不存在/路径错误，已改为目录＋`-g` 或精确文件重查；失败调用不作为缺失证明。
- 两次 CodeGraph 查询覆盖 `weixin_offline`、accounts/ingress 以及 generation ingress/dispatch、task service/web 关系；原文未覆盖处用精确文件读取。实际未新增产品代码、配置、依赖、网络凭据或状态。
- Obsidian/TencentDB 检索用于恢复 D 阶段背景，实际结论依当前源码和固定一手来源；记忆里的历史完成数字未当成本轮验证。
- 文档静态核对使用本项目 Python：31 个引用定义全部可解析、本地相对链接目标均存在、无行末空白，退出 0；`git diff --check -- docs/research/2026-10-28-personal-weixin-readiness.md` 退出 0（该文件为新增未跟踪，正文另由上述直接读取核对）。未运行任何功能测试。

本次核验的关键本地文件 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `src/cn_contract/weixin_offline.py` | `d76e22e9f0780284134a441d9dc79f8794269632855ac76b217f25f41527022a` |
| `src/cn_contract/weixin_inbox/accounts.py` | `0ab2584d848a7af293970594d157743a5028b63a040481596d0f0dac51d85f13` |
| `src/cn_contract/weixin_inbox/ingress.py` | `4faebd87c657dd5d4ab6a26eac77fa3f78af2ef3a0163271aeb5fc6dd736b093` |
| `src/cn_contract/weixin_inbox/generation_ingress.py` | `094c74629d66ce844f8ee5b227dcd5af67a09ea0c8f28241c55112a496934438` |
| `src/cn_contract/weixin_inbox/generation_dispatch.py` | `4f060c43dbedb62460f1d99564d8b1cbe3af06a37cb9fc403252a86ac1c703a6` |
| `src/cn_contract/task_drafts/service.py` | `377c70eaf877506ef9df72200ae065dbabe73da66c122ec54315b3cb3f5b2c2e` |
| `src/cn_contract/domain.py` | `66136add66127c79ac1be89465cdce9c04c9d269a139a8259363d179c8e36a08` |

[o-commit]: https://github.com/Tencent/openclaw-weixin/commit/874637a0dbc24050f72d1385add4fc6170a2d726
[o-license]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/LICENSE
[o-package]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/package.json
[o-readme]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/README.md
[o-compat]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/compat.ts#L11
[o-protocol]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/docs/protocol.md
[o-protocol-send]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/docs/protocol.md#L208-L248
[o-protocol-media]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/docs/protocol.md#L434-L476
[o-login]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/auth/login-qr.ts
[o-authz]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/authorization.ts
[o-api]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/api.ts
[o-decrypt]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/cdn/pic-decrypt.ts
[o-send]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/send.ts
[o-inbound]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/inbound.ts#L17-L20
[c-commit]: https://github.com/corespeed-io/wechatbot/commit/6914de4e4cae966b1a3f4c6531711c9dffd84fee
[c-license]: https://github.com/corespeed-io/wechatbot/blob/6914de4e4cae966b1a3f4c6531711c9dffd84fee/LICENSE
[c-package]: https://github.com/corespeed-io/wechatbot/blob/6914de4e4cae966b1a3f4c6531711c9dffd84fee/python/pyproject.toml
[c-protocol]: https://github.com/corespeed-io/wechatbot/blob/6914de4e4cae966b1a3f4c6531711c9dffd84fee/python/wechatbot/protocol.py
[c-auth]: https://github.com/corespeed-io/wechatbot/blob/6914de4e4cae966b1a3f4c6531711c9dffd84fee/python/wechatbot/auth.py
[c-crypto]: https://github.com/corespeed-io/wechatbot/blob/6914de4e4cae966b1a3f4c6531711c9dffd84fee/python/wechatbot/crypto.py
[c-client]: https://github.com/corespeed-io/wechatbot/blob/6914de4e4cae966b1a3f4c6531711c9dffd84fee/python/wechatbot/client.py
[p-commit]: https://github.com/photon-hq/wechat-ilink-client/commit/b3e59440e90da344667b5d38af122fdd77a8d2a3
[p-tree]: https://github.com/photon-hq/wechat-ilink-client/tree/b3e59440e90da344667b5d38af122fdd77a8d2a3
[p-readme]: https://github.com/photon-hq/wechat-ilink-client/blob/b3e59440e90da344667b5d38af122fdd77a8d2a3/README.md
[p-package]: https://github.com/photon-hq/wechat-ilink-client/blob/b3e59440e90da344667b5d38af122fdd77a8d2a3/package.json
[p-api]: https://github.com/photon-hq/wechat-ilink-client/blob/b3e59440e90da344667b5d38af122fdd77a8d2a3/src/api/client.ts
[p-types]: https://github.com/photon-hq/wechat-ilink-client/blob/b3e59440e90da344667b5d38af122fdd77a8d2a3/src/api/types.ts
[p-auth]: https://github.com/photon-hq/wechat-ilink-client/blob/b3e59440e90da344667b5d38af122fdd77a8d2a3/src/auth/qr-login.ts
[e-commit]: https://github.com/epiral/weixin-bot/commit/da0e1db9a2d23a588b1cbed2cc73092887f51049
[e-tree]: https://github.com/epiral/weixin-bot/tree/da0e1db9a2d23a588b1cbed2cc73092887f51049
[e-client]: https://github.com/epiral/weixin-bot/blob/da0e1db9a2d23a588b1cbed2cc73092887f51049/python/weixin_bot/client.py
