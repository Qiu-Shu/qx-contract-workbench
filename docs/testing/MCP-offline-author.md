# 首批本机离线 MCP 作者实际记录

日期2026-10-04，证据时间UTC，workspace `D:\Documents\ChatGPT\律所项目`，沿`codex/contract-review-v2`，本轮基线`efc6b56`。用户在两工具有限设计及未完成说明后明确“继续”；本轮仅实施受控本机STDIO虚构数据入口。作者目标及关联回归通过，独审与根全套验收由父任务另行记录；本记录不宣称生产完成或ChatGPT已连接。

## 实际变更

- 新入口`python -X utf8 -m cn_contract.mcp.offline_server`使用已装、原锁定G13的MCP2.2.0公开`MCPServer`、`Tool.from_function`及middleware；仅启动STDIO。没有安装依赖、插件、HTTP、账户、隧道或托管。
- 恰好两个工具：空业务参数`workbench_status`；必需且严格枚举`fixture`（sales/service/lease/nda）、`operation`（extract_facts/review_chunk/review_cross_clauses）、`model`（deepseek-flash/deepseek-v4-pro）的`deepseek_offline_example`。发现schema均`additionalProperties=false`；公开middleware在SDK校验/类型转换前检查原始arguments，拒绝多余字段、缺字段、错误类型与枚举、未知工具及未开放resource/prompt等方法。
- 唯一业务DTO仍在`domain.py`新增`McpOfflineExampleArguments`、`McpOfflineStatus`、`McpOfflineExample`，并引用既有DeepSeek模型/操作Literal与回复DTO。未改变ReviewRun、既有schema、defaults、Provider/mock注册、审批、签发、费用ledger或egress。
- 状态明确synthetic/OFFLINE_ONLY、真实模型/QCC关闭、生产阻断、法律审查不可用、ChatGPT连接未验证；传输帧及OS CPU/内存硬限制仍NOT_ESTABLISHED。
- 示例从原T06登记四份独立虚构DOCX自行取得数据：固定fixture键→固定文件名→有界读取（最多16384+1字节）→登记SHA-256一致才检查固定`word/document.xml`（8192字节上界）→最多32个文本锚点。用户不能给原文、raw响应、路径、URL、key、token、rates、actor或approval。fixture返回键及登记hash，不返回本机存储路径。
- 请求和人工固定响应复用既有`build_chat_request`/`decode_chat_response`，不调用估价。响应/固定100输入20输出token明确人工构造、非供应商、非法律意见；`cost=None`、`pricing_status=unknown`、`unit=USD`。原lease里的注入文本只作为quote数据。
- 固定错误正文不反射工具名、用户输入、URI/路径、ValidationError或request id；标准JSON-RPC信封继续回传合法id作关联。STDIO stdout实际仅协议帧，所测子进程stderr为空。
- 通过SDK公开middleware列表替换默认OTel及requestState边界；本入口不支持requestState或非空trace metadata。SDK客户端自动发送的空协议`_meta={}`仅在顶层兼容；工具arguments仍exact。非dict/非空metadata拒绝，不作宽泛放行。

正常导入既有`review.deepseek_codec`/`review.synthetic`会经过原`review/__init__.py`，并传递import既有workflow/validator/model_adapter/security/persistence；security创建既有随机dummy password hash。本轮不重构旧包初始化，不把模块导入说成实际业务调用。本入口不执行这些服务、不访问案件DB、环境凭证、真实模型或外部网络；目标测试也实际禁用env/SQLite/socket connect后成功调用示例，status禁用文件打开后仍返回。

## RED、修复与验证

每轮均独立保存原生`pytest --collect-only -q` nodeids和JUnit，命令、UTC起止、pytest实际退出码及数量在`.audit-local/mcp-offline-author/<轮次>-commands.json`。下表命令统一前缀为`.venv/Scripts/python.exe -X utf8 -m pytest`；pytest输出、nodeids及XML均保留，不覆盖旧证据。

|轮次/运行UTC|实际命令范围|collect exit/count|run exit/实际结果|判断|
|---|---|---|---|---|
|red-missing / 14:13:04.268751|`tests/unit/test_mcp_offline.py tests/integration/test_mcp_offline_stdio.py -q --tb=short --junitxml=.../red-missing.xml`|0 / 63|1 / 63 failed，0 errors|有效功能RED：importlib探测后明确断言包/入口/DTO缺失；无collection或导入异常充当RED|
|green-initial / 14:14:21.646038|同两目标，XML为green-initial|0 / 63|1 / 62 passed，1 failed，0 errors|实际SDK客户端发现被拒绝；其余目标已通过，保留失败|
|red-sdk-metadata / 14:15:28.192107|`tests/integration/test_mcp_offline_stdio.py`，XML为red-sdk-metadata|0 / 5|1 / 3 passed，2 failed，0 errors|新增空metadata wire回归也失败，确认兼容根因|
|green-sdk-metadata / 14:15:53.612811|同两目标，XML为green-sdk-metadata|0 / 64|0 / 64 passed，0 failure/error|最小兼容修复闭合|
|green-boundaries / 14:17:33.062163|同两目标，XML为green-boundaries|0 / 74|0 / 74 passed，0 failure/error|补强边界及实际OTel禁用观测通过|
|green-associated / 14:17:51.188145|上述两目标+`tests/unit/test_deepseek_codec.py tests/unit/test_domain.py tests/unit/test_model_schema.py tests/integration/test_mcp_transport.py`，XML为green-associated|0 / 342|0 / 342 passed，0 failure/error|新74与必要关联268实际回归通过|

共6轮、12个实际pytest命令（6次native collect、6次执行），各轮native收集数量与JUnit数量相同。父进程证据编排脚本自身的exit0表示记录完成，pytest的RED exit1始终保留在commands JSON及上表；没有把RED写成PASS。普通全套本作者NOT_RUN，由父任务统一运行；历史936不是本轮结果。

根因调查读取实际SDK `JSONRPCDispatcher.send_raw_request`：它即使无trace provider也总加入`_meta={}`，故原顶层“完全无extra字段”规则使真实SDK tools/list失败。标准库不发此字段时成功。先保留失败与新增最小wire失败回归，再只允许顶层空dict；7组None/bool/int/string/list/非空trace/非空private metadata各对list与call进行实际拒绝，工具内部`arguments._meta`仍拒绝。使用systematic-debugging、TDD及writing-good-tests参考；未对SDK私有manager做patch。

74个正式目标包括24组fixture×operation×model实际codec往返、枚举/类型/extras拒绝、hash漂移拒绝、固定lease注入仅作数据、状态读范围和无env/DB/network行为，以及13个集成测试。集成含12个标准库启动的受控真实child与1个SDK stdio_client实际child：initialize→发现→成功调用/安全拒绝→关闭。标准库child关闭stdin后自然exit0并检查stderr；SDK按其受限关闭流程退出transport上下文，不能把客户端超时/Windows job控制当成本server的帧或OS资源隔离。

OTel目标测试在独立真实child通过公共`set_tracer_provider`安装并校准trap：任一server span尝试会抛人工canary；实际initialize/list/成功示例/未知工具拒绝和自然退出全部成功且stderr空，证明本server默认OTel边界未执行。SDK客户端自身可能具有SDK的client telemetry代码，与server默认middleware禁用是不同边界；测试没有配置出口或真实追踪账户。

## 未完成与待审

这是固定虚构数据的离线协议入口，不能上传真实合同、抽取或审查实际案件、签发意见或查询QCC；没有真实模型调用、费用账单/价格批准、OAuth或身份桥、文件桥、宿主插件包、ChatGPT真实连接、HTTPS/托管/隧道或生产批准。帧硬限、OS CPU/内存sandbox仍未建立；有限虚构输入测试不等于公网或任意输入安全服务验收。法律gold、律师规则批准、许可与数据政策阻断保持原状态。

待独审核对原始arguments是否有旁路、错误/日志/OTel是否反射人工canary、fixture范围和hash拒绝、Registry/工作流隔离及既有行为回归。父任务另负责实际全套、基线漂移、defaults/schema/来源封证、状态更新和记忆保存。本作者没有修改TASK_STATUS/README/目标映射，没有commit/push或派子agent。
