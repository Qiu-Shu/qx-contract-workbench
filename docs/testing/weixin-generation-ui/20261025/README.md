# D2g4 对话页明确登记目标历史：实际证据

2026-10-25，基线 `5f3353cf87be3767108c8e4736aa4ff4484cdd44`。这是源码与独立虚构数据验收；安装版仍为0.4.1。真实微信、产品模型、真实合同、付费、签发及自动外发未启用。账号收件仍暂停，不能把历史登记称为运行切换或生产完成。

## 实现与证据边界

|类别|已核实内容|
|---|---|
|源码已实现|原对话页任务卡内新增折叠历史表单；明确读取、选择目标、填写理由、预览，再明确保存。预览只GET；缺绑定时保存才创建本机synthetic绑定，再提交八字段CAS历史请求。两个独立事务，可能只保存绑定。|
|源码已实现|未知绑定只GET task-drafts，找回后需再次明确保存；未知历史只GET固定request回执。缺失、错配回执保留待查询操作，不自动重发或清空。完整scope摘要/CAS元数据及有效UTC回执检查；409重读，401/403沿现控制器撤权。|
|源码已实现|旧授权与新历史表单互锁；切换、新建、退出及离页守卫；CID/epoch/读取序号/选择版本隔离迟到回调。冻结根scope签名，绑定完成后再次核本页稳定性；已确认保存与后续刷新失败分别报告。恢复readonly与后端fence保持。|
|已有测试证据|A—C及D1—D2g3的证据见各历史目录；本轮未重复计算历史全部测试数，未改写历史NOT_RUN。|
|本轮实际验证|12模块229个不同Python用例、15脚本233个Node用例、2组本机FastAPI/Chromium流程及4项开发检查全部exit0。独立41 Node及2 Python桥复跑通过，重复不累加。|
|尚未实现|按generation恢复收件/分发、可信微信身份/资格与传输入口、E有限期真实合同模型许可。界面明确提示仅记录历史、收件仍暂停。|

主要定位：[`bindWeixinGenerations`](../../../../src/cn_contract/web/static/assistant-weixin-generations.mjs) 的 `refresh`/`prepare`/`save`/`find`，原[`assistant.mjs`](../../../../src/cn_contract/web/static/assistant.mjs) 接线和导航守卫、[`assistant-weixin.mjs`](../../../../src/cn_contract/web/static/assistant-weixin.mjs) 互锁、[`assistant.html`](../../../../src/cn_contract/web/templates/assistant.html) 表单、[`app.py`](../../../../src/cn_contract/web/app.py) 的精确静态白名单。后端业务、DTO、schema、权限和暂停guard未变，仅补静态文件名。当前14个验证输入散列见 [verification-summary.json](verification-summary.json)。

## RED、修复与回归

- 初始新模块不存在：1个模块加载失败，不能冒充35项行为RED。[原日志](node-independent-red.log)。实现后35项通过。
- 独立真实Promise时序发现5项失败：旧prepare在新refresh后复活预览、旧prepare finally误解锁新read、已确认回执被后续刷新失败误标未知、未知绑定期间scope增长后恢复旧写权限、绑定等待中根变dirty仍继续POST。[35过/5败](node-independent-races-red.log)。
- 增加缺失/非法/非UTC created_at回执负例后41项中35过/6败，[原失败](node-independent-receipt-red.log)。修复共享状态门控与收尾后，根和独立41项均通过；[独立最终](node-independent-final.log)。
- 首轮实际浏览器停在初始表单，无截图批次完成；新增模块被原静态白名单拒绝。原HTTP导入图测试实跑11过/1败，明确404，[日志](frontend-red.log)、[JUnit](frontend-red.xml)、[浏览器首轮失败](browser-first-failure.json)。最小补新文件精确白名单并把新Node脚本接入已有Python桥，未扩大任意静态访问；原导入图随后通过。

|根验证组|数量|退出码|实际证据|
|---|---:|---:|---|
|frontend + pages|31|0|[日志](root-frontend.log)、[JUnit](root-frontend.xml)、[命令/散列](root-frontend.json)|
|head DTO/service/routes/atomic|57|0|[日志](root-head.log)、[JUnit](root-head.xml)、[命令/散列](root-head.json)|
|generation receipt/routes/recovery|64|0|[日志](root-http.log)、[JUnit](root-http.xml)、[命令/散列](root-http.json)|
|authorization DTO/routes + generation guards|77|0|[日志](root-authorization.log)、[JUnit](root-authorization.xml)、[命令/散列](root-authorization.json)|
|15个assistant Node脚本|233|0|[完整TAP](node-all.log)、[命令/散列](node-all.json)|

Python共229个不同(classname,name)，0失败/错误/跳过；四组及Node/四门的14个输入散列前后一致。Python桥内部会执行Node，独立复跑也会重复，均不加到233。永久新增覆盖见[`test_assistant_weixin_generations.mjs`](../../../../scripts/test_assistant_weixin_generations.mjs)，HTTP导入图和桥见[`test_assistant_frontend.py`](../../../../tests/integration/test_assistant_frontend.py)。

## 真实本机浏览器与恢复

运行已有仓库Python/Chromium，临时端口仅127.0.0.1，只有独立虚构会话与synthetic账号，不启动provider、worker或微信transport。输出在唯一`.local/weixin-generation-ui-20261025/`目录，数据库、qxbak、截图均未入Git。

- 新脚本[`validate_weixin_generation_browser.py`](../../../../scripts/validate_weixin_generation_browser.py) 第二次运行exit0，[实际报告](browser-history.json)。首次失败后未进行审美迭代；首次完成的1280/360截图批次已实际查看，中文标签、版本预览和保存按钮可读，无横向溢出，键盘focus/Enter成功。
- 读取与预览前后数据库计数相同，目标甲缺绑定仍零写。明确Enter后创建1个绑定、追加第1代。第2代真实POST已提交再丢ACK，仅固定GET确认，无重发。目标丙绑定POST已提交再丢ACK，GET仅找回绑定，第二次明确保存才追加第3代。
- 共3次generation POST、2次binding POST。源与真实qxbak恢复副本均为1账号、1根映射、4绑定、3代历史，其余grant/poll/descriptor/dispatch/inbox/draft/execution/attachment/model_attempt/run/review均0。恢复副本UI禁用写；固定历史GET200，POST409 BLOCKED_LIVE；未运行微信接收或审查。
- 原授权浏览器回归exit0，覆盖原同目标授权、真实两次上传独立注册合成DOCX、2个grant、丢ACK只查、真实qxbak只读及撤权；[报告](browser-legacy-report.json)、[命令](browser-legacy.json)。这组有2份合成附件，不与新历史组零附件混淆。
- 两组浏览器外部页面请求及pageerror均0。新历史组产品5个UI源哈希前后一致；app.py的精确白名单另由最终Python导入图与独立审查核验。

## 开发门、复核与未运行

四开发检查exit0：[schema](schema.log)、[defaults](defaults.log)、[sources](sources.log)、[dependencies](dependencies.log)。来源检查13项仍NOT_PRODUCTION_APPROVED；运行依赖55项＋构建1项，native_build_verified=false，network_calls=0。Impeccable机械扫描五个变动UI目标exit0，[结果为空数组](impeccable-detect.json)，未以此代替截图与行为验证。

同一独立审查者分别完成Spec/Standards两轴，0确认遗留问题；[审查报告](review.md)、[原始结构化结果](independent-review.json)。另一Standards代理再次被宿主thread limit拒绝，不能称两名独立审查者。本轮也补完上一片D2g3欠缺的独立Standards静态复核，0确认违规、测试NOT_RUN；保留旧阶段当时未完成记录。本轮WorkBuddy NOT_RUN，未重试既有Bash拒绝任务。

全仓单进程、安装版Electron、新安装包、真实微信、真实产品模型/合同、付费、签发和外发均 **NOT_RUN**。本轮恢复成功不证明既有WIN-PATH-02或原生访问冲突已修复，两项保持 **OPEN**。后续先接按代际收件/分发，再处理可信微信资格及E许可；本片仅登记历史，账号仍暂停。
