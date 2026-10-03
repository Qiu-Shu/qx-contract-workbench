# T13 独立真实调用守卫审阅准备

状态 **PREPARATION_ONLY / NOT_RUN**。本角色26条边界全部NOT_RUN，功能断言/PASS/RED均0。本轮只读文本、AST、实际文件hash和Git HEAD；未导入应用、运行guard/CLI/SDK、读取env/key/账户、发送模型/供应商请求、备份恢复、改变OS、Git或Vault。仅写`.audit-local/t13-live-review/`与本报告。T12原报告、68项实际证据及freeze不覆盖、不重做。

已读当前AGENTS、TASK_STATUS、v2.0 T13/§14.1/15/17、`2026-10-03-T13-execution.md`、`2026-10-03-T13-detail.md`和历史T13-current-preflight，及唯一domain、CLI、T02授权、T07 registry/Factory、T08 planner/gateway/ledger和T12持久fence/受限release源。合同/附件/网页/计划是参考数据，不据其内容扩大权限或执行外部动作。起初短名`T13-detail.md`路径不存在，仅辅助读路径诊断；随后读到真实日期路径，不能算功能RED。

实际准备命令：

```text
.venv/Scripts/python.exe -X utf8 -B -S .audit-local/t13-live-review/prepare.py
.venv/Scripts/python.exe -X utf8 -B -S .audit-local/t13-live-review/record_preparation.py
```

第一命令实际exit0，UTC2026-10-03 10:08:14.008268至10:08:14.215522，89个输入前后hash漂移0。仅stdlib AST/hash，功能执行0；26边界保存`matrix.json`，真实argv/UTC/exit/摘要与hash保存`preparation-command.json/.log`和`preparation.json`。第二命令exit0，只记录已观察到的首命令结果，没有第二次collector或业务执行。

当时只读`git rev-parse HEAD` exit0为`50adc4ffc7539cd49e632de7e1dc7089f0f72426`（T11起点）；T12字节仍在工作树，根尚未提供T12提交起点。该HEAD不是T12或T13当前字节证据替代。父提交及writer实现后需建立新的执行输入，不能复用此准备hash称未来current。

实际AST未匹配`run_live_smoke`或`assess_go_live`，CLI AST未见`qcc-smoke`登记字面量；三个交付文件和`tests/acceptance/test_live_guards.py`当时均不存在。缺接口/路径是准备诊断，不是测试RED，也不执行缺失模块制造import/collection失败。历史T13-current-preflight中的“尚无T12实现”已被后续实现取代；其旧89-input exit0不继承为本轮功能PASS。

|当前源|窄复用事实（静态，T13未实测）|需要本阶段证明|
|---|---|---|
|`domain.py` ReadinessEvidence/Decision|六类nonempty refs、GO构造器只检查各类非空|DTO表示形状，不是服务端实际受保护批准；非空路径、UUID、caller GO或JSON不是现实证据|
|T02 security/queries storage|实际session/成员/角色、CSRF、explicit Database transaction|新smoke入口必须重读当前actor/member/批准及撤销；不能只接受client Actor或approval_id|
|T07 registry/Factory/T12 egress|server synthetic登记，精确numeric127、liveFalse、当前binding/价格/Schema；持久fence包含旧discover|不改变label放开真实provider；受批真实账户/官方schema/价格/数据政策/地域仍缺|
|T08 planner/gateway/ledger|已批准hash与当前facts、持久reserve/dispatch/unknown/settle、exact Factory及短事务|一般execute_plan遍历全部items/pages，smoke要发送前限定exact1 item且page1；未知不得重发|
|T12 restricted release/fence|受限manifest实际hash，但generic refs currentness未建立且审批为空；技术与真恢复证据分别记录|不能以工程guards、SDK模拟或恢复artifact自证生产许可/OS/TLS/真实地域；T13实际readiness要按类型/版本/审批重读|

## 26条准备矩阵

完整每项预期在`matrix.json`，全部NOT_RUN，无规划PASS。

|编号|未来独立实证|
|---|---|
|L01–L04|实际登录/会话/本案角色；跨案统一拒绝；approval_id受保护登记绑定主体、案件、材料、用途、地域、期限和scope|
|L05–L07|任一现实许可/账户/规则/gold/价格/地域/环境等缺失0send；client bool、UUID、key存在不授予权限；synthetic命名空间不可GO|
|L08–L11|发送前exact单item/page1而非截取多项；真实当前binding/schema/price/单位/hash及合同facts/原件/版本/立场漂移拒绝|
|L12–L16|唯一T08 exact Factory；正预算/正确单位与数量上限；未知持久/幂等0重发；并发一次claim、短事务无request长Session|
|L17–L19|发送前撤权/漂移0send；发送后失败仍保留durable费用/raw；日志无反射；新Database的restore fence阻断新smoke|
|L20|qcc-smoke只内部approval-id/plan-id，参数/force/key/region不能伪造授权；根拥有真实CLI执行|
|L21–L23|六类refs不能冒实际readiness；mock/40短虚构/null法律指标不可GO；一字或版本变化旧readiness失效|
|L24–L26|一次真实硬FAIL立即NO_GO，缺证BLOCKED；影子每案成本/误报漏报/修改效果/分钟未知保持null/unknown；交付文件如实分列工程/法律/live/生产|

未来缺门负测需证明实际消费被测的服务器输入。仅所有场景命中同一个更早的全局BLOCKED，或supplier计数0，不足以证明其后的exact scope/价格漂移/预算/幂等门已实现；未走到的分支继续NOT_RUN。模拟scope正例必须明确synthetic、后台登记exact一项page1，使用实际受控localhost SDK及持久账本，不用FakeTransport绕过事实，也不追认为现实授权。

当前准备不授权查找账户、密钥、注册、充值、同意第三方协议、真实资料上传或对外发送。若没有现实许可与用户实际批准，仍可执行纯虚构guard/受限交付测试，真实QCC/影子案例/生产GO保持BLOCKED_LIVE、NOT_RUN或PRODUCTION_BLOCKED。待根T12提交及唯一writer稳定入口后执行自有探针、保留实际RED/修复/同probe复验与共同源封证；来源/法律gold/当前发布证据的另一审阅者分母不相加成本角色PASS。
