# CodeGraph安装与自动复用

日期：2026-10-09，Asia/Shanghai。用户明确要求安装 https://github.com/colbymchenry/codegraph 并自动使用。

## 安装结果

- 固定官方Windows x64独立发行版1.6.2，内置Node运行时；不改本项目Python/前端依赖。
- 下载地址：`https://github.com/colbymchenry/codegraph/releases/download/v1.6.2/codegraph-win32-x64.zip`。
- 下载大小54,260,850 bytes；解压前和安装后均核对GitHub release API提供的SHA256：`7455e817ee8032666867a1badeb799b8a884c5f4fea9b444e088a02069b6deea`。这是发行摘要核对，不冒称独立重建或完整供应链审计。
- 上游MIT许可证保留于只读参考源码clone。检视源码快照main `b635dd467f0578926a9c01a37b9d28d2b26689f1`，不将其冒称发行包对应源码提交。
- 安装根：`C:/Users/Administrator/.codex/tools/reuse-suite/codegraph`；入口`runtime/codegraph-win32-x64/bin/codegraph.cmd`。全局STDIO MCP使用其中node.exe和lib/dist/bin/codegraph.js绝对路径。
- 持久遥测偏好off；MCP环境`CODEGRAPH_TELEMETRY=0`、`DO_NOT_TRACK=1`、`CODEGRAPH_NO_UPDATE_CHECK=1`。本轮CLI均设相同环境。未配置云平台、模型、API密钥或付费功能。
- 仅新增全局`mcp_servers.codegraph`和AGENTS自动选择段落；原配置结构完整保留，原AGENTS前缀保留。备份仅存安装根evidence，不纳入Git。

## 自动使用与索引范围

编程任务需要模块理解、跨文件调用、修改影响、关联测试时自动用CodeGraph。明确传入实际项目路径和具体符号/文件名。精确文本检索仍用rg；图查询不替代源码核对及测试。新项目在相关任务中按授权范围单独初始化，不扫描整个磁盘/主目录/知识库。

本项目新增`codegraph.json`，排除sources、docs、.local、.audit-local、.venv、插件包、资料/规则/提示词、tests/fixtures等。实际文件清单核对170条唯一文件，仅来自src 90、tests 72、scripts 8；没有将资料库作为代码索引。`.codegraph/`加入项目gitignore，索引留本机。

初次索引：170文件、3622节点、11881边；状态complete，pendingChanges的added/modified/removed均0，pendingRefs0。统计只描述静态提取结果，不代表所有动态调用都被完整识别。

MCP当前发行实际提供1工具`codegraph_explore`。通过显式projectPath查询两个不同项目成功；宿主无默认项目时仍可用该参数。CLI可用于独立查询/影响分析，并作为宿主尚未加载或工具暂不可用时的后备入口。

## 实际检查

|操作/命令|退出码|实际结果|
|---|---|---|
|git clone参考源码；rev-parse|0|固定检视快照，MIT全文可读|
|下载v1.6.2/核对release digest/Expand-Archive|0|大小与SHA256一致，54,260,850 bytes|
|codegraph --version / --help|0|版本1.6.2，Windows入口可执行|
|codegraph telemetry off|0|关闭持久遥测偏好，DO_NOT_TRACK环境同时生效|
|codegraph init sample --yes|0|纯合成Python2文件、5节点、5边|
|query order_total --json|0|返回order.py对应函数|
|callers unit_price|0|找到跨文件order_total调用及order.py导入关系|
|query excluded_synthetic_sentinel --json|0|空数组；private/中的合成文件已排除|
|codegraph init 当前项目 --yes|0|170文件、3622节点、11881边|
|独立STDIO initialize/tools-list|0|server codegraph1.6.2，1工具codegraph_explore|
|独立MCP sample显式projectPath查询|0|order_total、unit_price源码和调用链；isError=false|
|添加合成coupon_total后立即MCP查询，无手动sync|0|返回新函数当前磁盘源码，但明确提示图索引尚未同步；此项单独不能证明图已更新|
|稍后query coupon_total/status/MCP再查，期间无sync或index|0|直接图查询已有coupon_total函数节点；6节点/7边、pending0；MCP包含coupon_total(function)，无过期提示；证明异步最终追上，不是即时一致|
|独立MCP 当前项目显式projectPath查询|0|返回项目符号/调用链/关联测试；isError=false。模糊词validate_contract返回相关符号，并不证明存在同名函数|
|codegraph status --json / files --format flat --json|0|complete，pending0；170唯一文件，实际路径范围核对通过|
|codex mcp get codegraph --json|0|enabled=true；绝对入口、关闭遥测/更新、启动60s/调用120s|
|Python静态保全/摘要/证据断言|0|原config完整结构、原AGENTS前缀、归档hash/大小、170文件范围、3次MCP调用和增量前后证据通过|
|git check-ignore .codegraph/codegraph.db|0|索引数据库已被忽略|
|git diff --check|0|无空白错误|
|当前聊天原生codegraph_explore，projectPath为本项目，query=validate_cases，maxFiles=1|工具isError=false|宿主自动加载后实际调用成功，返回9987字符（含函数源码、调用者及关联测试）；无需再重启|

证据位于安装根`evidence/`：release-asset.json、project-status.json、project-files.json、mcp-before-change.json、mcp-after-change.json、mcp-after-catchup.json、sample-final-query.json、sample-final-status.json、current-chat-native.json、codegraph-mcp.json、verification.json。CLI入口和具体复用方式见该安装根USAGE.md。

## 未验与后续

当前聊天原生工具发现和调用已在本轮宿主自动加载后通过，不需再重启。后台自动监听依赖MCP服务存活，服务不运行时不能称持续实时更新；异步索引可能短暂落后，看到过期提示时先等待/同步再核对。未测试所有语言、动态调用完整性、全套上游测试或完整业务回归。

没有改业务源码、原件、QCC/真实模型/正式签发门，未推送或发布。此前六工具的未提交文档保持。本机开发工具安装不改变生产批准状态。

独立复核末次Critical0/Important0。首轮指出的同步证据口径已用异步追上后的图节点/状态/无stale回执补齐并关闭；末次提及的一处“当前聊天尚未加载”后备入口文案已改为一般宿主不可用场景。独审仅查配置/归档/数据库/证据与文档，未重跑业务全套；当前聊天原生调用由父会话实际执行。
