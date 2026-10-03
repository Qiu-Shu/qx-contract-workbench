# T07 独立审阅

状态：ENGINEERING_SYNTHETIC_REVIEW_PASS（2026-10-03）；基线 fe7c9885ede7409634130c6b1452438b1bb7d597，workspace D:\Documents\ChatGPT\律所项目。未发现尚未闭合的P1/P2；不代表真实QCC、试点许可或生产完成。

已预读 v2.0 T07、唯一 ProviderConfig/ToolCatalog/BindingInput/ToolBinding/ProviderResult DTO、T07-detail、51包候选审计。候选缓存、静态SDK核对与离线dry-run不能替代安装/运行证据。作者先独占正式依赖合并与离线安装，再交接可测API。

待独立实证：实际session/owner/member；服务器不可变binding批准与撤销；完整input/output schema漂移及参数校验；mock与live身份隔离；无反射任意transport/endpoint；secret不入结果/error/log；未知工具和T08未完成的live请求0dispatch；真实固定mcp2.2.0/httpx2 SDK本机synthetic握手/发现/调用与有界超时；受保护raw引用/未知账单；caller事务失败无半写。只在API和包已可测后运行，不把不存在模块或导入错误算业务RED。

独立代理不安装、不修改业务或正式测试、不联网外查、不spawn、不运行root全套/demo、不提交、不写memory。父节点统一处理项目记录。最终同一冻结工作副本封SHA。真实QCC/账户/付费/法律效果/生产状态继续阻断。

所有命令前缀为 `.venv/Scripts/python.exe -X utf8 -m pytest`，独立文件位于 `.audit-local/t07-review/`，使用 `-q --tb=short`（初始API/roles用`--tb=line`）和下表JUnit。每轮在当时作者共享工作副本真实执行，阶段结果不能替代最终冻结回归。

|阶段|文件/范围|JUnit|退出码|实际数量|
|---|---|---|---:|---|
|角色首业务RED|test_role_separation.py|roles-initial.xml|1|1 failed / 2 passed|
|API首次|test_api_attacks.py|api-initial.xml|0|40 passed|
|角色+SDK首次辅助错误|test_role_separation.py test_sdk_attacks.py|roles-sdk-first.xml|1|6 failed / 3 passed|
|适配新API后的真实业务RED|同上|roles-sdk-adapted.xml|1|1 failed / 8 passed|
|扩展独立攻击|test_role_separation.py test_api_attacks.py test_sdk_attacks.py|expanded-first.xml|1|1 failed / 53 passed|
|真实SDK错误原始证据RED|test_sdk_attacks.py::test_sdk_error_invalid_output_retains_received_raw_evidence|received-raw-first.xml|1|1 failed|
|partial/raw独立闭合|SDK上述partial和raw两项|partial-raw-fixed.xml|0|2 passed|
|扩展SDK error边界|test_sdk_attacks.py|sdk-error-boundary.xml|1|1业务 failed + 1辅助 failed / 8 passed|
|动态引用真实网络RED|SDK dynamic_ref input/output两项|dynamic-ref-first.xml|1|1 failed / 1 passed / 1 warning|
|回执事务与SDK自身校验raw|test_receipt_atomicity.py及SDK raw两参数|receipt-and-sdk-boundary.xml|0|4 passed|
|动态引用/已知无structured错误闭合|SDK dynamic_ref两项及known_sdk_tool_error|dynamic-known-error-fixed.xml|0|3 passed|
|工具调用header密钥保护|test_sdk_header_secret.py初始单项|header-secret-first.xml|0|1 passed|
|首次握手新logger密钥RED|test_sdk_header_secret.py三phase|header-phases-first.xml|1|1 failed / 2 passed|
|真实SDK慢调用边界|test_sdk_timeout.py|timeout-first.xml|0|1 passed|
|动态logger修复与传输实例重用|header三phase+reused_sdk_transport|header-reuse-fixed.xml|0|4 passed|
|冻结后正式目标|tests/unit/test_qcc_binding.py tests/integration/test_mcp_transport.py|final-target.xml|0|46 passed / 0 warnings，14.11秒|
|冻结后必要授权回归|tests/security/test_auth.py tests/security/test_matter_access.py|final-affected.xml|0|17 passed / 0 warnings，7.15秒|
|冻结后独立首轮辅助失败|六个独立文件（header首先执行）|final-independent-first.xml|1|65 passed / 1辅助 failed，47.00秒|
|明确不同时戳后运行攻击|test_api_attacks.py::test_runtime_dto_tampering_zero_dispatch|deterministic-runtime-tamper.xml|0|10 passed，6.04秒|
|同冻结副本最终独立|六个独立文件（header首先执行）|final-independent.xml|0|66 passed / 0 warnings，38.43秒|

已实证并通知作者/父节点的P2：普通单角色handling_lawyer无法执行owner批准绑定；实际SDK返回state=success但pages_complete=False被误写sent_unknown；实际SDK合法is_error结果含自有output schema不接受的安全字段，服务端校验失败后用PROVIDER_ERROR替代dict覆盖已收到structured/content，raw hash不再对应供应商返回。三组已由作者修正并用独立对应probe闭合。

后续对应独立probe已闭合partial/raw及无structured的known error状态。真实SDK客户端自身校验失败时wire_response同样保留安全供应商JSON。外部`$dynamicRef`通过工具发现/绑定后，真实Draft validation曾对独立本机auxserver请求一次`/forbidden-schema`（P2）；拒绝所有外部引用并采用空Registry后，两schema侧GET0/call0已独立闭合。首次初始化响应头反射暴露动态创建httpcore2.http11 logger未被现有logger过滤器保护（P2）；作者加入context-local LogRecordFactory后，新进程的initialize/list/call三phase无canary泄漏、非私有日志before/after原样保留，独立闭合。只记录虚构canary，不含真实密钥。

慢工具实际SDK call约3秒终止为sent_unknown/dispatch1，没有自动重试；独立server的30秒任务被有界关闭，测试5.61秒通过。事务故障探针实际调用方catch+commit后raw/invoke仍0行；Mock发送后撤销actualsession，最终不返回，catch+commit后保raw+invoke2行、dispatch1、canonical hash准确，其他有效律师可以受授权读取、被撤销者不可以。

独立真实协议已通过：Unicode转义secret在content、工具名、description、input/output schema键的反射拒绝，public result/protected raw/error/caplog均无canary；schema只在供应商输出端变化且不主动discover，invoke实时发现后0 tools/call、TOOL_UNBOUND、旧binding disabled。每轮真实SDK initialize/list/call计数由本机127.0.0.1的uvicorn线程记录，有界finally关闭；未访问外网。

辅助错误单列：作者收口`bind_capability`返回pending ToolBinding而非技术ref，首次角色+SDK探针未适配造成6项setup失败，不能作为业务RED；适配`binding_reference(pending)`后8项通过、partial业务1项失败。SDK源码探查曾误用不存在的get_tools/_validate_tool_result和一个错误文件路径，均为只读辅助命令失败，无业务证据。独立probe不把这些错误计成缺功能RED。

新增nonerror非法structured探针第一版被SDKserver自身Pydantic提前拒绝，供应商真正返回安全error而非预期structured，属于1项辅助断言错误；后改为runtime返回满足Python adapter、advertised schema类型故意冲突，客户端SDK校验边界及真实wire证据均通过。与已实证known error无structured状态的业务失败分别保存。

冻结后独立首轮`approved_at`运行攻击曾取`datetime.now()`，未保证实际不同于刚创建的服务器审批时戳；没有异常不证明篡改通过。改为服务器原时戳加一天、先assert forged!=binding后，全部10种运行攻击通过，业务源不改。旧首轮完整JUnit保留为辅助设计缺陷。实例重用的实际SDK两次调用也已通过：第二次实时输出漂移只增加initialize/list，tools/call增量0，抛TOOL_UNBOUND、不造第二invoke回执，第一raw及hash保持不变。

最终独立完整命令：`.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/t07-review/test_sdk_header_secret.py .audit-local/t07-review/test_role_separation.py .audit-local/t07-review/test_api_attacks.py .audit-local/t07-review/test_sdk_attacks.py .audit-local/t07-review/test_receipt_atomicity.py .audit-local/t07-review/test_sdk_timeout.py -q --tb=short --junitxml=.audit-local/t07-review/final-independent.xml`。header排第一且pytest是新进程，首次动态logger缺陷不会被前序SDK调用掩盖。正式目标和必要回归的完整命令为表中范围加共同前缀与`-q --tb=short --junitxml=.audit-local/t07-review/<表中JUnit>`。

封证命令：`.venv/Scripts/python.exe -X utf8 .audit-local/t07-review/seal.py pre` 与 `post`，均exit0。作者FINAL_FREEZE inventory SHA为`c2eca758af2f50da68d5130503bdc50009c5c914916a02f2c27af91ccc2559e8`；验证前/后81/81 owned文件字节/SHA匹配且未漂移。最终`.audit-local/t07-review/final-seal.json`封115文件（81作者文件、核心/授权相关源码测试、独立探针和20份JUnit），SHA `afb374ff898e11f4320647b34b86bf94b962e1127e60721666abdc3c7331b6b9`。final JUnit精确46/66/17、失败/错误/跳过全0；父节点独占全套、四CLI、状态更新和提交。
