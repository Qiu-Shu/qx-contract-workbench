# T13 当前只读预检

状态：PLANNING_ONLY / NOT_RUN。仅实际读取当前本地文本、AST与hash；不执行T13 guard、真实查询、模型请求、账户/环境密钥查找、T12备份恢复、安装或配置变更。

v2.0 T13/§15/§17及既有T13-detail作为规格来源；本预检没有授予真实查询、付费、注册账户或真实材料上传授权。T12尚未实现，全部部署/恢复/地域/密钥托管条件是未来依赖。

当前run_live_smoke、assess_go_live、qcc-smoke及T13三份交付文档/guard测试均不存在。ReadinessEvidence的六类NonEmpty引用只表达数据形状；GO构造器仅核非空，不能替代服务端证据解析、内容/hash/版本、现实批准人、有效scope、案件/地域/用途及撤销/期限核验。

|项|可复用当前源事实|待实现/阻断|
|---|---|---|
|T13-P01 唯一readiness DTO与后端证据信任根|ReadinessEvidence有六类NonEmpty refs；ReadinessDecision GO validator仅要求各类tuple非空。|引用存在、任意UUID/路径、DTO构造成功不能证明内容、批准身份、当前版本、有效scope或真实来源。assess_go_live尚无服务。|
|T13-P02 来源、许可与依赖生产批准|来源开发与runtime门已有纯读取验证；当前13来源与55运行+1build批准未获生产许可。|须取得并重读所用目标及完整闭包实际生产批准；开发/NOTICE/static native证据不能替代许可或构建范围批准。|
|T13-P03 法源、规则与真实律师批准|T05现有规则/法源依赖hash、资格、案件与失效重读；14default卡均draft。|没有真实法源原文/规则批准；当前技术复核身份和合成源证明不能冒现实法律批准。|
|T13-P04 实际QCC接口、价格、许可、账单|T07当前注册端点、price与approval记录明确synthetic=true/live_allowed=false；固定SDK仅本机JSON子集。|真实官方工具schema、价格计费单位、服务许可、账户授权和bill provenance均缺；不能只改synthetic或provider字串放开。|
|T13-P05 会话、案件权限与执行批准主体|T02会话与案件成员后端重读；T08 authenticate_execution核token/CSRF后交给短事务网关。|T13真实执行批准需受保护记录绑定批准人、当前资格、案件、用途、资料、地域和有效期；非当前Actor DTO或持有approval_id即授权。|
|T13-P06 live smoke只允许一项最小查询|create/read/approve_plan冻结主体、binding、price、scope及hash；execute_plan当前迭代全部items与pages，Q0不发。|run_live_smoke未存在；必须预核已批immutable计划exact1 item且pages=1，禁止在多项计划中临时截取一项或发送后停止充当单项批准。|
|T13-P07 正预算、单位与已发送未知状态|T08实际reserve→mark/claim→settle短事务；unknown保留calls/credits，recover_inflight仅转sent_unknown不重放。|当前所有预算/价格仅synthetic_credit，不是实际人民币/官方积分；T13须正批准预算与正确实付单位，不能从合成0成本推真实免费。|
|T13-P08 唯一受控发送边界|FactoryQccTransport只允许synthetic mock或loopback；gateway拒任意transport/subclass；actual before_dispatch重核后单次claim。|未实现受批真实adapter与数据政策解析器；应增量沿唯一网关，不给live另设绕过预留/确认的发送函数。|
|T13-P09 secret_ref与实际凭据边界|ProviderConfig只有secret_ref；T07SecretStore仅synthetic-secret前缀的server临时map，SDK拒trust_env/redirect/auth discovery。|无真实密钥托管/授权引用；本预检不搜env、账户或key，不把可发现凭据等同人类授权。|
|T13-P10 地域、数据类型与T12受限环境|EgressPolicy/ReleaseManifest DTO可复用，当前MCP只numeric loopback，T12仍处规划。|批准国内host/HTTPS/OS外网隔离/受限解析worker/真实部署及恢复尚缺；Python检查和loopback不是完整OS沙箱或真实数据地域批准。|
|T13-P11 四类法律gold与未支持覆盖|T11登记84原表、147候选函数，40短独立虚构工程材料；gold双reviewer空，法律metrics只允许null。|author-visible blind family预留不是两名律师独立盲测；OCR/复杂对象等缺口不得移除样本抬高覆盖率。|
|T13-P12 硬失败与上线决策|T11assess_readiness任何hard gate/guard/partial FAIL立即NO_GO，否则始终BLOCKED。|T13assess_go_live缺失；要聚合真实readiness evidence、逐类型范围与zero-tolerance，并重读实际证据，不能平均分稀释硬FAIL。|
|T13-P13 qcc-smoke与T13文档/guard入口|CLI当前config/schema/demo/demo-server/evaluate；evaluate只offline并非GO时返回非零。|qcc-smoke、run_live_smoke、assess_go_live、test_live_guards及LIVE_READINESS/SHADOW_RUN_REPORT/GO_NO_GO未存在。|
|T13-P14 影子运行、每案成本与人工复核量|T11EvaluationReport cost/human_review_minutes null，真实provider requests固定0。|无影子运行批准/真实逐案误报漏报/修改效果/成本/分钟；尚不能用mock_credit或工程用时替代律师工作量。|
|T13-P15 正式签发与受限交付|T09approve_bundle重读run/patch/artifact/current后仍明确BLOCKED_LIVE；mock不能正式签发。|T13真实readiness、律师批准和签发批准必须独立；不能seed普通Approval或改mode解除现门。|
|T13-P16 T12前置与未来版本证据|T12备份/恢复/egress/build release是现规格接口，目前尚未实现；旧T12preflight仅规划。|当前T13观察不是T12验收：后续T12源码/配置改变后需重新建立readiness版本/环境hash，不复用本快照为新环境GO。|

当前单项smoke不能直接把一般execute_plan当作单项函数：现函数遍历全部items/pages；应在发送前核已批准精确计划只含一项且一页，并重核plan hash、当前主体、binding/schema/price、预算与用途/地域。临时从多项计划抽取一项不能继承原批准。

T07/T08批准记录是当前合成系统的真实后端技术记录，会重读权限与版本，但synthetic=true/live_allowed=false及synthetic_credit账单不能被追认为现实QCC许可、账户、价格或账单批准。SecretStore当前只接受synthetic-secret引用并驻内存；本预检没有查找或创建实际凭据。

当前T11工程能力与法律验收分别可见；40短样本/家族隔离/147固定函数/18维mock不等于真实法律金标准。重大召回≥95%、精确≥85%、锚点≥99%是待批目标，分数及律师gold保持空。影子成本、误报漏报、修改效果、人工分钟没有实测值时保持unknown/NOT_RUN，每类型分母单列，硬失败不得平均。

拟议实现顺序：待T12工程验收后，先四个live guard的真实RED→最小fail-closed实现→纯虚构目标回归；注册受保护批准与证据解析器；qcc-smoke仅接受内部ID。没有现实批准时以BLOCKED_LIVE/PRODUCTION_BLOCKED及受限可运行交付结束，不删除门禁，不自动轮询供应商。所有拟议测试本预检均NOT_RUN。

实际预检命令：`.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t13-current-preflight/prepare.py`，退出码0；16条规划映射、89实际源输入前后0漂移。完整AST摘录、行号、源hash、目标缺失检查及当前批准静态摘要保存在`.audit-local/t13-current-preflight/current-preflight.json`。pure AST阶段没有import应用或原生库。

探索命令中的缺路径/Windows glob语法错误/无匹配记录只作为辅助发现历史，不能计功能RED或T13测试失败；实际发现计数与退出码另存discovery-command-records.json。T11旧封证保持原bytes；此快照不覆盖T11历史或冒T12/T13已执行。
