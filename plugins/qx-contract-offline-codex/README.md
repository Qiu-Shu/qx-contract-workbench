# 群兴合同审查本机 Codex 适配包

版本0.1.1。适配当前 Windows Codex 的本机兼容格式，依赖仓库 `D:/Documents/ChatGPT/律所项目` 和其中的 `.venv`；不包含运行代码或独立运行环境。

保留原 `../qx-contract-offline-local` 七文件源包及其 ZIP 作为历史证据。原包使用的绝对 command/cwd 不符合当前宿主 portable MCP 解析约束，因此本包仅使用 `.codex-plugin/plugin.json` 与 `.mcp.json`，通过同一项目 Python 入口连接既有服务。0.1.1 配套服务新增有界整数 progressToken 兼容；原包绑定快照中该入口旧 hash 已过时，不能当当前环境证明。目录不能迁移后直接沿用；路径变化需重配并重新验收。

只声明 `qx-contract-offline` STDIO 服务，工具为 `workbench_status` 与 `deepseek_offline_example`。后者仅接受四类固定虚构合同、三种协议操作和两个离线模型名称；不能传入真实合同、任意正文、路径、URL、密钥或费率。人工响应、token 与未知费用不代表供应商调用或法律审查。

项目目录通过 `.agents/plugins/marketplace.json` 提供本机目录，通过 `.codex/config.toml` 启用本包并关闭原 portable 包；不修改全局配置。不包含 Skill、代理、hooks、shell 工具或远程 MCP。tools/list 和 tools/call 仅兼容空 metadata 或唯一 progressToken 且类型为整数、范围 0–2^63−1；字符串及其他字段拒绝，ping 仍仅接受空 metadata。该标记不会传给业务工具或产生进度通知，此为本机受限协议范围。运行绑定是人工核验快照，清单不会自动执行 hash 强制校验，也不能证明 OS 隔离。

生成时宿主调用尚未验收；实际安装、发现、调用及拒绝结果以 `../../docs/testing/PLUGIN-local-host.md` 的阶段记录为准。网页 ChatGPT 连接、模型主动选择工具、真实模型、企查查、法律金标准、正式签发及生产仍未完成或阻断。
