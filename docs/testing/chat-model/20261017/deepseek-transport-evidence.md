> 原始记录位于本仓 `.local/chat-model-20261017`；下文原始脚本、日志和未复制的页面文件路径均相对该目录。此处仅保存可提交摘要。

# CH-04 主模型协议与传输接线依据

2026-10-17 只读核验；未读取真实 key、未向模型端点发送请求。当前只读取公开文档与已安装源码，产品模块待主代理统一 DTO 后实施。

## 官方事实与首片选择

| 核验 | 事实 | 首片采用方式 |
|---|---|---|
| [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) | 路径 `/chat/completions`；当前模型目录列 deepseek-flash、deepseek-v4-pro；thinking 默认 enabled | 只允许受信配置选上述 ID；固定 HTTPS 官方端点，明确 thinking.disabled；不接受输入提供 URL |
| 同页 | JSON object 格式；max_tokens 限制输出；非 stop 的终止原因包括截断、过滤、工具请求、资源不足、中止 | 首片 stream:false、显式小预算 max_tokens、response_format.json_object；只接受完整单条结果，不启工具/图片/推理正文 |
| 同页 | usage 包含输入、输出、总量及缓存分项；usage 本身未标 required；输入数等于 hit+miss、总量等于输入+输出 | 缺失保留 unknown；出现的数值严格整数且非 bool，校验可验证的加总关系；usage 有误与内容校验分开记录，费用不补零 |
| [JSON Output](https://api-docs.deepseek.com/guides/json_mode/) | 提示中还需明确 JSON 和格式示例；可能返回空内容，预算不足可导致截断 | 服务端固定提示含 JSON 与本机输出契约；空内容或非法结构不保存正常成果；不自动修复或重发 |
| [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/) | 非流式等待期间可能持续空行；流式为保活注释；未开始推理 10 分钟后服务器才断开 | 接受有界前置空白；逐次读超时外再设独立总截止，不把10分钟当本应用等待目标 |
| 同页 | 429 是并发超限；可选 user_id 用于隔离，不能含私人信息 | 首片本机限并发；不自动重试429；不额外发送客户身份字段 |

完整供应商响应仍是未可信数据。JSON mode 保证不替代领域结构、来源或权限核验。当前首片不采用供应商 token 流；官方最后 chunk 的 usage 语义并非另发 choices=[] 的 usage-only 块，未来启流时需独立按该供应商协议验证。

公开证据：`official-doc-fetch.json` 保存三个 URL、HTTP200、原始 HTML 摘要与字节数；同目录 `json-mode.html/.txt`、`rate-limit.html/.txt`、`chat-completion.html/.txt`。Web 首读部分入口曾 Internal Error；Scrapling 首读均因中文 CA 路径 curl77 失败（`protocol-source-probe.json`）。第二次复制 certifi 相同字节至本机临时 ASCII 文件并开启 TLS 验证后成功；临时 CA 已删除，不是绕过证书验证。上述页面本次成功抓取不表示供应商账号或模型实调成功。

## 已安装 HTTP 栈（本机源码事实）

- `httpx2==2.13.1` 实际可 import；签名记录在 `protocol-source-probe.json`。现有 `providers/mcp_client.py` 已使用它，runtime lock 的 mcp 依赖包含同版本。
- `httpx2/_transports/default.py::AsyncHTTPTransport` 支持 `retries=0`、TLS验证、`trust_env=False`；`_client.py::AsyncClient` 支持禁止重定向及 `.stream()`。
- `httpx2/_models.py::aiter_bytes` 会解码 Content-Encoding；`aiter_raw` 读原始流。建议请求 `Accept-Encoding: identity`，拒绝非 identity 的 Content-Encoding 后累计 raw 字节，防压缩膨胀；既不依赖 Content-Length，也不用无界 response.read/json。
- 没有必要安装 OpenAI/DeepSeek SDK。若产品直接引用 httpx2，应在 pyproject 明确声明同一固定版本并同步已有依赖证据；这是直接依赖声明，不是引入第二套 HTTP 栈。

## 提交给主代理统一的最小契约建议

1. 主模型传输输入只能是已验证的聊天 DTO 和受信配置：固定 provider/model、有限消息、输出 token 限额；不收自由 URL、tools、任意参数字典或本机路径。真实模式从受信 resolver 取凭据；测试构造器仅接受精确 `127.0.0.1:<port>` 合成端点，绝不由 HTTP 输入开启。
2. 一次方法调用最多一次 HTTP POST；`before_dispatch` 由 runner/attempt 层以短事务完成 claim，网络调用不持 Session。异常只返固定代码与结构化传输阶段，不泄漏 exception repr、URL凭据、响应正文。
3. 适配器要区分 received / sent_unknown / failed-before-send，并返回可空 provider_request_id、真实 usage、响应摘要、content-validation 状态。收到不合格正文仍可能计费；不要抛失已收到 usage 的简单异常。
4. 首片可用 `stream(MainRequest)` 返回状态和完整已解析的最终候选，而非原始 vendor token。父层校验受众/来源后才出业务事件；协议层不批准事实、不创建档案、不改材料版本。
5. 总 deadline 使用外层 `asyncio.timeout` 包含连接、发体、读头、保活及读体；HTTP 内部 connect/read/write/pool 分别有界；无重试、无 redirect、无代理环境。取消必须传播，attempt 层仍对可能已发送的请求留未知账。
6. 普通日志只固定码/摘要/时长。复用已有 ContextVar 日志清理模式，但不要直接依赖合成 MCP 的 endpoint gate、专用日志开关或协议 Session。使用合成 key/body canary 检查 info/debug、异常、header 回显、body 回显；允许的正文内容与秘密标记区别处理。

建议协议失败测试覆盖：精确请求参数；usage缺失与非法；空内容/截断/模型漂移/工具或推理正文；重复键/深度/响应大小；chunked和伪Content-Length；压缩响应；不停空行的总截止；429/500/redirect各一次POST；取消；无key零POST；异常与debug日志无合成秘密。全部只用本机合成服务，后续实现结果另记。
