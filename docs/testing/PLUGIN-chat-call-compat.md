# 本机工具调用元数据兼容与当前聊天接入状态

日期2026-10-05，时区Asia/Shanghai，实际证据使用UTC。从`54adbdac281ce139735f9cda03a250d823a035e6`沿`codex/contract-review-v2`增量继续；已有T00–T13、原包及历史验收不重做。

本轮修复了受控STDIO服务对宿主聊天标识的拒绝：只在tools/call接受36位小写规范UUID形式的threadId，可与既有有界整数progressToken共存。标识不作身份或批准，不进入业务handler或返回结果。工具名称、业务schema、domain、固定虚构样本、默认配置及真实模型/QCC关闭状态保持。

## 来源与真实失败

精确本机宿主`0.159.0-alpha.12.1`，公开源码pin`180d8caaac22c656bfc6329f2f573ee1430cbe20`。该版本直接工具调用会插入threadId，rmcp 3.2.0再合并并生成整数progressToken。[宿主调用与元数据](https://github.com/openai/codex/blob/180d8caaac22c656bfc6329f2f573ee1430cbe20/codex-rs/app-server/src/request_processors/mcp_processor.rs#L576-L633)，[SDK合并](https://docs.rs/rmcp/3.2.0/src/rmcp/service.rs.html#880-894)。宿主能解析其他UUID表示；本机仅接受规范小写表示是受限profile，不承诺覆盖全部宿主元数据。

正式测试先启动真实产品STDIO子进程，使用独立虚构UUID和宿主样式信封，实际得到4 failed/6 passed/0 errors。四失败均为thread-only或与0/1/max整数进度编号共存时，合法status调用被旧边界固定拒绝。这是**合成协议复现RED，未发生原生宿主tools/call实测失败**。随后仅修改入口UUID导入、metadata核验及tools/call开关；业务函数及低层转发不变。

tools/list仍只允许空metadata或整数progressToken；ping仅空metadata。UUID不限版本，但类型必须精确str、长度36且解析后小写规范表示等于原值。progressToken必须精确int且范围0..2^63−1。未知字段、字符串进度编号、非规范UUID、traceparent/tracestate和业务arguments注入仍拒绝，错误正文固定且不反射人工canary。源码存在条件性trace/read-only metadata；当前实际宿主调用是否携带未观察，继续单列兼容限制。

## 本轮实际验证

|命令/证据|退出码|实际结果|
|---|---|---|
|作者`pytest -q tests/integration/test_mcp_host_metadata.py --tb=short`及独立collect|1/0|先10项中4 failed/6 passed，native=JUnit，0 errors；证据`red-thread-profile-*`|
|同目标首次GREEN|0|10 passed；随后补虚构v7覆盖，不再改变入口|
|host_metadata、offline_stdio、unit/offline三个MCP目标及collect|0|94 passed，0 warnings/failure/error/skip；native=JUnit；证据`green-three-mcp-*`|
|独立标准库STDIO探针|0；child自然0|246检查/242请求回复：120成功、122固定拒绝；完整24示例及6种规范UUID，结果与无metadata完全相等，stderr/多余stdout空|
|独立源/旧证据保全|0|24/24；当前源5件/90绑定匹配，旧cache0.1.1、原7件/ZIP、旧seal及24旧证据不变；新cache不物化单列|
|独立native证据核对|0|7/7；仅init、target plugin/read和单server status；工具descriptor与上阶段相等，恰两工具/toolsError null，child自然0|
|根完整`pytest -q --tb=short --junitxml=docs/testing/PLUGIN-chat-call-results.xml`|0|1030 passed，0 warnings/failure/error/skip，336.38秒；原生摘要数量=JUnit数量|
|`verify_sources.py --mode development / release`|0 / 1|13来源/13生产警告；release实际9 errors，仍阻断|
|`verify_runtime_dependencies.py --mode development / release`|0 / 1|55运行+1构建包，开发errors0；release实际59 errors，network_calls0，仍阻断|

作者正式证据在`.audit-local/plugin-chat-call-compat-writer`，独立边界与保全在`.audit-local/plugin-chat-call-compat-review`；根完整JUnit为[PLUGIN-chat-call-results.xml](PLUGIN-chat-call-results.xml)，原生输出及退出由本轮实际命令确认，根`verification.json`另核对1030个testcase且0 failure/error/skip，并逐项核验作者与独审seal。初始只读连接准备目录`.audit-local/plugin-chat-connection-boundary-review`保留23/23、26固定调用和8提示，后两者全部PLANNED_NOT_RUN，不能计入本轮调用数。

## 源包、活动缓存和聊天分别记录

新版五文件适配源包为0.1.2，90项当前绑定仅入口hash改变；快照不是自动强制hash门。0.1.1源包五件已在本轮私有baseline另存，旧缓存原封保留；原七文件portable包和ZIP继续保留为历史，旧入口绑定过时。服务自身版本0.1.0与适配包版本是不同编号。

根启动一个独立本机host，仅initialize、target plugin/read和过滤`qx-contract-offline`状态。实际read返回localVersion0.1.2/source为当前repo、installed/enabled true；实际发现恰两工具、toolsError null、resources/templates空。**localVersion来自源目录，installed布尔可由旧缓存满足；runtime loader使用active安装缓存。新独立宿主选择0.1.1，新cache0.1.2不存在；本聊天已加载的插件根未验证。** 旧MCP清单与新版相同，绝对入口指向本仓库；本轮当前代码的wire验证另有证据。发现证明服务可启动，不构成宿主运行入口hash证明，也不证明0.1.2缓存安装或本聊天调用完成。

本轮没有复制/改写安装缓存，没有调用plugin/install、plugin/reconcile、forceRefetch或config/mcpServer/reload。源码核验显示install会改用户启用配置并清缓存/刷新MCP和hooks；reconcile无本地target参数且面向远程已安装集合；全局MCP reload会遍历所有loaded线程。它们不能冒充单插件只读检查。[活动安装目录选择](https://github.com/openai/codex/blob/180d8caaac22c656bfc6329f2f573ee1430cbe20/codex-rs/core-plugin-common/src/installed.rs#L47-L67)，[全局reload实现](https://github.com/openai/codex/blob/180d8caaac22c656bfc6329f2f573ee1430cbe20/codex-rs/app-server/src/mcp_refresh.rs#L9-L67)。没有重试旧10050代理连接、创建/resume聊天、启动模型turn或重启用户app。

本轮JUnit SHA256 `93a804b44d0ca7189346f212c2324814096a734094b77f97b99fabc61ae4e2d4`；作者seal `af6891db0c17b49ded1ab553ab124ab812d864571b1274c7b5f50a174e516ffc`，边界seal `1dbf040bfc8d91861b2daec8c8b7e7d713c662724d9ed4fcff955eff441fbd31`。两个seal共31证据文件由根实际逐项hash复核，无不匹配。源码/缓存补充只读报告`REPORT-cache-install-readonly.md` SHA256 `672cbe4a37d2f56735441d4c301f8788f4eba7bb890fb6f8fd970342cf112325`，native transcript `204d3e91ddf42a2563668a7b9807b81f7b2c238679f6c283694b87a0079fdd04`。完整本轮私有根证据在`.audit-local/plugin-chat-call-root`，不纳入发布包。

本聊天purpose-built元数据确属local Codex，实际cwd为本项目；本轮工具inventory315项，无目标两工具。用户确认设置能看到插件且有刷新入口；已请用户刷新，完成尚未确认。当前目录缺少已知日志位置的文件，未宣称做过完整日志诊断。旧10050只证明传输失败；旧代理NDJSON未到WebSocket握手，不能据它推断插件拒绝或账户权限。

云端eligible USER-scoped personal plugin listing实际成功但plugins=[]，不代表无账户、无权限或所有workspace插件缺失。ChatGPT Developer mode、目标workspace、Tunnel权限/关联/运行凭据或公有HTTPS endpoint均未验证；没有创建云插件、账号、隧道或托管。匿名固定虚构两工具可先接入，不要求提前完成未来案件OAuth/文件桥。[官方连接与测试](https://developers.openai.com/plugins/deploy/connect-chatgpt)

当前状态：**WIRE_METADATA_ENGINEERING_PASS；SOURCE_0.1.2_READY；FRESH_HOST_CACHE_0.1.1_DISCOVERY_VERIFIED；CACHE_0.1.2_NOT_MATERIALIZED；CURRENT_CHAT_LOADED_ROOT_UNVERIFIED；CHAT_INVOCATION_NOT_RUN；CHATGPT_CONNECTION_NOT_RUN；REAL_MODEL/QCC_DISABLED；PRODUCTION_BLOCKED**。

下一步使用用户已看到的插件刷新入口后检查本聊天工具清单；若出现目标工具，先实际status，再虚构示例与拒绝验收。若仍未出现，记录刷新结果及安全错误形状后继续定位。未来真实案件身份/授权、文件桥、真实供应商transport/预算/价格/数据政策、律师规则/gold、外查许可、影子和生产批准仍分别缺失或阻断。本轮完整pytest回归不替代原84能力、40材料、Word或浏览器的独立阶段验收，本轮未重新执行这些独立验收流程。
