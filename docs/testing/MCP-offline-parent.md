# 首批本机离线 MCP 父验收记录

2026-10-04，证据时间UTC；workspace `D:\Documents\ChatGPT\律所项目`，基线`efc6b56`，沿`codex/contract-review-v2`。用户在已提交的具体两工具设计和未完成说明后说“继续”；按该有限范围实施，无新增账户、依赖、付费、真实资料或宿主安装。本轮结论为 **ENGINEERING_PASS（受控本机虚构STDIO）**，ChatGPT连接、真实调用和生产仍未验收。

## 本轮实现和复用

新增`src/cn_contract/mcp/offline_server.py`及包入口，沿用固定MCP2.2.0、现四份登记虚构DOCX、唯一领域类型和DeepSeek纯codec，保持原页面、CLI、精确MockProvider注册门、审批、费用和签发代码。只在domain新增三个DTO及一个fixture Literal；既有domain AST去除这四项后与基线完全相同，ReviewRun/schema/defaults未改变。

两个实际发现的工具为`workbench_status`和`deepseek_offline_example`。前者无业务参数，不读案件；后者只接受四fixture、三operation、两model枚举，拒绝额外原文、raw响应、path、URL、key、token、rates、actor、budget和approval。schema为additionalProperties=false，原始arguments先过严格白名单，空协议_meta仅为SDK兼容。示例返回登记hash、请求和人工固定回复，response/token明确人工构造、非供应商和法律意见；cost为None/unknown/USD。

STDIO继续由SDK解析、分帧和调度。高层MCPServer提供公开工具注册/list/call；公开低层Server转发这两接口，公开消息write-stream在SDK编码前将JSONRPCError统一为固定正文并保留标准相关id。两层默认OTel均移除，不访问或patch私有manager，不修改SDK。原始错误数据、未知工具名及canary不进入结果正文或stderr。固定fixture及所有名义祖先的symlink/Windows reparse在内容open前拒绝，读取后再核固定hash。

正常导入原review包会传递导入workflow/security/persistence并初始化公开dummy password hash；正常SDK/Pydantic初始化也读取普通locale/PYDANTIC/OTEL变量。工具不调用这些业务服务、不读取凭据、不访问案件DB或外部网络；不能把正常模块导入或整个进程的环境继承描述成零读取。

## 实际测试及失败历史

|实际执行|退出码|实际结果与范围|
|---|---:|---|
|作者首轮两目标RED|1|63 failed/0 errors：缺入口/DTO的有效断言，非import收集错误|
|作者最小实现及SDK兼容RED|1|62 PASS/1 FAIL；SDK自动空_meta被过严拒绝；新增wire回归先3 PASS/2 FAIL，再64 PASS|
|作者初版目标/关联|0/0|74 PASS/342 PASS；只是初版，后续独审仍发现缺陷|
|传输初审|1|133 setup ERROR+1生命周期FAIL：私有launcher缺SYSTEMROOT，未进握手，不计产品RED；修复审阅脚本后134 PASS|
|传输前置层真实RED|1|7项中5 PASS/2 FAIL：SDK时代分类在middleware前反射error.data.requested|
|材料边界初审与真实RED|0/1/1|先88 PASS；真实目录symlink和NTFS junction各1 FAIL，hash拒绝前读到私有人工canary文件|
|作者修复正式RED|1/1|先4 FAIL，再补目录/祖先symlink和junction后6 FAIL，0 errors；原证据保留|
|作者修复目标/关联|0/0|80 PASS/348 PASS，原生收集与JUnit数量一致，0警告|
|独立传输最终复验|0|原141+补3=144 PASS；native与JUnit逐项一致；8实际child自然exit0、stderr0、两层OTel入口0|
|独立材料边界最终复验|0|92 PASS，native与JUnit逐项一致；四类目录/祖先link读前0 opens；工具env/credential/DB/network零越界|
|父独立SDK STDIO调用|0|initialize/list，status1、四类×三操作×两模型24成功、4拒绝；transport正常关闭、child stderr空；不是24次供应商或法律审查|
|父首次完整回归|4294967295|因上述真实独审缺陷主动停止自己的已核验pytest进程；151.078秒、无最终JUnit，不能记PASS或功能RED|
|父最终完整pytest|0|1016 PASS，0失败/错误/跳过/警告；native1016与JUnit逐项一致；原936+新80|
|defaults/schema/pip check|0/0/0|默认hash仍0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887；ReviewRun schema一致，环境无破损依赖|
|来源development/release|0/1|13来源开发通过；发布实际9阻断，未取得生产批准|
|runtime development/release|0/1|55 runtime+build1实际核对；发布59阻断，native build未验收，无网络调用|

作者初版6轮12命令、修复4轮8命令，共10轮20个pytest命令，各轮独立native/日志/JUnit/UTC保留。完整作者过程见[初版记录](MCP-offline-author.md)和[修复记录](MCP-offline-author-repair.md)，初版seal与报告没有覆盖。

父最终pytest使用私有收集plugin记录真实session.items，再以`pytest.main`执行完整默认项目suite；没有指定单文件缩减范围。实际命令、stdout/stderr和UTC保存`.audit-local/mcp-offline-root/full-final.json`。开始`2026-10-04T14:26:09.738554+00:00`，结束`14:31:51.624564+00:00`；wrapper341.891秒、pytest339.43秒。JUnit SHA-256为`92e2beacdd872febcc1318e4b45837926936c3e23bc725fc877b0e827baec67f`，native集合SHA为`95c311f9fdfaa8e9a4a548732e9ebaa90fbeb968d1fee719fdee2da55e048cae`。首次中止的full.json/raw输出单独保持，不作为最终通过证据。

父SDK最终复跑`14:26:06.758226–14:26:08.930131 UTC`，实际29个tool调用，详情和schema保存在`parent-final-stdio-evidence.json`；固定人工token100/40/60/20/120及未知费用，不产生真实账单。

## 独审和保留核验

独立传输报告`.audit-local/mcp-offline-transport-review/REPORT-final.md` SHA `bca528483bfe339312da67207c16e4a1f1e0b59feb78dd220ae07a008139ef54`；evidence-final.json SHA `87812507128c6a1808a67f0449ca9c91ffeba98b83ea702e07308a660c2d27d3`。原139 PASS/2 FAIL和launcher错误各自保持。

独立材料边界报告`.audit-local/mcp-offline-boundary-review/REPORT.md` SHA `aaa6bfddff90b1e2fbe82fedde3215d5a3eb34b43c5f125342d27e9ecb11451d`；verification.json SHA `64e69d711d228344bb622b4cdf5da4181774737b729607915ed05fe1dcaffcd6`。14所审源前后相同，305来源/许可/fixture及52旧test.py字节不变；普通依赖startup环境读取单独记录，不读真实变量值。

父`candidate-verification.json`实际重算609基线文件，仅domain有已声明新增；核8作者文件+54证据，共62项全匹配，原seal hash不变。最终offline_server SHA为`75835bb9606e17a8d66a9563a66447d4e0b5a3bb6b3f553e4cb6f9c109568f73`。full前后和提交前另核源码/测试/来源不漂移；本文与README/状态/目标映射的更新仅是结果文档，不追加低价值文案测试或重跑已通过suite。根最初路径猜测未命中只属辅助读取，未当功能RED。

父14:36:46.397593 UTC实际提交前核验exit0：精确12个预期暂存文件，index与工作副本实际字节也完全相同（不仅LF等价）；459个full前源码/测试/config/schema/来源/依赖输入零漂移，312个既有sources/fixture文件字节不变，full JUnit实际hash匹配，diff检查0。仅三条明确secret pattern扫描findings0，不是完整敏感资料分类。本段为首次暂存核验后的结果追加，最终索引另存新的核验文件，不覆盖first-staging。

## 仍未完成

仅当前editable仓库和四登记虚构文件可运行；未打包或安装插件、未连接Codex/ChatGPT宿主，没有OAuth/案件身份桥、文件上传下载桥、真实案件工具、HTTP、公开端点、托管或隧道。真实DeepSeek transport/费用账本、QCC、律师规则/gold和生产批准继续阻断。

`TRANSPORT_FRAME_LIMIT_NOT_ESTABLISHED`和`OS_CPU_MEMORY_SANDBOX_NOT_ESTABLISHED`继续保留。消息错误脱敏不是帧大小防御或OS沙箱；静态reparse测试不宣称解决恶意并发文件系统竞态。未进行本轮Word/普通浏览器视觉、完整浏览器网络捕获、真实模型、真实影子或生产部署。

T13历史84能力仍是5 PASS/36 NOT_RUN/16 NOT_IMPLEMENTED/7 NOT_SUPPORTED/20 BLOCKED，58 guard单列；本轮没有重跑84 CLI或40材料法律评测。1016工程回归和24离线示例不能替代这些业务能力或双律师法律验收。
