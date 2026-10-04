# ChatGPT 合同审查插件目标与复用映射

状态：**PLANNING_ONLY**。核验时间：2026-10-03 UTC。用户确认最终交付目标是 ChatGPT 插件，本轮先做 DeepSeek 的离线适配与验证；本文件是后续接入方案，不是运行 Skill、插件清单、安装或发布证据。沿当前 T00–T13 后端增量建设，既有审批与权限继续由后端核验。

2026-10-04接续：DeepSeek首批纯离线适配已在`382850d`完成，936回归属于上一批实际结果。新本机MCP只读预检已完成，具体结果见[MCP-offline-preflight](../testing/MCP-offline-preflight.md)。本次聊天已提交无案件status与固定四虚构fixture/op/model的离线例两工具短设计，确认尚待回复；工作台server/两工具/STDIO产品验证仍NOT_IMPLEMENTED或NOT_RUN，未安装或连接宿主，不把纯SDK内存探针当新插件验收。

## 已核实的本机基础

- 项目 Python 3.12 环境固定 `mcp==2.2.0`，实际只读导入成功，服务端入口为 `mcp.server.MCPServer`，不能套用旧 FastMCP 示例。已安装 SDK 提供 `tool/add_tool/resource/run/streamable_http_app`，支持 stdio 和 Streamable HTTP。未启动新的 MCP 服务、未进行新的协议调用。
- `src/cn_contract/providers/mcp_client.py` 是企业查询 MCP **客户端**；`tests/helpers/synthetic_qcc.py` 是独立虚构测试服务器。它们不能代表工作台已经具备对外 MCP 服务或已经连接 ChatGPT。
- HTTP 身份入口为 `web.app.actor_in`、`web.dependencies.get_actor`；内部身份由 `security.authenticate/_principal` 校验，所有案件业务使用 `security.authorize` 核对当前会话、角色和成员资格。浏览器 Cookie/CSRF 不能直接当远程 MCP OAuth 认证。
- 历史 T13 工程验收保持原范围。此次预检只运行 SDK 导入和公共源文件读取，退出码 0；功能测试运行数 0。未安装插件、未建账户/隧道、未读取密钥或私人材料。

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

建议首批只读工具为无材料的 `workbench_status`，以及服务端固定独立虚构库下的案件列表、案件详情、已有审查结果和任务状态。工具名只是候选，尚未注册或发现。参数限 UUID、受限分页与长度；不允许传 Actor、角色、批准、任意 URL/本机路径、SQL 或 shell。只读注解不能替代实际权限校验。返回数据需要明确 `synthetic`、`mock` 和阻断状态。

当前真实模型门仅允许已注册的 exact MockProvider，`web.services` 两处仍直接构造 mock。因此 DeepSeek 需要单独受控适配与测试，不能只改环境变量或通过插件传入对象绕过注册门。本轮离线验证与未来插件包装分别记录。

## 本机 Codex 与 ChatGPT 的验收分别进行

本机 Codex 可在后续批准的范围新增薄 MCP server，复用原项目 runtime，以 stdio 先验证；源包包含 portable 插件清单、MCP 配置和说明，必要时附宿主兼容清单。必须实际验证启动、工具发现、无害调用、跨案/撤销拒绝与输出最小化后，再走宿主安装流程。Windows 本地 stdio 或上传源包，不会使 ChatGPT 网页自动获得本地进程访问。

ChatGPT 开发模式可连接公有 HTTPS Streamable HTTP，或者通过 Secure MCP Tunnel 接私有 stdio/HTTP MCP。必须在目标宿主实际发现工具和运行测试，才可记录已连接；开发模式受账户和工作区政策约束。[官方连接与测试](https://developers.openai.com/plugins/deploy/connect-chatgpt)

私有 Tunnel 仍需额外 Platform tunnel_id、运行凭据、组织 Tunnels Read+Use/Manage 权限、目标工作区关联及开发模式权限。传输隧道不授予案件身份或数据处理许可，OAuth 授权服务器还需可达。本轮未建立或安装隧道。[官方 Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)

现实案件需要 OAuth 2.1 + PKCE/S256；服务器逐请求校验 token 签名、issuer、aud/resource、有效期及 scope，并以可信 issuer+subject 绑定内部 user/session，保留撤销与案件权限校验。客户端会话元数据和插件提示词均不能赋予角色。ChatGPT 不支持把客户自定义 API key 当这种用户认证；DeepSeek key 仅用于后端供应商调用。[官方认证说明](https://developers.openai.com/plugins/build/auth)

公开目录提交仍需稳定公网 HTTPS Streamable HTTP 端点，私有开发 Tunnel 不满足公开提交条件。最终成为插件的目标不等于已经授权上架、建立付费托管或上传真实材料。本轮没有创建外部插件或 Sites 项目。[官方服务器部署要求](https://developers.openai.com/plugins/build/mcp-server)

## 文件入口与待办边界

未来 ChatGPT 文件输入可按 `_meta["openai/fileParams"]` 声明顶层字段，文件对象声明 download_url/file_id/mime_type/file_name，仅前两者 required；可选文件库能力须检查支持。宿主授权文件 URL 仍需后端限制来源、大小、格式与归属，不能接收任意 URL；现 Windows storage_ref 不是 ChatGPT 下载链接。草案下载桥应独立验证，不能因已有 DOCX 导出就声称宿主文件传递完成。[官方文件 API 与 schema](https://developers.openai.com/plugins/reference)

后续顺序：完成本轮 DeepSeek 离线适配 → 固定插件只读范围与可信身份方案 → 新 MCP 协议/权限测试 → 本机宿主安装验收 → 取得目标 ChatGPT 接入权限及传输方案 → 虚构数据实际连通验证 → 分别批准真实数据、写操作和生产。现实模型调用、真实材料上传、QCC、影子运行和正式签发继续遵守各自批准门。

## 只读证据

本机 `.audit-local/plugin-preflight/sdk-inspection.json` 记录 SDK 签名、UTC 时间和 17 个项目源文件 hash；只读核验 UTC `2026-10-03T10:44:38.453552+00:00`，退出码 0，SHA-256 `0cdb746ca35b73512258f8b868be4f3da8289cff37cf1097652c3d8d63318979`。完整候选报告在同目录 `REPORT.md`。这些私有预检文件不是发布制品，不包含真实案件或供应商 key。
