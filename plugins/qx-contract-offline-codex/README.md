# 群兴合同审查本机 Codex 适配源包

源配置版本 0.1.4。依赖固定项目 `D:/Documents/ChatGPT/律所项目` 与该项目 `.venv`，不含独立运行环境。当前新增明确选案只读连接；最新源码与实际HTTP/STDIO测试见 `../../docs/testing/CASE-bridge-20261009.md`。未刷新缓存，本父聊天仍是旧连接拒绝；不把本机测试称网页ChatGPT接入。

历史0.1.3阶段源曾冻结为 v2 绑定：100 个源/选定文件、57 个已安装版本，构建编号 `qx-offline-source-0.1.3-bd6518818b05ba45094fe2e8f1040be9`。实际 `--check`、固定绝对入口 SDK 和独立原始 STDIO 均通过；原 0.1.2/v1 快照保留为历史证据。Git 对已绑定文件和新虚构清单保留精确 bytes；独立核验 101 个对象与工作文件一致。详情见 `../../docs/testing/AUDIT-A3-entry-binding.md` 和 `../../docs/testing/ASSISTED-parent.md`。这些结果只证明当前源入口，未刷新或验收宿主缓存与聊天调用。

`.mcp.json` 保留原固定项目 Python command/cwd，入口改为 `-I -X utf8` 加 `src/cn_contract/mcp/bound_entry.py` 的固定绝对路径。避免 `-m` 在检查前导入 `cn_contract.__init__` 及领域代码。`-I` 减少当前目录、用户 site 与 Python 环境变量对查找路径的影响，不是 OS 沙箱或依赖字节认证。

新入口只读取当前项目源包的固定 `plugins/qx-contract-offline-codex/runtime-binding.json`，不接受 MCP 客户端路径或环境覆盖。v2 绑定核对项目根、实际入口、既有离线模块、源配置、Python 和锁内已安装依赖版本、mock/QCC 关闭默认值，并独立枚举 `src` 内所有 `.py/.js/.css/.html`（包括未跟踪的新文件）。另绑定选定锁、默认配置及原四份虚构合同和 provenance；未知、遗漏或额外映射、字节 hash 不符、重复 JSON 键、越界大小、已知链接/reparse/hardlink 均拒绝。构建编号由绑定内容的规范 JSON hash 派生，验证时重算。

检查成功后才将已核验的项目 `src` 加入导入路径并调用原 `offline_server.main`。失败时退出码 78，仅 stderr 输出 `BOUND_ENTRY_REJECTED`，不启动工具或污染 STDIO stdout。`--check` 成功时仅输出固定状态和非私密构建编号，不启动 SDK 服务。

检查针对当前项目源包，不证明活动缓存中的 manifest 或已加载入口相同。执行中的 Python 与守卫代码仍是启动前提；可以同时篡改守卫及绑定的本机权限主体不受它隔离。源码和运行时在检查后仍可能变化；Python/已安装包/OS 及 `.pth` 启动行为没有被此守卫免疫化。依赖版本匹配不能替代 wheel 字节、许可批准、系统隔离或实际宿主验收。

当前源增加无参只读工具 `read_selected_case`，读取默认持久工作台当前明确开放的15分钟虚构案件，不能代替律师确认、写回或批准。原 `workbench_status` 与 `deepseek_offline_example` 保留；后者只接受四类固定虚构合同、三种离线协议操作和两个模型名称；人工响应/token/未知费用不是供应商调用或法律结论。不能传真实合同、正文、路径、URL、密钥或费率。协议允许有界整数或 UTF-8 字符串 progressToken；tools/call 另允许小写规范 UUID threadId，标识不进入业务 handler、身份或批准。详见 `../../docs/testing/AUDIT-A3-progress.md`，其协议测试不等于宿主聊天调用。

保留原 `../qx-contract-offline-local` 七文件源包及 ZIP 作为历史证据。项目 `.agents/plugins/marketplace.json` 与 `.codex/config.toml` 的旧安装记录保持原状，不修改全局设置或缓存。本源包不含 Skill、代理、hooks、shell 工具或远程 MCP。实际宿主加载/聊天调用、网页 ChatGPT 连接、真实模型/QCC、法律 gold、正式签发和生产仍未验收或阻断。
