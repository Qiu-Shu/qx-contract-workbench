# D2g5h 待收件界面：2026-10-26 实测

基线 `1a84f7507af94434eebccdf64a94b55924422041`，沿 `codex/contract-review-v2`、schema21 实施已有 D2g5g 服务的界面接线。未改后端业务、数据库、依赖；后端唯一接线是在静态资源白名单中加入新模块。

## 实际行为

“审查合同 · 模拟”内的微信授权区域新增“待收件”：从已保存对话选择原收件目标，明确读取首批或下一批（每批最多20条）；候选对话不是授权名单，由既有服务核验历史归属。仅显示接收时间、文本有无和附件数量，首批第一条可以明确分发到固定目标。只创建模拟任务记录，不启动审查。

分发只提交 descriptor_id。九字段回执须与固定目标和描述符一致；类型、合法 UTC 日历、游标及摘要格式均严格核验。结果未知时保留原操作，只能精确 GET 查回执；禁止重复 POST，锁定目标切换、新对话、退出及关联微信/任务写操作。迟到响应、scope变化、撤权与销毁不会恢复旧操作。已确认后刷新列表，并提供固定目标任务链接。

## 最终验证

| 验证 | 实际数量 | 退出码 | 结果 |
|---|---:|---:|---|
| pending HTTP / dispatch HTTP / 静态导入图 | 38 / 46 / 1，共85个不同Python用例 | 0 | PASS |
| 22份Node脚本 | 444项：443前端、1个几何脚本入口 | 0 | PASS |
| 新待收件模块专项 | 54，包含在上述443中 | 0 | PASS |
| 独立Spec / Standards原探针 | 3 / 4，不计入根代理444项 | 0 | PASS |
| 四开发门 | schema / defaults / sources / runtime | 各0 | PASS |
| 本机合成Chromium业务流程 | 1次完整通过，另保留首轮超时 | 0 | PASS |

完整argv、实际用例ID/名称、运行时间、退出码及644份最终输入SHA见 [verification.json](verification.json)。六个最终运行前后输入一致，发布证据时重新逐项核对；中间运行、独立作者测试和探针复跑均不叠加数量。几何脚本内部断言不另计成测试。四门检查13份来源、55运行包及1构建包；来源仍为 NOT_PRODUCTION_APPROVED，native_build_verified=false，network_calls=0。

## 失败与修正

1. 功能初始RED为可调用模块接口缺失，退出1（不是导入错误），见 [ui-red.log](ui-red.log)。静态导入图首次返回404，退出1；新增静态白名单后最终85项包含该回归通过，见 [static-red.log](static-red.log)。
2. 独立Spec发现2项P2：数组摘要被正则隐式转换后接受，以及2月30日被Date.parse纠正。补两个真实失败回归后收紧字符串类型及日历合法性，[strict-red.log](strict-red.log)为2 FAIL，[strict-green.log](strict-green.log)为54 PASS。原三个独立探针未经修改再次通过；最终 [Spec](spec-final.md) 和 [Standards](standards-final.md) 均0确认遗留。
3. 首次浏览器运行完成20+1分页并成功写入一次分发，但后续刷新未在默认5秒内完成，因此实际记FAIL；[初次报告](browser-initial.json)保留，不能计作完整通过。增加“回执已确认、正在刷新”提示，将验收等待设为20秒后完整流程通过。服务仍复用完整历史验证，不宣称O(limit)或性能问题已解决。

## 浏览器与视觉证据

[最终报告](browser-final.json)：两次明确POST，第二次服务已提交后丢弃ACK；UI保留操作并精确GET一次恢复，没有再次POST。未知结果期间目标、任务保存和新对话均被阻止。22条原descriptor全部保持不变，最终2个dispatch receipt、2个TaskInbox；task_executions / assistant_runs / assistant_model_attempts / review_runs 均0；外部请求、页面异常均0。服务、账号与全部数据仅为独立本机合成夹具。

实际检查 [1280px截图](pending-1280.png) 和 [360px截图](pending-360.png)：原生控件、中文文案和按钮可读，窄屏自然换行，键盘Enter可分发，读取按钮焦点可见；document宽度分别1280/1280和360/360，无横向溢出。Impeccable检测一次退出0、结果为空，见 [impeccable-detect.json](impeccable-detect.json)。未进行额外审美重构。

复现浏览器：`.venv/Scripts/python.exe scripts/weixin_pending_ui_smoke.py --output .audit-local/<新的唯一目录>`。复现独立探针：`node --test docs/testing/weixin-pending-ui/20261026/probes/*.mjs`。随仓探针仅将模块URL改为相对路径，测试体不变；封装后7项再次通过，不累计为新增探针。原始/封装摘要见 [probe-packaging.json](probe-packaging.json)。随仓日志仅规范化本机仓库路径、换行和行尾空格；原始记录及临时数据库保存在本机 `.audit-local/weixin-pending-ui-20261026/`，数据库未纳入Git。

## 限制与后续

本片全仓长进程Python、桌面安装包、真实qxbak往返、真实微信/模型/客户材料均NOT_RUN。安装版仍0.4.1；WIN-PATH-02与原生AV仍OPEN。可信微信身份/资格、下载解密、E模型有限期许可与真实试点审批仍待，不因合成演示通过而称生产完成。

用户AGENTS.md原改动保留未暂存。提交与远端SHA/tree以后续 [GitHub同步回执](github-sync.md) 为准。
