# 本机插件安装、发现与受限协议验收

日期：2026-10-04；实际 workspace `D:/Documents/ChatGPT/律所项目`，沿 `codex/contract-review-v2`，基线 `4551f052a8801eec299879371a8f675d5b205a39`。用户“继续”承接上阶段本机安装待办；不授权真实模型、付费、真实材料上传、建账户或外部发布。本阶段先完成本机 Codex 的安装与发现，网页 ChatGPT 与聊天实际调用分别记录。

## 当前已确认范围

本机适配包 `plugins/qx-contract-offline-codex` **0.1.1** 已由实际 Codex **0.159.0-alpha.12.1** 解析、缓存并启用，目标 STDIO 服务成功完成握手和工具发现。只发现 `workbench_status` 和 `deepseek_offline_example`，`toolsError=null`、resources/templates 为空、HTTP origin 为空，身份状态为 unsupported（本机无 OAuth），无已加载线程的 runtimeStatus 为 null；不能将它写成聊天持续连接或认证验收。

从已安装缓存的 `.mcp.json` 使用固定 SDK 实际调用：24 组四类虚构材料×三种操作×两个离线模型、2 次状态、12 次越界拒绝通过。人工响应、token 与费用未知不代表真实供应商调用、法律审查或案件授权。宿主聊天调用和模型选择工具仍 **NOT_RUN**。

本阶段发现并关闭两项真实兼容问题：原 portable 包绝对启动路径被宿主忽略；现有服务拒绝宿主标准整数 progressToken 导致工具发现失败。原源包和 ZIP 保留为历史证据，新包使用本机兼容格式，服务仅最小扩展受限元数据。没有重写已有工作台、加入新依赖或扩展工具/业务参数。

## 宿主格式失败与修复

首次本机目录与项目启用后，原 `qx-contract-offline-local@qx-contract-local` 的安装状态为 true、enabled true，但 `plugin/read.mcpServers=[]`，目标工具发现为空；安装不等于入口被接受。7 个缓存文件与原源包逐项字节相同。

精确宿主版本官方源码及实际二进制确认：portable stdio command 仅接受裸可执行名或包内 `./` 路径；cwd 也必须在许可的包内/数据目录范围。原根 `mcp.json` 中绝对 `.venv` command/cwd 不符合该格式。宿主在每服务解析失败时仅发 tracing warning，响应的 loadErrors 不能证明 MCP 接受。[精确版本解析器](https://github.com/openai/codex/blob/180d8caaac22c656bfc6329f2f573ee1430cbe20/codex-rs/codex-mcp/src/agent_plugin_config.rs)、[宿主 loader](https://github.com/openai/codex/blob/180d8caaac22c656bfc6329f2f573ee1430cbe20/codex-rs/core-plugins/src/loader.rs)。此前18项结构检查是结构/SDK验证，不是 portable 宿主解析通过；先前依据通用宿主绝对路径支持的推断不足，现予更正。

另两组私有格式候选实际 installed/enabled 均 false，未作为启用后的格式失败。添加 inline/兼容清单字段不能救回已经被根 portable 配置拒绝的服务；没有因此开启实验功能或扩大权限。

新独立包仅使用 `.codex-plugin/plugin.json` 与 `.mcp.json`，没有 root portable `plugin.json/mcp.json`。精确版本将此选为 Legacy，允许现有绝对 runtime command/cwd。[兼容格式选择](https://github.com/openai/codex/blob/180d8caaac22c656bfc6329f2f573ee1430cbe20/codex-rs/utils/plugins/src/plugin_namespace.rs)、[兼容 MCP 解析](https://github.com/openai/codex/blob/180d8caaac22c656bfc6329f2f573ee1430cbe20/codex-rs/codex-mcp/src/plugin_config.rs)。源包五文件、原静态图标和当前90项人工绑定；不复制 runtime/合同/依赖、Skill、代理或 hooks。

本项目 `.agents/plugins/marketplace.json` 提供本机目录，`.codex/config.toml` 启用新包、关闭原包；没有全局配置或用户目录源设置修改。宿主自动生成用户缓存 `C:/Users/Administrator/.codex/plugins/cache/qx-contract-local/qx-contract-offline-codex/0.1.1`。未使用 plugin/install、全局目录添加、协议接受、身份连接、daemon 重启或新聊天。[项目目录与配置规则](https://developers.openai.com/plugins/build/plugins)。

## 宿主协议失败与修复

初版纯兼容适配被实际宿主安装、启用、识别服务，但发现返回 `MCP startup failed: Mcp error: -32602: OFFLINE_REQUEST_REJECTED`。本机临时透明诊断仅记录握手字段形状：initialize `2025-06-18` 成功，随后 tools/list 带 `_meta:{progressToken:int}`，被原只允许空 metadata 的规则拒绝。诊断配置仅为单个子进程覆盖，未进入产品包或项目配置。

正式新增4项测试先实际 **4 failed / 0 errors**；三个允许标记的发现失败及拒绝后合法恢复失败均为功能 RED。独立审阅另实证原代码整数标记的 list/status 两次应成功而实际拒绝。随后新增 `_finite_tool_metadata`，仅在 tools/list、tools/call 允许空对象或唯一 progressToken，其类型必须精确 int、范围 `0..2^63-1`。string/bool/float、负数、超界、嵌套内容和额外字段继续拒绝；ping 仅空 metadata，resources/prompts/custom methods 继续关闭。业务 handler 只收到 name/arguments，没有传入进度标记，不发布进度或 trace。

MCP 标准允许整数或字符串标记，允许服务不发送进度；非负和上限是本机受限配置，并非标准要求。这里未实现全范围 progress utility。[MCP 2025-06-18 progress](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress)。所有业务 DTO 仍只在 domain.py，schema、默认/QCC/mock/真实模型门及领域文件均未改变。

## 实际命令与分母

父审计脚本位于忽略目录 `.audit-local/plugin-host-install-root/`；表中 pytest 均实际以 `.venv/Scripts/python.exe -X utf8 -m pytest` 执行，其他 Python 命令使用同一解释器。API 数量与独立辅助断言不并入 pytest 数量。验收使用当前固定虚构材料；未重跑84项完整能力 CLI、40材料 sampler、Word 或浏览器旅程，不据历史通过声称本轮重验。

|命令或接口|退出码|实际结果|
|---|---|---|
|实际 CLI 帮助/公开协议只读检查|0；两次 scope 参数错误2|宿主无 project scope 安装参数，使用项目目录/配置；辅助参数错误不是功能 RED|
|`probe_adapter.py` 初版|1|取响应安装字段位置错误，实际已识别服务；保留辅助 KeyError，非产品 RED|
|`probe_adapter.py` 第二版|0|installed/enabled true、服务名存在；toolsError 为实际功能失败|
|`probe_handshake.py`|0|目标单服务诊断；确认 initialize 成功、整数 progressToken list 被拒绝，诊断没有修复代码|
|`pytest -q tests/integration/test_mcp_host_metadata.py --tb=short --junitxml=.audit-local/plugin-host-install-root/metadata-red.xml`|1|4 failed / 0 errors，4.64秒|
|`pytest -q tests/integration/test_mcp_host_metadata.py tests/integration/test_mcp_offline_stdio.py tests/unit/test_mcp_offline.py --tb=short --junitxml=.audit-local/plugin-host-install-root/metadata-green.xml`|0|84 passed，0警告，24.93秒；3允许标记测试+37次拒绝探针及恢复属于4个正式新测试|
|最终 `probe_adapter.py`|0；宿主子进程自然0|真实 installed/enabled true；服务恰两工具，toolsError null；filtered target 启动，没有模型 turn 请求|
|`installed_adapter_calls.py`|0|从实际缓存声明发起40次 SDK API 请求：initialize/list 各1，工具调用38（24示例+2状态+12拒绝）；stderr空；非宿主聊天调用，无 SDK 子进程退出码断言|
|独立进度边界探针|0；子进程自然0|113检查/110直接 STDIO 请求；此前原入口2项实际 RED，非法方法/metadata/业务参数仍拒绝|
|独立最终包与协议核验|0|32检查；5源/5缓存 exact byte-match、90当前绑定，仅入口旧hash失效；原7文件/ZIP与旧证据保留|
|独立边界最终保存/原生schema核验|各0|23保存及宿主transcript检查、7原生schema检查；与113协议检查及32格式检查分别记录|
|`checks.py` 的 defaults/config/schema/pip|各0|默认hash、配置、唯一schema和安装依赖兼容通过|
|`verify_sources.py --mode development`|0|13来源实际核验；13生产批准警告保留|
|`verify_sources.py --mode release`|1|9实际批准/依赖阻断，非生产 PASS|
|`verify_runtime_dependencies.py --mode development`|0|55 runtime+1 build 核验；native_build_verified false|
|`verify_runtime_dependencies.py --mode release`|1|59实际批准/组件/生产阻断|
|完整 `pytest -q --tb=short --junitxml=docs/testing/PLUGIN-local-host-results.xml`|0|1020 passed，0警告，338.32秒；原生数量=JUnit1020，0 failure/error/skip|

早期活动宿主 proxy 连接因 Windows socket 错误10050退出1，未建立连接。独立 app-server 的 thread/loaded/list 实际为空，不能将持久线程ID视为已加载；没有创建、resume 或启动模型 turn 来绕过这一限制。宿主聊天 `mcpServer/tool/call` **NOT_RUN**；下一步复用目标宿主已经加载的原聊天，验证工具发现/调用权限，工具主动选择另行验收。[公开 app-server 接口](https://learn.chatgpt.com/docs/app-server)。这些实验协议不是稳定生产接口。

## 绑定、保留与阻断

原七文件包与 `dist/qx-contract-offline-local-0.1.0.zip` 保留，ZIP SHA256 `f61b41c11b707474f971f99a84ad4bab83c7835cf4cc856ae1c96d2bbfb54905`。原绑定的 offline_server.py 旧hash `75835bb9606e17a8d66a9563a66447d4e0b5a3bb6b3f553e4cb6f9c109568f73` 已过时，原包 README/绑定中的未安装状态是历史生成快照；不能当当前宿主或当前90项证明。新绑定90项匹配当前内容，入口hash `bea040305629ddc23dfa05a5a9dd2ad17696d08bfa77b4ff93981f86bdfd9076`；其 host_installation 字段明确是冻结时 NOT_RUN，真实后续结果以本阶段独立记录为准。清单不自动强制hash，也不提供 OS 隔离。

当前**工程安装和发现已验证**；聊天实际调用/模型选择、网页 ChatGPT 连接、独立异机分发、帧/OS硬限、可信案件身份/文件桥、真实 DeepSeek transport/费用与数据批准、QCC账户/许可/律师批准、法律 gold、影子与生产仍未完成或阻断。没有真实模型/企查查工具调用、真实材料外发、付费、外部注册或发布。宿主正常 bootstrap 与公开文档访问不等于 OS 全网捕获，不能宣称整个宿主零网络。

完整1020包含前阶段1016和本阶段4项，不与84目标/独立辅助检查相加。完整JUnit SHA256 `5152b51e48d44caa4687560ad770cafc9da771972809f79dab6d09ef1be83a87`。私有证据包括 `adapter-read-and-discover-final.json`（真实 native 协议）、`adapter-source-freeze.json`、`installed-adapter-calls.json`、原失败/诊断、两份 JUnit 和 `checks-summary.json`；格式独审另在 `.audit-local/plugin-host-install-schema-review/`、边界独审在 `.audit-local/plugin-host-install-boundary-review/`。

父最终保存核验退出0：起始625个tracked文件中620个原字节不变；5个已声明修改为 README、TASK_STATUS、复用映射、offline_server 和既有测试命名。原7文件源包/ZIP不变，全局config不变，新5文件/cache相同、新90绑定全匹配。新增文件在Git提交前另核对；没有整仓替换。父新审计63文件封证 `SEALED.json` SHA256 `0dc5bed3d6cb859839d1189d2f12b59a1e8966f80034a78fce6659be4b558424`；旧封证保留。

独立格式最终报告 SHA256 `e4c54dfd8bff343278157e49760bef1bb59ac2e017dd2f8f0faf42dba4d7d002`；边界报告 `9a7c4f6b7c157787dd8e22ae1fcc645f7f81101fd0e1108d9bfc2de17cc36736`、其封证 `ac0625855768834e522813fa12ca1675d85eb65f61e8c879ead8954bd76d3075`。格式独审时阶段文档尚不存在的备注已由父补齐本文件解决；未修改独审历史文字。封证范围为私有审计文件，不能当外部生产批准或整个安装环境证明。
