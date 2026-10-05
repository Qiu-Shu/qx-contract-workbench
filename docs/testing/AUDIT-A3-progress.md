# A3 / F12：有界标准 progressToken

2026-10-05。只调整既有 MCP 边界，保留两工具、身份隔离和所有真实调用关闭。精确整数保持 0–2^63−1；字符串原样接受（含空串、中文），最多 128 码点 / 512 严格 UTF-8 bytes。Cc/Cf、孤立 surrogate、bool/float、超限及未知 metadata 拒绝。threadId 仍只在 tools/call 核对 canonical UUID，不能作案件身份或批准。

|实际命令/阶段|exit|结果|
|---|---:|---|
|新增真实 STDIO 字符串目标 RED|1|7 failed，0 errors|
|新增目标 + host_metadata|0|37 passed，0 warnings|
|offline / stdio / transport 关联|0|100 passed，0 warnings|
|作者最终 wire capture|0|118 输入含 1 notification；111 响应=52 accepted+59 fixed refusals；另 6 SDK parser 无 reply，正常 status 随后恢复；child0/stderr0|
|独立目标|0|37 passed|
|独立直接边界|0|532/532，包含全部 235 个 Cc/Cf 在 call/list 的核验|
|独立 wire|0|23 输入/20 响应=13 accepted+7 refusals；另 2 parser 无 reply后恢复；child0/stderr0|

独立核对纠正作者第一次捕获的报告数字：原始 JSONL 实际 **89 输入、87 响应**，另外包含 1 notification 和 1 无 reply 帧；原作者 REPORT 的“88 响应”不准确。初次脚本错误地等待 parser 拒绝帧回复而 exit1，原请求、响应和空 stderr 保留，未把它计产品失败或最终 wire 通过数。首次目标还发生过同名测试模块 collection error，修正文件名后另存记录；不是功能 RED。

SDK parser 在 middleware 前拒绝孤立 surrogate 且不返回 protocol error。该限制仍存在，本次不包装 parser、不建立帧或 OS 资源硬限，也不将无 reply 写成固定拒绝回复。静态协议和 SDK 子进程结果不证明当前宿主或 ChatGPT 调用。

详细证据：`.audit-local/audit-a3-progress-20261005/REPORT.md`、`wire-summary.json`、原 JSONL，以及 `audit-a3-progress-review-20261005/REPORT.md`。独审 17 个受保护文件前后 hash 不变。旧插件源码绑定因本轮变更已过时，入口源包核验另记；没有修改活动缓存或执行刷新。
