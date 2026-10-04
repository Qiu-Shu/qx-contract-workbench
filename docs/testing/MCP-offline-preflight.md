# 首批本机离线 MCP 预检实际记录

2026-10-04，证据时间UTC，workspace `D:\Documents\ChatGPT\律所项目`，基线`382850d78d1e8c69d7687c5821bafd7c97f6c847`，沿`codex/contract-review-v2`。本轮仅只读核验与候选设计；新增工作台MCP源代码、正式目标测试、实际STDIO启动及宿主连接均未实施或NOT_RUN。上一批936通过是其历史结果，本轮不重跑或冒称新原型通过。

用户要求继续最终ChatGPT插件方向，真实DeepSeek调用仍暂不开始。已在聊天提交两工具短设计确认：无案件的能力状态，以及服务器固定四份独立虚构材料的离线codec示例；客户端仅fixture/operation/model枚举，不能提供原文、raw响应、token、路径、URL、身份、价格、预算或批准。确认回复截至本预检保存时尚未收到；不把记忆笔记中的建议prompt当作用户的设计批准。

## 现状差距与复用

|当前实际能力|首批可复用|仍未实现或验收|
|---|---|---|
|DeepSeek三纯函数、唯一domain三DTO，OFFLINE_ONLY/protocol_only|固定请求构造、人工响应解析、明确unknown费用；新业务DTO仍仅domain|真实模型transport/费用账本/价格与数据批准|
|已装MCP/mcp-types2.2.0、T07本机模拟客户端与测试server|MCPServer、公开middleware、stdio客户端/服务端、现测试模式|工作台入站MCP模块和正式两工具；QCC客户端不作为入站server|
|四个固定独立虚构DOCX与规范hash|固定fixture key，服务器自选原文及人工响应；无任意用户材料|真实文件入口、下载桥与案件读取|
|原会话/成员/版本/批准/精确mock注册门|保持原代码；后续案件MCP须复用实际授权|OAuth或宿主身份到内部principal的可信桥；本批无案件，不能冒称跨案鉴权已验收|
|源码/运行锁、G13 MIT全文与固定wheel|既有开发runtime；无需新包或升级|生产批准仍空，未扩大transitive许可或OTel数据范围|

## 两独立预检的实际结果

复用审阅私有报告`.audit-local/mcp-reuse-audit/REPORT.md`，原始命令与退出`.audit-local/mcp-reuse-audit/commands.json`。已装SDK6/6源文件与固定mcp wheel逐字节一致，wheel及G13 MIT全文hash与锁一致；不是完整上游源码审核，也不把所有传递组件声明成MIT。

仅复跑已有`tests/integration/test_mcp_transport.py`作兼容性核验：首轮UTC13:55:49.655414，exit1，20 collected/10 passed/10 setup errors，JUnit1.239秒；原因是私有basetemp父目录不存在导致WinError3，未进入相关fixture，不计功能RED。创建审计目录后同文件UTC13:56:01.802370，exit0，20 passed/0 failure/error，JUnit5.393秒。原日志与JUnit保留；没有新增产品正式测试。复用探针首次把middleware结果dict误作model_copy而exit1也保留，属于探针脚本错误。

纯SDK内存探针实际确认无参函数收到额外actor/path仍被静默忽略：3次call、2次执行、未知工具为is_error。随后公开middleware可行性探针实际2次call、1次执行、1次额外输入拒绝，发布schema明确additionalProperties=false。该结果证明SDK接口可用，不是工作台工具或STDIO产品验收。

安全审阅私有报告`.audit-local/mcp-safety-audit/REPORT.md`与`evidence.json`。实际捕获20个选定项目/SDK源hash，3个内存SDK探针exit0：无参extras接受后丢弃、ValidationError反射人工canary、未知工具错误反射人工name。它们是SDK风险证据；新增正式功能测试0、工作台server启动0、该审阅网络调用0。

## 需落实的边界与未解除项

工具入口须在公开middleware看到的原始arguments上做exact对象/字段白名单验证，拒绝未知工具及多余字段，不能只靠函数类型或只读注解。错误必须固定脱敏，不能返回调用者原文、工具名、URI、路径或ValidationError；资源/prompt等未开放入口也须安全处理。默认SDK OTel会把method/name/id写入span，须显式关闭或移除并实测日志与wire；ERROR级别不代表没有遥测。

已装SDK STDIO按整行读后解析，源码预检未见本项目帧限制。首批仅在父进程控制的有限虚构输入下验证；`TRANSPORT_FRAME_LIMIT_NOT_ESTABLISHED`、`OS_CPU_MEMORY_SANDBOX_NOT_ESTABLISHED`须保留，客户端限长/超时不冒作服务端或OS防御。标准stdio_client会合并默认环境白名单，env={}不能声称完全无环境继承；工具不读真实key与SDK的OS进程启动分别观测。

|状态|准确范围|
|---|---|
|DESIGN_CONFIRMATION_PENDING|已提交本轮两工具短设计，尚未收到用户确认；不写产品或正式tests|
|NOT_IMPLEMENTED / NOT_RUN|工作台MCP入口、两工具、STDIO握手/发现/调用/退出；宿主安装、插件包、ChatGPT连接|
|NOT_ESTABLISHED|STDIO外层帧与OS CPU/内存硬限制；不得将有限示例说成公网安全服务|
|BLOCKED|真实模型/QCC/付费/真实材料、生产许可/法律gold/可信实际批准、OAuth/文件桥/真实托管|

ChatGPT接入还需在目标宿主实际发现与调用工具，并具备公有HTTPS或Secure MCP Tunnel等可达连接；本地stdio本身不构成网页已连接。公开提交另需稳定公网HTTPS，开发连接也受账户/工作区权限限制。[官方连接验收](https://developers.openai.com/plugins/deploy/connect-chatgpt)、[官方server要求](https://developers.openai.com/plugins/build/mcp-server)。本轮只读取这些公开页面，没有建账号、隧道、外部项目或接受协议。

根只读定位曾遇Windows rg通配路径及旧SDK目录猜测错误；官方.md地址返回不支持text/markdown，改读取实际HTML页。均为辅助读取，不计产品RED。本轮没有变更业务源码、正式tests、原件/来源/依赖锁，没有真实供应商请求或材料外传。下一步只在本轮设计确认后实施相应失败测试、最小包装、真实STDIO调用、关联回归与独审，保留实际数量和以上接入阻断。

根UTC14:00:53.025456实际重算上一批full-post的666文件，差异0；独审20选定hash比较只出现TASK_STATUS与目标映射两份明确的结果文档变化，其余代码/SDK相同。原失败/复跑JUnit及两独审报告/证据SHA保留于`.audit-local/mcp-root-preflight/verification.json`，没有重写任何独审证据。UTC14:00:54.371530首次暂存核验exit0：精确三份预检/状态文档，index与工作副本按既有LF一致，staged秘密pattern扫描3/findings0、diff检查0；限定pattern不等于全面敏感分类。无新产品代码、正式tests或依赖进入本批暂存。本段为首检后结果追加，提交前另核实际最终索引；设计确认仍待回复，不以文档提交冒作MCP实现完成。
