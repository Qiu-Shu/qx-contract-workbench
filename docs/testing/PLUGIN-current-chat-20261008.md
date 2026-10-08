# 当前聊天离线插件：首次真实调用记录

日期：2026-10-08。基线 `ef17c58`。本记录增补2026-10-05的历史SOURCE/SDK验收，不覆盖或追改旧结果。

## 实际结果

当前聊天工具清单出现 `qx-contract-offline` 的两个工具；实际调用状态工具和一个固定虚构sales示例，均被拒绝。当前状态是 **DISCOVERED；CHAT_INVOCATION_FAILED（2/2）**，不是HOST_PASS，也不是网页ChatGPT连接成功。

|实际操作|结果|
|---|---|
|`workbench_status({})`|工具错误 `-32602: OFFLINE_REQUEST_REJECTED`|
|`deepseek_offline_example(fixture=sales, operation=extract_facts, model=deepseek-flash)`|同一固定错误；未返回合成结果|
|当前源 `python -I -X utf8 src/cn_contract/mcp/bound_entry.py --check`|退出0，`BOUND_ENTRY_VERIFIED`；build `qx-offline-source-0.1.3-bd6518818b05ba45094fe2e8f1040be9`|
|源码与0.1.3安装缓存三文件逐字节hash核对|`.mcp.json`、`.codex-plugin/plugin.json`、`runtime-binding.json` 3/3一致|
|本机目标Python进程只读盘点|观察到两组本项目bound_entry启动路径；只凭进程列表不能将某PID绑定到本聊天|

安装缓存路径为 `C:/Users/Administrator/.codex/plugins/cache/qx-contract-local/qx-contract-offline-codex/0.1.3`。本轮没有写安装缓存、全局配置，没有请求reload、重启用户应用或终止上述用户进程。

两次调用错误与hash/源入口命令结果保存于 `.audit-local/continue-20261008/host-calls.json`。固定示例参数中的模型名只是离线codec枚举，不代表供应商调用。本轮没有启用模型、QCC、真实材料、付费、托管或云连接。

## 定位结论及边界

当前源码启动校验成功与宿主调用被拒绝可以同时成立。三份缓存关键文件一致，不能继续把失败直接归因于旧0.1.1缓存。返回错误对应入口的有限请求拒绝，但工具调用层没有提供实际入站JSON-RPC信封，因而还不能确定是宿主元数据、信封结构或其他入口条件。

不据猜测放宽未知字段、身份或权限，不把threadId当登录用户。后续定位需取得该目标服务的最小、去值的信封形状诊断（方法、字段名与类型），比较真实失败与现有成功的STDIO测试，然后加入复现测试后修复；不收集其他插件日志、合同正文、密钥或全量会话。

本轮没有修改业务代码、重跑完整pytest或更新源绑定。上轮1346通过仅属于其原阶段；OCR/新viewer/48页仍未运行。
