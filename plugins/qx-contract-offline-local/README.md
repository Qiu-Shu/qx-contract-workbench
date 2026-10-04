# 群兴合同审查·本机离线连接源包

版本 0.1.0。此包只有连接清单、说明、图标和运行绑定记录；必须保留本机现有仓库及 `.venv`。包内没有应用源码、Python、依赖或合同。使用通用插件清单格式，不代表可独立迁移运行，也不是已安装或已连接 ChatGPT 的插件。

## 当前可用内容

|工具|参数|结果范围|
|---|---|---|
|`workbench_status`|空对象|离线能力与阻断状态，不读取案件|
|`deepseek_offline_example`|fixture：sales/service/lease/nda；operation：extract_facts/review_chunk/review_cross_clauses；model：deepseek-flash/deepseek-v4-pro|服务器选择四个登记虚构文件；请求与响应均为离线人工协议示例，费用为 None/unknown/USD，legal_opinion 为 false|

例如 `{"fixture":"sales","operation":"review_chunk","model":"deepseek-flash"}`。额外原文、路径、URL、密钥、token、价格、身份和批准不受支持；固定示例不能启动案件审查或真实供应商请求。

## 运行绑定

两份 MCP 清单均使用现有入口：

- command：`D:/Documents/ChatGPT/律所项目/.venv/Scripts/python.exe`
- args：`-X utf8 -m cn_contract.mcp.offline_server`
- cwd：`D:/Documents/ChatGPT/律所项目`

这是本机绝对路径绑定。解压源包后的配置仍有意运行现有仓库，没有随包复制 runtime。`runtime-binding.json` 记录基础提交、已安装版本及关键文件 hash，供核对；清单不会自动执行这些 hash 检查。移动项目、重建环境或更新源码后，应重新核对、调整两份 MCP 清单与绑定记录，再运行测试。普通 Python/SDK 初始化可能读取系统环境，源包不声明整个进程无环境继承或已受 OS 沙箱隔离。

## 包结构与核验

`plugin.json`/`mcp.json` 是通用清单；`.codex-plugin/plugin.json`/`.mcp.json` 是同步的 Codex 兼容清单，图标为本项目新作的简单文档 SVG。没有新增 Skill、案件权限、账户映射、文件桥、生命周期钩子或外部服务 URL。元数据中的项目名不是外部平台已验证的发布者身份。

准备接入宿主时，需要分别核验初始化、仅发现两个工具、状态调用、虚构示例、非法参数拒绝和正常停止。直接启动后等待协议输入，不会打开网页。源包检验及当前具体限制记录在项目的 `docs/testing/PLUGIN-local-package.md`；该报告在仓库中，不在 ZIP 内。

## 仍待完成

宿主安装与工具发现验收尚未执行。本包没有进行账户上传、注册 marketplace、修改全局配置或公开提交。ChatGPT 网页连接另需目标账户/工作区权限及可达传输；本机 STDIO 清单本身不能建立网页连接。当前没有 HTTPS 端点或 Secure MCP Tunnel。

真实 DeepSeek、企查查、真实材料、正式签发、律师金标准与生产继续阻断。帧大小和 OS CPU/内存硬限尚未建立；现有开发许可核对不等于生产许可批准。工程示例通过不能作为法律准确率、完整合同审查、真实试点或生产完成的证据。

## 格式来源

依据 2026-10-04 核对的[官方插件包格式](https://developers.openai.com/plugins/build/plugins)、[清单字段](https://developers.openai.com/plugins/deploy/submission)及[连接验收说明](https://developers.openai.com/plugins/deploy/connect-chatgpt)。采用现有可运行服务，保留原件、来源锁、审批门和默认关闭状态。
