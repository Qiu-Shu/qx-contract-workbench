# T09 独立导出业务审阅

状态 INDEPENDENT_ENGINEERING_REVIEW_COMPLETE（2026-10-03）。已在作者同一75项最终冻结上执行三组验证并封证；无剩余已知P1/P2。最初exports尚未交付的NOT_RUN历史保留在baseline，不继承T08、依赖候选或父节点Word兼容smoke结果，也不把作者初13当完整验收。工程审阅结论仅针对独立虚构材料，不代表法律、真实供应商、试点或生产批准。

已读spec§10/T09、T09-preflight、domain唯一Patch/Approval/ExportArtifact/ArtifactBundle，实际T03原件及resolve_anchor/T06read_run-current_manifest/T08receipt与T02授权/基础批准投影。T09-detail当前不存在，记文件读取诊断，不算业务RED。独立矩阵E01–E20在 `.audit-local/t09-export-review/PLAN.md`，全部NOT_RUN。

重点是exact whole-anchor跨run/真实revision、实际patch批准/hash/current版本、三audience全ZIP与旧批注/props/hiddenpart过滤、mock formal硬阻断、高风险双人/真实负责人例外记录、不可变文件/manifest/hash、权限先读与跨案不泄漏、caller捕获继续commit无半写。对外红线副本同样必须过滤或明确阻断风险部件，不能只滤新report字段。表格/复杂对象可靠manual不算自动修改能力PASS。

审阅只写ignored证据与本文，不改业务/正式tests/锁/status，不跑whole/Word/COM/额外nativehelper，不安装或注入bundled依赖、不联网/外部/真实材料/commit/Vault。后续按实际项目固定依赖正常服务测试，Word真正visual父节点单列，XML/mocks不替代视觉或法律验收。待唯一作者API与helper稳定再真实执行，最终源/样例SHA与count/exit全部按实际证据填写。

已按实际首批helper签名草拟独立probe，覆盖跨run的每段格式/空白、literal XML、table/bookmark/field及确认过基线的旧revision、6类原件隐藏部件×2对外受众、无批准修改时对方报告不带完整意见、批准受众范围、8种会话/成员撤销边界、事实/立场/政策变化、撤销patch后旧bundle下载、同UUID跨案、先授权后文件读取、savepoint及outer rollback文件清理、部分磁盘写异常，以及高风险实际第二reviewing身份及其当前资格撤销。高风险fixture在服务器生成意见时明确产生虚构high结果，不用caller Run DTO伪造批准，不给mock正式签发。Windows junction仅允许在probe自己的pytest tmpdir创建，以验证路径能否被重定向，不改用户目录或系统设置。

`probe-draft.json`记录一次`python -B -S`纯AST读取退出0；它没有import项目模块/运行pytest，不计业务测试或验收。源码、原始四fixture及provenance的初始hash保存在`baseline.json`；最初T09-detail文件不存在是读取诊断，不是功能RED。后续每次实际pytest由`run_probe.py`写完整命令、exit、JUnit数量和源码/样例prepost hash；作者实现期间变化不会被冒称冻结一致。

## 已实际执行的增量审阅

每条完整argv/UTC/exit/count/源码前后hash在同名JSON及`commands.jsonl`，JUnit和日志均位于`.audit-local/t09-export-review/`。这是同一阶段增量复验，数量不能相加冒称独立不重复分母。

|证据label|实际exit/pytest结果|解释|
|---|---|---|
|initial|1；41 passed/4 failed/4 warnings，45.74秒|45项收集执行。3真实P2：部分write残片、高风险复核角色撤去后旧批准仍用、owned-temp Windows junction重定向导出；另1个FactSnapshot(version3)含version2 facts是审阅fixture适配错误，不算业务RED。4条警告来自fixture的str enum，已改唯一domain枚举。作者期间改helper与正式目标文件，prepost已明确记录，非冻结通过。|
|expanded-narrow|1；9 passed/1 failed/0 warnings，12.23秒|10项same-probe/追加边界。前3真实P2已GREEN，facts构造修正后实际stale通过；硬链接与生成后junction替换被拒绝。新table manual真实P2：位置与批准新旧文/说明分在两张无绑定表，人工不能准确对应。源码prepost无变化。|
|manual-expanded|0；6 passed/0 warnings，7.87秒|manual完整同项行P2原probe GREEN；实际规则v2注册使旧件superseded/不可下载、100001旧revision保留及新ID避撞、重复/同anchor重叠patch拒绝、新preview保留旧artifact bytes/id均通过。期间正式unit test改动已记录，非finalfreeze。|
|current-high-atomic|0；6 passed/0 warnings，7.40秒|无can_sign实际不同reviewing可批draft、formal拒绝；高风险批准人actualsession/member/disabled三种撤销阻断bundle与standalone；prepare末尾立场改变后catchcommit无半候选/文件；撤销patch后standalone拒绝。期间正式integration/security文件变动已记录，非finalfreeze。|

四类独立实证P2都已告唯一作者和父节点，并原probe闭合。作者另发现并修复同run两current DOCX的版本与anchor归属混配；独立two-document-ownership实际1 passed/0 warnings/exit0/1.74秒，同时验证同字节同SHA两个文件仍需正确version+anchor绑定。该问题的初始功能RED归作者，不冒称独立发现；其fixture前期辅助错误没有被计入功能RED。高风险session current检查和standalone修订读取撤销检查，也已用实际服务验证。

父节点已明确并由上述六项实际验证：高风险draft第二名必须是不同的当前reviewing_lawyer及有效案件成员/调用会话；`can_sign`仅用于formal签发，不应用作draft修改批准资格。无can_sign的reviewing成员仍只获draft、formal拒绝。普通handling批准与高风险reviewing资格分开核验，Actor.roles自报不是权限证明。

范围撤销的实际覆盖指patch批准audiences/对外修改范围。当前T06 run严格QCC0且无外部receipt；QCC receipt→报告消费者NOT_IMPLEMENTED，不拿T08合成gateway收据当已完成外查报告集成，也不要求无关外查scope变动使无外查run失效。Windowsjunction/硬链接仅测试自己owned tmpdir，无系统设置或用户目录操作。

## 同冻结最终证据

作者冻结文件为`.audit-local/t09-author-final-freeze.json`，SHA-256 `909fc8fd9a909f9a60689741ebb3fad5df15526807db1ed310cc58149fba67f8`，75项源码/正式测试/依赖seal输入/历史作者证据逐项bytes及SHA在最终运行前后75/75匹配。三组分别运行，没有whole或CLI/demo；以下分母各自独立，不能加起来当84项规格验收。

|独立最终命令组|实际结果|证据|
|---|---|---|
|三正式目标：unit/test_patch_preconditions、integration/test_exports、security/test_approval|37 passed；exit0；0 warnings/failures/errors/skips；43.34秒|final-target.xml/log/json|
|独立服务probe完整文件|61 passed；exit0；0 warnings/failures/errors/skips；73.94秒|final-independent.xml/log/json|
|必要受影响：auth、matter_access、upload、document_parts、parsing、review_flow六文件|136 passed；exit0；0 warnings/failures/errors/skips；42.56秒|final-affected.xml/log/json|

每组完整命令、起止UTC、JUnit和源码/样例prepost SHA在同名JSON与`commands.jsonl`；三组源码/样例变化均0。`run_final.py`实际退出0，汇总在`final-runs.json`，作者seal核对在`author-freeze-before.json`及`author-freeze-after.json`。四个T06原始DOCX和provenance共5项与本审阅开始时hash一致；没有重写原fixture、生成正式gold或改评价矩阵。独立审阅自己的文档和ignored证据最后以`freeze.json`逐文件SHA封证；derived __pycache__不计源证据。

实际接口保留唯一domain DTO：approve_patch(matter_id,run_id,Patch,Actor,*,db,audiences,exception_authorization_id=None)登记精确草案修改批准；prepare_exports(ReviewRun,Audience,patches,Actor,*,db)生成不可变新candidate与整包manifest；apply_patch(DocumentVersion,Patch,*,actor,db)只对支持的完整普通正文锚点产生模拟ins/del；read_bundle/download_artifact和standalone read_patch_artifact均重验当前server记录、成员/会话/批准范围及文件hash。initialize_storage须显式Database，无默认DB或import-time存储。对外route的CSRF和浏览器旅程属于T10，本服务测试不冒称已验。

61项独立范围覆盖每个run格式/空白及接受/拒绝结构投影、XML literal、table/bookmark/field/旧revision人工处理、旧高ID及untouched部分保留、整ZIP六类隐藏canary×两个对外audience、counterparty不含未批准完整意见、audience grant/revoke、actualcaller成员/会话撤销、high批准者资格撤销及无can_sign draft关系、facts/position/policy/rule变更、重复/重叠patch、sameUUID跨案、授权先于file读、partialwrite、afterappend失败catchcommit、outerrollback及末尾current重验回滚、ownedjunction/hardlink和不可变旧preview、真实双current-doc归属。

三受众均产生fresh report；仅internal可在支持范围输出原件native redline。client/counterparty的原件全ZIP未获独立外发范围认证，实际只生成新报告并逐项manual，不能称三受众原件自动修订均PASS。复杂表格/旧修订降级正确也不能称自动编辑能力通过。所有输出DRAFT/MOCK，approve_bundle对mock一律BLOCKED_LIVE；真实非mock正式批准、真实负责人exception授权和真实外查report消费者均没有技术正例或所需证据。补丁后的整份合同法律/数值语义重审无独立服务入口，本次只证实精确结构和当前记录绑定，不能据此宣称已完成法律一致性验收。

本审阅没有启动Word/COM/渲染helper、安装包、运行真实SDK/供应商、使用外网、读写Vault或提交。正常项目固定依赖加载（包括python-docx/lxml）不被描述为“零native代码”；Windows路径探针明确在owned tmpdir调用本地文件系统命令，未变更系统ACL/防火墙/隔离设施。Word实际glyph、分页、修复告警、接受拒绝和全页visual由父节点单独记录，XML oracle与这些实际视觉记录分开；律师gold/法律指标仍未由本审阅证明。
