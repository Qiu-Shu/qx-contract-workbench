# 本机离线插件连接源包验收

记录日期 2026-10-04，证据时间 UTC，显示时区 Asia/Shanghai。基础提交 `63637d9049a8a172023ba8bef2f61c028c039b2b`，沿 `codex/contract-review-v2` 增量工作。状态 **LOCAL_SOURCE_PACKAGE_VERIFIED；HOST_NOT_RUN；CHATGPT_CONNECTION_NOT_RUN；PRODUCTION_BLOCKED**。

用户“继续”承接已验证的两工具及最终 ChatGPT 插件目标。本阶段只把现有入口封装成可核对的本机连接源包，没有改业务行为、重新实施 T00–T13、安装宿主插件、建立外部账户或上传制品。没有新增运行依赖、案件权限、Skill、UI、OAuth、文件桥、HTTP 或隧道。静态连接清单及新作图标属于可逆低影响封装，未为它们添加镜像实现的单元测试或虚构功能 RED；现有业务目标回归和实际解压调用另行执行。

## 制品与复用

源目录 `plugins/qx-contract-offline-local`，版本 `0.1.0`；制品 `dist/qx-contract-offline-local-0.1.0.zip`，**10,399 bytes，7 个文件，一个同名根目录**。SHA-256：

```text
f61b41c11b707474f971f99a84ad4bab83c7835cf4cc856ae1c96d2bbfb54905
```

`dist/` 按现有 Git 规则忽略，保留本机交付；七份来源文件进入版本控制。包内实际为 `plugin.json`、`mcp.json`、`.codex-plugin/plugin.json`、`.mcp.json`、`runtime-binding.json`、`README.md` 和 `assets/offline-document.svg`。没有随包加入应用源码、虚拟环境、依赖、合同、审计目录、原包 A 或凭据。

|组件|复用/封装|实际限制|
|---|---|---|
|STDIO 服务|原 `cn_contract.mcp.offline_server`，同一 Python3.12.14/MCP2.2.0 环境|仍只有 `workbench_status` 与 `deepseek_offline_example`|
|通用清单|根 `plugin.json` 和带 `type: stdio` 的 `mcp.json`|包内组件引用可移动；不代表 runtime 可独立移动|
|Codex 兼容清单|同步身份/版本/展示信息；`.mcp.json` 省略通用 schema/type|完整宿主解析及安装未执行；本地结构检查不冒称官方校验|
|运行绑定|现有绝对 Python 路径、参数数组与项目 cwd；90 个所选仓库文件 hash|记录供核对，不会由清单自动执行 hash 门，也不是依赖/OS 完整证明|
|图标|本项目新作64×64 SVG；两份清单指向同一包含文件|无脚本、远程资源或品牌身份验证声明|

两份配置均实际指向 `D:/Documents/ChatGPT/律所项目/.venv/Scripts/python.exe`，参数 `-X utf8 -m cn_contract.mcp.offline_server`，cwd 为当前仓库。解压后的配置有意调用原仓库；实际模块来源已核验为 `src/cn_contract/mcp/offline_server.py`，并匹配原 SHA-256 `75835bb9606e17a8d66a9563a66447d4e0b5a3bb6b3f553e4cb6f9c109568f73`。不能把这一结果写成独立 runtime 分发或异机部署成功。

## 本阶段实际命令及结果

统一解释器为项目 `.venv/Scripts/python.exe -X utf8`。根辅助 runner 在新 `.audit-local/plugin-package-root` 中保留每命令 argv、UTC、实际子退出码、stdout/stderr hash；runner 的外层退出0不代替子命令结果。没有覆盖上一阶段封证。

|命令/验收|实际子退出码|实际结果|
|---|---:|---|
|`baseline.py`|0|617 个原已跟踪文件取样；构建完成时617/617原始 bytes 不变|
|`build.py`|0|七文件白名单打包；CRC及七份 source/ZIP bytes 相等；90项运行绑定|
|`inspect_and_smoke.py`|0|新目录解压；两种清单各初始化/发现并调用，4次状态、48组固定示例、12次拒绝，恢复后状态仍关闭；两次SDK session关闭、stderr为空|
|`pytest tests/unit/test_mcp_offline.py tests/integration/test_mcp_offline_stdio.py -q --tb=short`，附原生收集和JUnit记录|0|**80 passed，0 fail/error/skipped/warning**；原生80逐项等于JUnit80；pytest20.67s，命令21.234s|
|`scripts/verify_defaults.py --file config/defaults.json`|0|默认语义hash仍为 `0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887`|
|`-m cn_contract.cli schema --check`|0|唯一领域 schema 核对通过|
|`-m pip check`|0|No broken requirements found；无安装或新增依赖|
|`scripts/verify_sources.py --mode development`|0|13来源，errors=[]，保留13个生产批准警告|
|同来源 `--mode release`|1|**9个实际生产阻断**，没有把非零改成PASS|
|`scripts/verify_runtime_dependencies.py --mode development`|0|55应用/测试+build1，errors=[]，network_calls=0，native_build_verified=false|
|同依赖 `--mode release`|1|**59个实际生产阻断**，network_calls=0|

根调用 UTC `14:48:49.425676–14:48:52.171348`；回归 UTC `14:48:47.577868–14:49:08.817794`。48组是两种配置各4×3×2的人工离线协议调用，不是48份合同法律审查或真实模型请求。12次拒绝覆盖额外身份、路径、原文、非法fixture/model、未知工具。结果均保留 `OFFLINE_ONLY / protocol_only`、人工响应/token、费用 `None / unknown / USD`、`legal_opinion=false`。普通SDK/Python初始化有系统环境继承；工具不读取凭据与整个进程环境隔离是不同结论。

新回归JUnit SHA-256 `2c9139cfe51d0644c3624e4e27b9b4e031ad85a1d0f06fbded2ef05b96146b97`；原生nodeids SHA-256 `0cc1094022a20c4529050e86dcdaf371fb7fd30c768f5f93c449747205210cdd`。证据路径分别为 `.audit-local/plugin-package-root/regression.xml`、`regression.nodeids.json`、`regression.json`、`package-smoke-evidence.json` 和 `build-evidence.json`。

根最终 `final_verification.py` 实际退出0：原617已跟踪文件中614份 bytes 不变，仅README/状态表/目标映射三份说明更新，新增七份包源及本报告；全部原src、tests、sources、schemas、rules、prompts、config均未修改。90绑定hash、七源文件及ZIP继续冻结；独审五份报告/证据及上一阶段1016的JUnit hash逐一匹配。三类限定秘密模式在本次11文件命中0，不声称全面敏感分类。结果保存在新 `.audit-local/plugin-package-root/final-verification.json`，没有覆盖历史失败或封证。

此前完整1016项通过是[上一阶段](MCP-offline-parent.md)的实际结果，本阶段没有重跑整个1016、84能力CLI、40份材料、Word或普通浏览器。不相加不同回归分母，也不以清单检查替代法律金标准或真实宿主验收。

## 独立审阅与校验能力

格式审阅实际18/18结构检查通过，五份JSON可读且无重复键，七份ZIP文件与来源相同，90/90绑定hash匹配。检查本机CLI `0.159.0-alpha.12.1` 的10次只读帮助/版本/协议schema命令，九次退出0，`codex plugin validate --help`退出2（未支持此子命令）。实际生成440份app-server协议JSON，其中26份名称含plugin；这些是协议schema，不能拿来当插件清单schema。未找到可用完整插件包验证器，官方完整schema验证明确 **NOT_RUN / VALIDATOR_UNAVAILABLE**。

格式审阅初次辅助脚本误把 `expected_tools` 列表当数量，保留退出1，再修正辅助检查；未改变制品，不计产品RED。图标要求在静态预检中发现并在打包前补齐，未声称初始无图标方案已通过宿主验证。审阅报告 `.audit-local/plugin-package-schema-review/REPORT.md` SHA-256 `20685298500ec84299b436bb251f99019c78d384e92d1d561545de252b39b0be`，`candidate-inspection.json` SHA-256 `3e0197b68d98eec2d7014aeea2f67fcc7339a6852e98edde0c2e6c163ad0e55a`。

边界审阅独立新目录解压，七文件白名单、90绑定hash及86份源/default/fixture快照相等；使用解压配置的实际command/cwd，确认原仓库模块，再初始化/发现两工具、24组示例、10次拒绝、拒绝后恢复状态。最终75项独立检查通过，实际38个协议请求，子进程EOF自然退出0，stderr与额外stdout为空。初次辅助脚本错误要求通用/兼容JSON整体相同；改为共享元数据及配置语义相同后通过，初始失败保留，不计产品RED。边界报告 `.audit-local/plugin-package-boundary-review/REPORT.md` SHA-256 `2ba2d7d143d8ab026f844f3477cb1122b8bd8bc9e03a996c585590a63defaaea`；最终证据 SHA-256 `27f471f9d6de044af941fc8c675c8fd9d442e997a8b781f336ef6a67b097d350`；独立封证 SHA-256 `fc9dbb9efb911f8c3d876e27c1bd3e905040fc86250df7eff341e3325c74d03f`。全部属于有限源包/受控调用检查，分母不与pytest相加。

## 阻断表与后续验收

|项目|状态|解除条件|
|---|---|---|
|源包文件/实际配置调用|LOCAL_SOURCE_PACKAGE_VERIFIED|当前本机绑定范围；迁移或修改后重新核验|
|官方完整包schema/宿主解析|NOT_RUN / VALIDATOR_UNAVAILABLE|可用目标验证器或实际安装解析结果，不能借结构断言代替|
|本机宿主安装及会话内工具发现/选择|NOT_RUN|通过目标宿主支持的安装流程，实际新会话发现及调用；本阶段未修改全局配置或marketplace|
|ChatGPT网页实际连接|NOT_RUN / ACCESS_TRANSPORT_PENDING|目标账户/工作区开发权限；已核验可达HTTPS或Secure MCP Tunnel；实际发现/调用并留证|
|真实案件身份/文件桥及案件工具|NOT_IMPLEMENTED|可信宿主身份绑定后端会话/成员、撤销/跨案/版本测试、受控文件桥；沿现有服务增量实现|
|真实DeepSeek及企查查|DISABLED / BLOCKED|用户范围仍为离线；许可、数据政策、现实批准、价格和费用链路分别建立|
|正式签发、律师gold、影子与生产|BLOCKED|原T13现实批准与能力缺口逐项解除；源包和mock不能授权上线|
|帧与OS CPU/内存硬限|NOT_ESTABLISHED|独立进程/部署保护及对应实测，不能由插件元数据宣称完成|

格式依[官方包结构](https://developers.openai.com/plugins/build/plugins)及[字段/图标说明](https://developers.openai.com/plugins/deploy/submission)，实际连接依[官方验收流程](https://developers.openai.com/plugins/deploy/connect-chatgpt)，均2026-10-04核对。按所读插件创建技能的本机源包路线保持原服务，源包不上传账户、不注册外部插件、不接受第三方条款。没有新lawyer approval、密钥配置、真实资料处理、付费或供应商请求，也没有生产完成声明。
