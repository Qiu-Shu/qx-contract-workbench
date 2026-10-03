# T13 上线证据只读审阅准备

PLANNING_ONLY / NOT_RUN。仅读取本机现有文本、AST与hash；本轮不执行应用、guard测试、真实请求、账户/密钥查找或环境变更。来源为v2.0 T13、§14.1/15/17、T13执行/细化安排和本轮实际源码。

T12现已具备并实际验证受限合成恢复，独立54检查封证见T12-restore-final-review.md；旧T13-current-preflight所写“T12尚未实现”属于当时历史，不改写它。真实国内host/OS隔离/TLS/数据政策/密钥托管仍未部署或批准，恢复成功不代表完整沙箱或生产完成。

ReadinessEvidence现有六类非空引用只证明数据形状。ReadinessDecision仅检查六类tuple非空；任意UUID/路径或构造成功不证明实际证据、批准角色、hash、范围、当前版本、时间或撤销。未来assess_go_live必须读取服务器受保护登记和实际字节，不能由调用方描述授予真实GO。

|项|当前可复用事实|未来实际断言（本轮全部NOT_RUN）|
|---|---|---|
|R01 六引用只表达形状|domain.ReadinessEvidence/Decision：六tuple NonEmpty；GO validator仅核每类非空。|同六非空任意UUID/路径/payload不得GO；必须经后端解析实际登记。|
|R02 受保护server登记|T02会话/成员及T05受保护source evidence已有入口；T13专用登记尚未实现。|类型、ID、来源角色、实际批准主体、内容hash、scope/version/UTC期限/撤销均核；客户端bool/DTO/存在key不是授权。|
|R03 读取字节与保护路径|T12 checked_file严格路径、reparse/硬链/hash；release绑定文件bytes。|ref指向既定保护根且登记SHA一致；篡改、错类、外路径、ADS、链接、重复别名不能成为批准。|
|R04 来源/许可/runtime闭包|现有source/runtime pure gates，55 runtime＋1 build全部production approval null。|完整当前 source/runtime/build 范围及声明native/构建限制重读；开发PASS/NOTICE候选不能变生产许可。|
|R05 原始批准可信来源|T07 approval与endpoint/price/binding是后端技术记录，synthetic/live_allowed明确限制。|必须官方工具/schema/价格单位/服务账户许可和有效批准；把provider名字或synthetic标签改成真实不能放行。|
|R06 时效/当前源闭合|T11固定AST/nodeid/source/collection/hash闭合；T12 release currentness=hash-bound-only。|历史报告须绑定此次实际源码/config/rules/model/fixtures/env范围；复制旧hash或传空currentness不为当前验收。|
|R07 规则/法源与现实律师|T05默认14 draft；法源索引pending，技术fixture不是执业资格证明。|当前完整原文、原文hash/生效时点、适用例外、真实合资格批准人及规则依赖核；草案不能法律GO。|
|R08 接口/账单与未知收费|T08 reserve/claim/settle/reconcile；T12恢复实际unknown仍15used/5remain/1call。|真实字段/trace/官方账单hash与金额单位/人工批准核；sent_unknown不清零/不重放、不用mock积分冒真实费。|
|R09 84能力与guard分开|T11原84表、guard/partial/full分列，历史cap仅5PASS，未实证项不补分。|不能把guard PASS、registered static selectors、collection或全suite PASS作为84能力全达标；本源改变需关联重核。|
|R10 硬失败优先NO_GO|现assess_readiness真实hard gate status/guard/partial FAIL立即NO_GO。|服务器核实的编法源/跨案泄漏/真实外传/超额/错位/未批签发任一FAIL即NO_GO，平均分不可稀释。|
|R11 缺证据BLOCKED|T12 production manifest缺host/OS/TLS/policy/gold/shadow且null审批。|任一必需项缺失/NOT_RUN或无有效批准=BLOCKED；不得因证据列表非空、模拟complete、同人称双审变GO。|
|R12 双律师真实gold|T11 40短工程材料、16family/24dev16预留blind，实际两reviewer/gold空。|两名真实独立律师审阅及分歧协调证据；现实scope/sample provenance与分母核；writer可见blind预留不是独立盲测。|
|R13 四类指标/分母/边界|v2 §14.1 95%召回/85%精确/99%锚点为待批准目标，法律scores null。|逐sales/service/lease/nda TP/FP/FN/重大分母/样本量与失败原因核；阈值不当成绩、困难/NS项不删除抬分。|
|R14 影子逐案成本/人工分钟|当前真实shadow未运行，EvaluationReport cost/human_review_minutes null。|保护逐案费用单位/误报漏报/修改效果/人工分钟与实际复核人、范围、日期、批准及源hash；无记录unknown/NOT_RUN。|
|R15 恢复/单实例/永久隔离|T12独立54实际恢复已封：38表、原件/制品、unknown、旧sessions/jobs/current批准持久fence。|恢复受限功能并非真实部署；当前隔离实例不准现签发/外发，尚无解除fence方案；不得把恢复PASS变全OS环境PASS。|
|R16 国内host/TLS/OS地域|T12只有应用gate、数字loopback、无生产region/OS隔离/TLS批准。|实际获准国内host/HTTPS/key custody/单实例与受限worker/OS外网隔离部署记录；Python/helper检查不能证明完整沙箱。|
|R17 mock/synthetic范围|现T09 mock水印且正式签发blocked，T07 transport仅synthetic/mock/loopback。|任何synthetic scope、mock模型、模拟账单/身份、source研究scope都永远不能真实GO；模拟正例须独立标注。|
|R18 仅exact单项一页smoke|T08 execute_plan遍历所有items/pages，create/read/approve重核snapshot。|T13必须发送前核已批immutable计划恰1item/page1/明确主体；不能从多项临时截1，走唯一T08边界、不备用SDK重试。|
|R19 实际会话/actor/预算批准|会话token/CSRF/成员后端核，admin不当然跨案；plan/binding价格hash实际重读。|独立现会话、本案权限/授权人、计划hash/批准期限/正预算/资料用途地域均核，approval UUID或环境key不算授权。|
|R20 CLI与三交付件|当前CLI已有release-manifest但未qcc-smoke；T13两个服务和三交付文件尚缺。|真实missing批准CLI非0/供应商0/费用0；LIVE_READINESS、SHADOW_RUN_REPORT、GO_NO_GO按实写受限内部交付。|
|R21 最终证据最小准入|当前T12 source/owned seal与T11历史报告保持，不由评测者替法律批准。|current evidence registry全部独立类型核验；证据非法不自动转positive，硬FAIL与missing理由分列；生产仍BLOCKED_LIVE。|

服务端核实的硬FAIL优先NO_GO；任何必需批准/证据缺失或未运行保持BLOCKED。合成scope/mock、source研究候选、历史工程全套通过、影子阈值与工程耗时不能替代真实法律gold或律师复核分钟。即使六refs齐全，也必须分别核许可/规则/接口账单/当前84能力/真实盲测/影子结果及环境恢复范围。

建议纯虚构的后续失败探针覆盖：同六任意非空refs、错类/路径/hash/版本/UTC/过期/撤销/角色/案件、未经保护登记、gold仅一律师或scope synthetic、每类型重大分母缺失、阈值当成绩、影子无成本/人工分钟、guard当capability、硬FAIL混入平均分、restore PASS当OS/TLS国内部署、mock真实GO。全部预建议NOT_RUN；当前用户未授权注册账户、付费、上传真实资料或真实联调。

实际只读准备命令退出0；21条规划映射、86源输入、72 AST文件，前后漂移0。当前run_live_smoke/assess_go_live定义0处，CLI现parser为config-validate, demo, demo-server, evaluate, release-manifest, schema；runtime55＋build1，production批准非空各0/0。该统计仅读JSON，不重跑source/runtime gate或安装验证。完整摘录、行号/hash/计数与命令在.audit-local/t13-readiness-review/preparation.json。

探索命令的缺路径/无匹配仅辅助发现，不能记功能RED。旧T12独审及T11/T13预检封证保持原bytes；本准备不是新T13guard执行、法律验收或真实上线结果。
