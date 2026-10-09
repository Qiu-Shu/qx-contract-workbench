# 明确授权的插件候选提交：实际实施记录

2026-10-09（Asia/Shanghai）；命令收据使用UTC。基线b8da6d7，沿codex/contract-review-v2增量，复用现有持久工作台、选案授权、来源核对、ReviewProposal、律师处置、原生修订和导出。仅独立登记虚构数据，无新增依赖、数据库表或真实外发。

## 已实施

- 审查页新增默认未勾选的“一轮候选提交”同意。只读同意不扩大为写入权限；后端严格校验布尔值、登录会话、角色/成员、15分钟有效期、材料/事实上下文及原文来源。
- 新submit_selected_candidates工具只接收AssistedReviewInput，不接受指定案件、身份、来源证明或任意地址。固定本机8767、禁代理/重定向、有界请求/响应、无自动重试。超时显示须去工作台核实。
- 每次授权只保存一轮。相同输入返回原收据，不同输入拒绝；读案不会因候选已保存而误撤授权。数据库事务之后再加锁读取收据，提交commit与缓存发布在同锁内，覆盖并发读取及重放窗口。重启保留数据库候选，但旧授权失效。
- 后端生成local_plugin_unverified收据，模型身份UNVERIFIED、推理NOT_ATTESTED、工作台模型及QCC调用0。插件或聊天自身推理未经工作台认证。来源随不可变候选、重验及报告保留；人工入口沿用旧字段及哈希规则。既有assisted_manual工程流程名称保留，不代表插件候选为人工。
- 候选落库保持awaiting_lawyer，未经人类处置不会自动采纳或签发。已实际测试律师处置、客户稿及原生红线批准/下载；草案显示插件来源未核验。
- 源包0.1.5提供4个工具。116源/选定文件、57已安装版本，构建qx-offline-source-0.1.5-8a798b6dbd89dba87cc5be5fa71a6b45。未改活动宿主缓存或全局安装配置。

## 实际测试

[证据目录](plugin-candidates-20261009/)保存逐项命令、UTC、退出码、输出SHA、JUnit及失败原文；不同批次有重叠，不相加宣称独立总数。

|阶段|实际结果|退出码|范围与处理|
|---|---:|---:|---|
|backend-red|10 failed / 2 passed|1|未实施显式写权限及提交入口|
|backend-green初次|1 failed / 11 passed|1|测试误取API外层status，修正测试字段，非权限缺陷|
|tool-red → tool-green|2 failed → 12 passed|1 → 0|有限写工具、输入与原客户端边界|
|target|53 passed|0|早期候选/旧桥接/客户端|
|export-red → export-green|1 failed → 1 passed|1 → 0|实际下载暴露旧人工页眉；按可信收据输出来源|
|regression|270 passed / 1 failed|1|手工、确认、PDF、MCP元数据/进度/协议/入口；旧首页标签断言失败，无bridge页面保留原人工标签|
|final-target|58 passed|0|包含上项失败的精确复验、候选、旧桥接/客户端与实际STDIO→HTTP提交；此批早于并发残余修复|
|review-fixes|6 passed|0|父侧对独审最初6探针复验|
|concurrency-fix|3 passed / 18 deselected|0|并发提交/提交后读取/并发读取修复目标|
|final-binding|90 passed|0|最终源入口及全部插件候选用例，包含两并发窗口和真实STDIO/HTTP；82.54秒|
|browser|1 passed|0|实际页面默认只读拒写、单独同意提交、刷新显示待律师处置与未核验来源、撤销；9.74秒|
|entry-check / dependencies|VERIFIED / no broken requirements|0 / 0|固定绝对入口核验、环境依赖一致；新增安装0|
|独审 corrected-probes|2 failed / 3 passed|1|提交后读案误撤连接、来源误称人工两P2有效RED|
|独审 exports-manual|13 passed|0|12原手工完整旅程+1插件原生红线批准下载；192.74秒|
|独审 final-probes（中间）|6 passed|0|两项P2最初修复，尚未覆盖随后发现的并发窗口|
|独审 concurrent-read-red / publication-race-red|各1 failed|各1|提交前读取旧状态、commit后收据发布窗口有效RED|
|独审 final-eight-probes|8 passed|0|最终两P2及并发残余关闭；45.52秒|

独审最初initial.xml另含2探针设置错误、2产品失败、1通过；随后已修正探针，不把设置错误当产品问题。[最终独审报告](plugin-candidates-20261009/independent-review.md)范围内无未解决Important/Critical。未重复已通过的270项大回归；最终相关变化由90项、3项及独审8项覆盖。

真实STDIO子进程通过固定loopback8767提交与相同输入重放，拒绝额外actor参数；数据库仅一份候选，子进程退出0、stderr空。该测试重定向测试凭据文件，未读取或建立用户个人账户。浏览器使用独立18768测试实例和虚构案，不触碰原8766案件。1440桌面与390窄屏截图已查看，连接选项/候选显示未见裁切；无横向溢出，页面异常0、外部请求0。不声称全站无障碍验收。

## 未完成与下一步

父聊天本轮原生workbench_status仍返回-32602 OFFLINE_REQUEST_REJECTED，当前工具清单仅旧2个，尚未暴露read_selected_case/submit_selected_candidates。本机源码通信通过不等于当前聊天加载成功，网页ChatGPT连接仍未完成。下一项为宿主加载0.1.5后的实际选案读取/候选提交验收，不通过扩大权限或替换用户聊天伪造该结果。

真实合同政策、真实模型调用、企查查、法源/法律gold、修改后完整语义重审、正式签发和生产批准仍未完成或阻断；旧48页OCR仍有11页质量缺口。本轮未重跑工程全套、48页OCR或Word视觉渲染，历史成绩不改成今日通过。用户授权仍为先离线验证，真实DeepSeek暂不调用。
