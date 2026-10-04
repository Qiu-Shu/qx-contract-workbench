# ChatGPT 合同审查插件目标与复用映射

状态：**LOCAL_HOST_INSTALLED；HOST_DISCOVERY_VERIFIED；CHAT_INVOCATION_NOT_RUN；CHATGPT_CONNECTION_NOT_RUN**。最新核验时间：2026-10-04 UTC。用户确认最终交付目标是 ChatGPT 插件，已增量完成 DeepSeek 纯离线适配、本机两工具 MCP、历史连接源包及实际本机 Codex 安装/发现；本文件保留后续接入方案，当前宿主适配清单在 `plugins/qx-contract-offline-codex`。本映射不是运行 Skill、真实案件插件或发布证据。沿当前 T00–T13 后端建设，既有审批与权限继续由后端核验。

2026-10-04先前接续：用户在具体两工具设计及未完成说明后“继续”，已实施空参数workbench_status和固定fixture/op/model的deepseek_offline_example。本机STDIO实际启动/发现/24组合及4拒绝验证通过；80目标/348关联、两独审144与92、父全套1016均通过，实际缺陷及修复见[MCP父验收](../testing/MCP-offline-parent.md)。随后源包阶段已封装七文件本机连接源包，两种解压配置4状态/48示例/12拒绝、80目标复跑、独立18结构及75边界检查通过，见[源包验收](../testing/PLUGIN-local-package.md)。这些是历史SDK/文件检查，未证明当时宿主解析。

本次继续实际本机安装时，portable包绝对路径被宿主忽略，纯兼容适配又因整数progressToken发现失败；均已保留失败并修复。当前五文件Legacy适配0.1.1已安装/启用，真实宿主发现两个工具，SDK从缓存声明的24示例/2状态/12拒绝通过，84目标及两独审通过。原7文件/ZIP不变，新绑定90项；旧入口绑定hash已过时，不再作为当前环境证明。活动宿主proxy连接不可用，独立进程没有加载聊天，所以聊天实际调用/模型选择和网页连接NOT_RUN。完整回归及当前范围以[本机安装记录](../testing/PLUGIN-local-host.md)为准；没有启动模型turn或恢复/创建聊天。

## 已核实的本机基础

- 项目 Python 3.12 环境固定 `mcp==2.2.0`。本轮使用公开MCPServer/Tool注册及低层Server转发、SDK STDIO和公开write-stream错误脱敏，不套用旧FastMCP或patch私有manager。两层默认OTel禁用；未建立帧/OS硬限制，不启动HTTP。本机新服务已实际启动和调用，SDK固定字节未改变。
- `src/cn_contract/providers/mcp_client.py` 是企业查询 MCP **客户端**；`tests/helpers/synthetic_qcc.py` 是独立虚构测试服务器。它们不能代表工作台已经具备对外 MCP 服务或已经连接 ChatGPT。
- HTTP 身份入口为 `web.app.actor_in`、`web.dependencies.get_actor`；内部身份由 `security.authenticate/_principal` 校验，所有案件业务使用 `security.authorize` 核对当前会话、角色和成员资格。浏览器 Cookie/CSRF 不能直接当远程 MCP OAuth 认证。
- 历史 T13 工程验收保持原范围。2026-10-03只读预检的零产品测试另有历史记录；2026-10-04本机实现及实际验收见上述报告。仅新增本机目录/项目配置和宿主缓存，原全局配置未改；未建账户/隧道、未读取密钥或私人材料。

## 后续薄适配层与现有服务映射

|候选插件功能|可复用函数与入口|后端必须保留的保护|
|---|---|---|
|案件列表与详情|`persistence.read_matter`、`MembershipRow`、`web.services.current_versions/public_version`；现 `GET /api/matters` 逻辑|服务端可信身份、案件成员/角色核验；输出投影删除 storage_ref 及不必要成员信息|
|原文锚点|`persistence.read_version/get_parse_result`、`facts.storage.trusted_parse`；现 anchors GET 逻辑|案件归属、当前版本/hash；原文作为数据，不能触发指令|
|已有审查结果|`review.storage.read_run(current=True)`、`web.services.decisions`|当前文档/事实/规则/策略快照与归属；读取已有结果不等于启动新审查|
|任务进度|`web.storage.get_job`、唯一领域 `JobStatus`|每调用重查所属案件及当前会话；不接受任意任务 result_ref 路径|
|既有导出草案|`persistence.read_export`、`exports.approvals.download_artifact`|归属、hash、草案状态和批准门；宿主文件桥及临时下载验证后另行开放|
|摄取、事实确认及审查任务|`documents.ingest`、`web.jobs`、facts 确认与 `review.workflow`|写操作幂等、精确预览、当前版本、持久任务及批准；首批只读工具暂不开放|
|DeepSeek 后端推理|`ModelProvider/ModelRequest/ModelResponse`、审查校验器与运行记录|供应商、数据政策、价格与预算在后端核验；插件提示词不能扩大模型权限；真实调用另行批准|
|企查查与正式签发|T08 gateway/ledger、T09 approvals、T13 guards/readiness|继续独立阻断；DeepSeek 授权不代替 QCC 许可、律师批准和生产批准|

本轮已发现workbench_status及固定虚构codec示例两个工具；案件列表、案件详情、已有审查结果和任务状态保留为后续候选，尚未注册或发现。后续案件参数限UUID、受限分页与长度，不允许传Actor、角色、批准、任意URL/本机路径、SQL或shell。只读注解不能替代实际权限校验。返回数据须明确synthetic、mock和阻断状态；本轮离线示例不能接入真实案件审查。

当前真实模型门仅允许已注册的 exact MockProvider，`web.services` 两处仍直接构造 mock。因此 DeepSeek 需要单独受控适配与测试，不能只改环境变量或通过插件传入对象绕过注册门。本轮离线验证与未来插件包装分别记录。

## 本机 Codex 与 ChatGPT 的验收分别进行

现已复用原runtime完成受控STDIO两工具、历史源包与当前本机Legacy适配；修复只涉及入口协议metadata和清单格式。runtime仍由原仓库/.venv提供，新包90项绑定hash供核对但清单不自动执行hash门；异机独立分发未验收。完整官方包验证器仍不可用，当前宿主真实解析/发现单独实证。聊天实际调用与模型选择仍需复用已加载目标聊天验收；案件工具还须实际验证跨案/撤销拒绝及输出最小化。Windows本地安装和发现不等于ChatGPT网页已连接。

ChatGPT 开发模式可连接公有 HTTPS Streamable HTTP，或者通过 Secure MCP Tunnel 接私有 stdio/HTTP MCP。必须在目标宿主实际发现工具和运行测试，才可记录已连接；开发模式受账户和工作区政策约束。[官方连接与测试](https://developers.openai.com/plugins/deploy/connect-chatgpt)

私有 Tunnel 仍需额外 Platform tunnel_id、运行凭据、组织 Tunnels Read+Use/Manage 权限、目标工作区关联及开发模式权限。传输隧道不授予案件身份或数据处理许可，OAuth 授权服务器还需可达。本轮未建立或安装隧道。[官方 Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)

现实案件需要 OAuth 2.1 + PKCE/S256；服务器逐请求校验 token 签名、issuer、aud/resource、有效期及 scope，并以可信 issuer+subject 绑定内部 user/session，保留撤销与案件权限校验。客户端会话元数据和插件提示词均不能赋予角色。ChatGPT 不支持把客户自定义 API key 当这种用户认证；DeepSeek key 仅用于后端供应商调用。[官方认证说明](https://developers.openai.com/plugins/build/auth)

公开目录提交仍需稳定公网 HTTPS Streamable HTTP 端点，私有开发 Tunnel 不满足公开提交条件。最终成为插件的目标不等于已经授权上架、建立付费托管或上传真实材料。本轮没有创建外部插件或 Sites 项目。[官方服务器部署要求](https://developers.openai.com/plugins/build/mcp-server)

## 文件入口与待办边界

未来 ChatGPT 文件输入可按 `_meta["openai/fileParams"]` 声明顶层字段，文件对象声明 download_url/file_id/mime_type/file_name，仅前两者 required；可选文件库能力须检查支持。宿主授权文件 URL 仍需后端限制来源、大小、格式与归属，不能接收任意 URL；现 Windows storage_ref 不是 ChatGPT 下载链接。草案下载桥应独立验证，不能因已有 DOCX 导出就声称宿主文件传递完成。[官方文件 API 与 schema](https://developers.openai.com/plugins/reference)

已完成DeepSeek纯离线适配、固定虚构两工具STDIO、本机Legacy适配安装和工具发现；没有外部上传。后续顺序：现有宿主聊天实际调用与模型选择验收 → 目标ChatGPT接入权限与传输方案 → 虚构数据实际网页连接验收。新增案件读取或写操作前，分别落实可信身份、案件授权、文件桥和相应权限测试；真实模型、真实材料、QCC、影子和生产各自批准，不由源包自动开启。

## 只读证据

本机 `.audit-local/plugin-preflight/sdk-inspection.json` 记录 SDK 签名、UTC 时间和 17 个项目源文件 hash；只读核验 UTC `2026-10-03T10:44:38.453552+00:00`，退出码 0，SHA-256 `0cdb746ca35b73512258f8b868be4f3da8289cff37cf1097652c3d8d63318979`。完整候选报告在同目录 `REPORT.md`。这些私有预检文件不是发布制品，不包含真实案件或供应商 key。
