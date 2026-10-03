# T10 父节点普通浏览器实际记录

2026-10-03 UTC，本机CUA in-app browser，loopback `127.0.0.1:8765`，用户授权的独立虚构数据。开发检查和最终验收不同：旧sales单案四下载只在`.audit-local/t10-browser-development`，不算最终四类。最终重启最新代码，新目录`.local/t10-browser-final/20261003T082500Z`，未复用旧导入进程。

四案通过普通表单创建、真实filechooser选择固定DOCX；逐项核对候选，确认版本1→2；开始mock任务，观察queued/completed、18维/3、6、5、4意见。原件与未批准规则缺口如实可见。使用当前经办虚构身份处置，保存edit/request_info/refer/reject/accept共五项历史；额外实际点击租赁意见的定位链接，URL和精确原文锚点相符。该样本含越权指令，只作为文字与提示，未执行。

|类型|确认事实|18维|意见|实际下载|复核身份正式按钮|
|---|---:|---:|---:|---:|---|
|买卖|3|18|3|4|BLOCKED_LIVE|
|服务|1|18|6|4|BLOCKED_LIVE|
|租赁|2|18|5|4|BLOCKED_LIVE|
|保密|1段原文，无价款|18|4|4|BLOCKED_LIVE|

每案输入并另行批准缺件意见对应整段的精确替换文字，明确internal/client/counterparty使用范围；内部报告+原生修改副本两下载、客户/对方各报告一下载。16份文件由浏览器真实download事件取得，不是调用内部导出函数冒充点击。父只读核验每份与数据库ExportArtifact SHA/范围/草案状态一致，ZIP CRC、报告含替换文；内部w:ins/new与w:del/old逐一exact。对外修改为报告内人工表，不提供原件包自动修订；律师补件或接受意见不等于正式签发。复核身份每案再生成内部预览并点击正式按钮，共4个BLOCKED_LIVE，正式批准0。

买卖案在事实确认前通过普通页面登记原文候选、人工明确选择、建立/批准/运行Q0，观察“费用0、调用0、未外发或收费”；候选可能含双方与整段，未认定公司名称解析或真实身份。其他三案实际访问费用页，保持QCC关闭/待明确批准，没有供应商请求。只读DB显示query_ledger0，一条query_records是Q0 plan_approval；不能把它称一供应商调用。

额外无上传的DOM文字canary通过普通建案表单输入包含img/onerror的虚构标题。实际DOM标题保留原字符串、img节点0、执行标记null、资源仅本地CSS/JS；仅此输入点的转义验证，不是所有XSS/输出上下文已覆盖。当前tab 300 warn/error记录无应用URL项；扩展自身告警另存，不冒称浏览器全部无告警。实际声明资源为`/static/workbench.css`和`/static/workbench.js`，链接为本机路径；完整网络捕获因只读CUA performance API不可用明确NOT_RUN，不能据资源声明推导所有外发0。后端QCC账本0另证。

证据：`.audit-local/t10-browser-final/downloads.json`、四类review/formal/audience DOM、formal-results.json、dom-canary.json、console-all.json、declared-resources.json和四张formal-blocked.jpg；四图由根逐张实际查看。下载原字节在D:/Downloads与父QA copies，均不进Git；SQLite/受保护材料同样忽略。父核验脚本`.audit-local/t10_parent_final_checks.py`最终exit0、四类/16下载/190作者输入无漂移，七门检查实际码和时间在`.audit-local/t10-parent-final/checks.json`。

历史辅助定位错误（getByLabel精确、选项标点）与QA字段/运行路径错误已纠正并留记；不计功能RED。T09 Word六轮十页/接受拒绝全文证据保留，本轮没有重做或称16份新文件均经Word视觉验收。真实律师gold、正式签发正例、真实外查/模型和生产始终BLOCKED。
