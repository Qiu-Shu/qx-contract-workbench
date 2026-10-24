# D 阶段微信协议核验（仅研究，2026-10-24）

核验时间：2026-10-24T12:17:55Z；工作目录：`D:/Documents/ChatGPT/律所项目`。本次只读取公开 GitHub API、固定提交源码及现有项目文件；未安装、执行上游代码、登录账号、发送消息或上传私人资料。以下“已核实”指固定版本客户端源码实际声明/行为，不等于服务端正式协议承诺或真实账号验收。

已先查本地 `docs`、`sources` 和项目记忆；本工作区未找到既有 openclaw-weixin / ilink / wecom-aibot 十二仓库研究正文，不能把“未找到”写成“已复核”。项目记忆指向既有 D 接入待办，未作为协议事实来源。当前 A—C 与真实通道的完成状态以 `docs/TASK_STATUS.md` 为准。

## 固定来源

| 来源 | 本次核实版本 | 许可与边界 |
| --- | --- | --- |
| Tencent/openclaw-weixin | `main` 当时 HEAD：`874637a0dbc24050f72d1385add4fc6170a2d726`；提交时间 `2026-10-13T03:31:48Z`；包 `@tencent-weixin/openclaw-weixin` `2.4.10` | `LICENSE` 正文及 package 均声明 MIT。GitHub 元数据当时为 `NOASSERTION`，不能据此声称无许可证。[提交][commit]、[许可][license]、[包][package] |
| WecomTeam/wecom-aibot-python-sdk | `master` 当时 HEAD：`6bcb59a9a636c566f4c6ea5268b228e3def1611a`；提交时间 `2026-03-20T07:18:36Z` | MIT；仅作不同企业微信通道的比较，不纳入本轮依赖。[提交][wecom-commit]、[许可][wecom-license] |

来源仅为研究核验，未因此升级为本项目 `production_approved`。MIT 软件许可不能代替账号资格、平台服务条件、真实材料数据政策或律师批准。

## 已核实：iLink 入站结构

下列名称来自 [types.ts][types] 和 [api.ts][api]；上游 TypeScript 接口字段多数可选，本项目接纳条件应另外验证。

| 对象 | 实际字段/行为 |
| --- | --- |
| 拉取 | POST `ilink/bot/getupdates`；请求含 `get_updates_buf` 和 `base_info`，无本地缓存时传空字符串。响应含 `ret`、`errcode`、`errmsg`、`msgs`、`get_updates_buf`、`longpolling_timeout_ms`。`sync_buf` 标记为弃用兼容。游标是服务端不透明上下文字符串，不能当整数加一。 |
| 消息身份/范围 | `message_id`、`from_user_id`、`to_user_id`、`client_id`、`session_id`、`group_id`、`seq`；另有创建/更新/删除时间、`message_type`、`message_state`、`item_list`、`context_token`、`run_id`。`seq` 的全局唯一性、排序或游标替代语义未被证明。 |
| ID 精度 | `message_id` 是 wire uint64，客户端按字符串保真；JSON 解析还特别保护 `msg_id`、`svr_id`，因为服务端可能返回数字。不能先经过 JS Number 再转字符串。 |
| 枚举 | `MessageType`: USER=1、BOT=2；`MessageState`: NEW=0、GENERATING=1、FINISH=2；`MessageItemType`: TEXT=1、IMAGE=2、VOICE=3、FILE=4、VIDEO=5，另有 NONE=0、工具项 11/12。 |
| 项目内容 | `item_list[].text_item.text`；文件为 `file_item`，其 `file_name`、`md5`、`len` 均可缺失，其中 `len` 声明为字符串。媒体引用为 `file_item.media`，不是普通业务附件 URL。 |
| 项目完成字段 | `MessageItem.is_completed?: boolean`（types.ts:179），不是整数 0/1；同对象还可含数值型 `type`、创建/更新时间，字符串 `msg_id` 及各类型内容项。消息层 `seq`、创建/更新/删除时间是可选 number；`client_id`、`session_id`、`context_token`、`run_id` 是可选 string（types.ts:193–208）。 |
| 引用 | 位于 `item_list[].ref_msg`，包含 `svr_id`、`message_item`、`title`、`partial_text`；上游选 `svr_id`，其次内嵌项 `msg_id`。引用可能只有 ID，也可能仅选中文字；没有通用顶层 `reply_to` 字段。[引用实现][inbound-quote] |

补核固定 pin 的 `inbound.ts`、`process-message.ts`、`monitor.ts`，三文件均未出现 `is_completed`、`message_state` 或 `MessageState` 的使用；本次没有发现“FINISH=2 后仍必须 is_completed=1/true”的上游入站 gate。若 D1 只接收 FINISH 并拒绝显式 false，应明确记为本项目保守策略；字段出现时按布尔值严格校验，不能把数字 1 当 true。[入站][inbound]、[处理][process]、[监控][monitor]

接口用 JSON/HTTP；POST 头含 `AuthorizationType: ilink_bot_token`，有 token 时带 Bearer；还有 iLink 应用标识、客户端版本、随机 `X-WECHAT-UIN`。`bot_agent` 是观测标签，不是凭据或路由。[HTTP 构建][api-headers]

账号维度来自可信的拉取连接/凭据，不应从消息正文补造。二维码确认返回的 `ilink_bot_id`、`ilink_user_id`、`bot_token`、`baseurl` 是不同字段；前者为 bot 账号，后者为扫码用户。[登录返回][login]

上游公开能力仅声明 `chatTypes: ["direct"]`，鉴权策略关闭群聊；原始 DTO 存在 `group_id` 不能证明已支持群聊。普通用户 ID 后缀识别也只是客户端路由实现，不是律师身份认证。[能力][channel]、[鉴权][authorization]

## 已核实：游标、引用与 context_token 范围

- 游标文件按账号保存；监控成功时先保存非空新游标，再遍历处理消息。这段代码不能证明收件与游标原子提交、崩溃可重放或端到端恰好一次。[监控][monitor]、[游标存储][sync]
- 引用缓存数据库主键是 `(account_id, conversation_id, message_id)`，查询也包含三项。它提供本地作用域证据，没有声明服务端消息 ID 在所有账号全局唯一。[引用缓存][quote-store]
- `context_token` 注释要求原样回传出站；实现按账号＋用户缓存并可落盘，发送时使用该次处理获得的 token。它不是本系统用户身份、案件权限或发送批准。[token 存储][inbound]、[处理][process]
- 上游无 owner 的历史账号会允许消息通过、只禁止命令；这是兼容分支，不能作为本项目可信绑定规则。正常路径按 sender 精确匹配，策略为私聊配对、群聊关闭。[鉴权][authorization]

### 补核：svr_id 与顶层 message_id 的引用键关系

同一固定提交存在明确的官方客户端串联证据，不能把“可能是不同 ID 空间”的猜测写成事实：`inbound.ts:202–209` 优先取顶层 `message_id`；`process-message.ts:214–230` 将该值存入引用缓存 `messageId`，范围为账号与 sender；`inbound.ts:337–352` 取 `ref_msg.svr_id` 后直接作为相同缓存键查找，没有转换表或另一套 ID 翻译。SQL 在 `quote-store.ts:304–314` 按账号、会话及消息 ID 三字段精确相等查找。[入站取 ID][inbound-id]、[缓存写入][process-cache]、[引用查找][inbound-quote]、[SQL][quote-store]

`inbound.test.ts:309–341` 明确让 `svr_id`、mock 缓存记录的 `messageId`、`find` 的第三参数与 `ReplyToId` 取同一个大整数 ID 字符串；`:542–545` 另测顶层 `message_id` 优先于项 ID。`quote-store.test.ts:72–92` 测相同 ID 的持久读取及跨账号/会话不命中。这些是官方客户端预期与单元测试证据，不是服务端正式协议或真实消息流测试；本次只读测试源码，没有运行它们。[引用测试][inbound-tests]、[缓存测试][quote-tests]

因此可确认“该 pin 的客户端把引用 svr_id 与缓存的顶层 message_id 当成可直接比较的键”，仍不能宣称跨账号全局唯一、所有客户端/未来版本恒同，或平台正式保证。D1 若沿此客户端合同处理引用，必须限定同源、同账号、同 peer 的精确命中；若 D1 的准入要求服务端级保证，则保留原始引用并待 D2 验证/映射，不能猜出跨范围链接。后者是本项目保守范围选择，不是已证实两种字段属于不同 ID 空间。

## 已核实：媒体与限额的实际含义

`CDNMedia` 声明 `encrypt_query_param`、`aes_key`、`encrypt_type`、`full_url`。上游优先使用 `full_url`，否则回退为配置 CDN 下的 `/download?encrypted_query_param=...`；默认 CDN 是 `https://novac2c.cdn.weixin.qq.com/c2c`，API 默认地址是 `https://ilinkai.weixin.qq.com`。[媒体类型][types]、[下载构建][cdn-url]、[默认地址][accounts]

文件/语音/视频解密使用 AES-128-ECB、PKCS7；`aes_key` 可为 base64 的 16 原始字节，或 base64 的 32 位十六进制字符串。图片另有优先的 `image_item.aeskey` 十六进制 key。不能与企业微信 AES-256-CBC 混用。[解码][decrypt]、[AES][aes]、[入站媒体][media]

上游下载器直接 `fetch(fullUrl)` 并整体取 `arrayBuffer`，这些函数未见 scheme/host/端口/私网/重定向约束或下载中途限流。文件保存处把 `100 * 1024 * 1024` 传给框架，但在下载/解密之后；这不是已经证实的平台文件上限，也不是安全的下载流量限制。`file_item.len` 和 `md5` 仅为上游元数据，不能代替实际字节、SHA256、解析质量或法律真实性核验。[下载器][decrypt]、[保存位置][media]

`textChunkLimit=4000` 是插件配置值；引用缓存单文件 25 MiB、每账号 256 MiB、媒体 7 天/文字 30 天也是本地缓存策略，均不能写成微信服务端限制。服务端文字字节限额、单消息项目数、文件格式/大小、频率、媒体 URL/token 有效期，本次没有官方保证。[文本设置][channel]、[缓存策略][quote-store]

## 已核实：发送、错误与撤销边界

POST `ilink/bot/sendmessage` 的请求包裹单个 `msg`；文字 helper 设置空 `from_user_id`、指定 `to_user_id`、生成 `client_id`、BOT/FINISH、文字项及可选 `context_token`/`run_id`。响应只声明可选 `message_id`、`ret`、`errmsg`；helper 区分客户端 ID 与可选服务端 ID。当前源码没有送达/已读证明。[发送构建][send]、[API][api-send]

上游 send API 对非零 `ret` 抛错；拉取监控同时检查非零 `ret`/`errcode`。`-14` 被视为 token 失效并按账号暂停一小时；普通拉取错误先隔 2 秒，连续三次后退避 30 秒。客户端长轮询超时返回空消息且保留原游标，是客户端容错行为。[错误处理][monitor]、[会话守卫][guard]、[超时实现][api-poll]

读取的 API 入口包含拉取、发送、取配置、typing、上传 URL、启停通知；没有发现远端撤销凭据、消息撤回或按 client_id 查询发送回执的入口。账号清理删除本地凭据、游标、token、白名单及引用缓存，不证明服务端凭据已撤销。`delete_time_ms` 的声明也不足以推断消息删除通知如何重放。[API][api]、[账号清理][accounts]

未找到服务端对重复 `client_id` 的去重保证、超时后查询结果办法或安全重试承诺；源码产生客户端 ID 不能当成幂等证明。CDN 上传的重试是另一条路径，不能推广到发消息。[文字发送][send]、[CDN 上传][cdn-upload]

## 企业微信备选：不同通道，不替换 iLink 字段

WecomTeam SDK 使用 `wss://openws.work.weixin.qq.com`，以 bot_id/secret 认证；帧 `headers.req_id` 用于回复关联并等待 ACK，文件解密为 AES-256-CBC。它属于企业微信机器人通道，不能把 req_id、ACK 或 CBC 套到腾讯个人微信插件；账号资格、会话范围、数据政策须独立批准。[说明][wecom-readme]、[帧/ACK][wecom-ws]、[解密][wecom-crypto]

## 本项目建议（不是上游事实，也不代表已经实施）

1. D 的首片只做离线 envelope 校验与合成入站，真实账号、网络拉取、媒体下载、发送、模型和真实材料外发保持关闭。纯解析函数输入来源不自动取得“官方可信”身份。
2. 绑定至少精确区分本地连接/绑定修订、远端 bot、owner 用户、私聊 peer；必须由本系统现有可信桌面授权绑定到本地用户/工作区。拒绝缺失、旧版本、撤权、跨账号/peer、群聊或身份不一致；不得继承空白名单放行。
3. 收件唯一键包含来源通道、可信连接/账号、会话 peer 与 provider message_id；保持 provider ID 精度。引用只查询同源同账号同 peer 已保存记录；未知或多义引用保留待处理，不能跨会话猜任务。
4. 不透明远端游标与既有本地整数 revision 分开。新增事件、媒体待办和新游标需一起提交；重复同来源事件只有完全一致才幂等，不一致内容记录冲突并阻断，不静默覆写。
5. 文件元数据可以形成 `media_pending`；未得到受控、完整、校验过的明文字节前不得计为已接收材料或进入冻结 manifest。URL/key/token 属于受限能力数据，日志、普通视图和可分享证据只保留必要状态/摘要。
6. 将来接网前另做允许的 HTTPS 主机/路径、DNS/私网、端口、凭据、重定向逐跳、超时、流式密文/明文上限及 key 校验；未知来源 full_url 先阻断。以上是本地安全策略建议，不是声称所有合法腾讯 URL 均已穷举。
7. 出站必须分别经过指定收件人/内容批准；客户端超时或缺少明确回执进入 `unknown` 并停止自动重发。`context_token` 更新不可替代重新核验批准和绑定；本片不实现出站。

真实接入仍待确认：账号资格/授权范围与平台条件；服务端 ID 唯一范围、游标保留/重放/重置语义；更新/删除/撤回事件；全部服务端限额；token/context_token/媒体 URL 的到期和撤销；发送幂等、回执查询及未知结果恢复。以上没有账号实测，不能标 `PASS` 或“真实微信已打通”。

## 本次证据与验证

用于上述结论的固定提交 GitHub API/Raw 只读请求成功；路径探查时 `src/messaging/context-token-store.ts` 返回 404，随后从实际存在的 `inbound.ts` 核对实现，未把失败路径当来源。未运行产品测试（研究任务，无业务代码变更）。首轮文档引用校验退出 0：30 个定义、40 处使用、缺失 0；引用 ID 补核后校验亦退出 0：34 个定义、46 处使用、缺失 0。完成字段补核后再次校验引用。核心文件抓取内容按 UTF-8 编码的 SHA256 如下；未导入源码为运行依赖：

| 固定提交文件 | UTF-8 SHA256 | 字节数 |
| --- | --- | ---: |
| LICENSE | `7f1e8cf099cf03de7c775e33e97e3c950c3a56a9616bb4de6b14d3c911bc5573` | 1301 |
| src/api/types.ts | `9e321e1a79bd7ec385b8e2b9695f1d87507282ff33f9cfdafbe4e33aea5387ac` | 7546 |
| src/api/api.ts | `7a808846a33c70423b4a4a5fcf3c1a45f885d005994218ef5f4db663d4e6e935` | 22100 |
| src/cdn/pic-decrypt.ts | `49a9b08ced1b3ddb7c4d80dd279ba7d7f977febc999a9507f8f41c05976dceaa` | 3504 |

[commit]: https://github.com/Tencent/openclaw-weixin/commit/874637a0dbc24050f72d1385add4fc6170a2d726
[license]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/LICENSE
[package]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/package.json
[types]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/types.ts
[api]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/api.ts
[api-headers]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/api.ts#L227-L254
[api-poll]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/api.ts#L438-L487
[api-send]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/api.ts#L579-L597
[inbound]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/inbound.ts#L14-L127
[inbound-quote]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/inbound.ts#L300-L354
[inbound-id]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/inbound.ts#L202-L209
[process-cache]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/process-message.ts#L214-L230
[inbound-tests]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/inbound.test.ts#L309-L341
[quote-tests]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/quote-store.test.ts#L72-L92
[login]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/auth/login-qr.ts#L450-L472
[accounts]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/auth/accounts.ts
[channel]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/channel.ts#L229-L269
[authorization]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/authorization.ts
[monitor]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/monitor/monitor.ts
[sync]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/storage/sync-buf.ts
[quote-store]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/quote-store.ts
[process]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/process-message.ts#L289-L295
[cdn-url]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/cdn/cdn-url.ts
[decrypt]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/cdn/pic-decrypt.ts
[aes]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/cdn/aes-ecb.ts
[media]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/media/media-download.ts
[send]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/messaging/send.ts#L56-L136
[guard]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/api/session-guard.ts
[cdn-upload]: https://github.com/Tencent/openclaw-weixin/blob/874637a0dbc24050f72d1385add4fc6170a2d726/src/cdn/cdn-upload.ts
[wecom-commit]: https://github.com/WecomTeam/wecom-aibot-python-sdk/commit/6bcb59a9a636c566f4c6ea5268b228e3def1611a
[wecom-license]: https://github.com/WecomTeam/wecom-aibot-python-sdk/blob/6bcb59a9a636c566f4c6ea5268b228e3def1611a/LICENSE
[wecom-readme]: https://github.com/WecomTeam/wecom-aibot-python-sdk/blob/6bcb59a9a636c566f4c6ea5268b228e3def1611a/README.md
[wecom-ws]: https://github.com/WecomTeam/wecom-aibot-python-sdk/blob/6bcb59a9a636c566f4c6ea5268b228e3def1611a/aibot/ws.py
[wecom-crypto]: https://github.com/WecomTeam/wecom-aibot-python-sdk/blob/6bcb59a9a636c566f4c6ea5268b228e3def1611a/aibot/crypto_utils.py
