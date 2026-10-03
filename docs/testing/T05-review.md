# T05 独立工程审阅

日期：2026-10-03；实际workspace为 `D:\Documents\ChatGPT\律所项目`。范围为v2.0 §5/7/T05、T05 detail计划与preflight、唯一domain DTO、T02–T04接口及T05新增代码。独立审阅者只读实现与正式测试，只新增忽略目录中的独立虚构probe和本记录；没有安装、抓取、真实模型/QCC、真实材料、外发或提交。Obsidian检索/保存由父节点统一完成。

## 实际验证

|实际命令|退出码|实际结果与范围|
|---|---:|---|
|`.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_state.py tests/unit/test_versions.py tests/unit/test_facts.py tests/unit/test_party.py -q --tb=short --junitxml=.audit-local/t05-review/core-before.xml`|0|79 passed，16.62s；实现稳定前基线，不算T05验收|
|`.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/t05-review/test_source_probes.py -q --tb=short --junitxml=.audit-local/t05-review/source-early.xml`|1|3 failed、2 passed，1.20s；草案、脚本URL标题壳、摘要被认证完整来源的真实失败|
|同独立source文件，`--junitxml=.audit-local/t05-review/source-expanded.xml`|1|2 failed、5 passed，1.52s；声明law位阶仍可覆盖明确draft/snippet材料状态|
|独立rule文件的 `test_nonlaw_rule_cannot_smuggle_unverified_authority`，`--junitxml=.audit-local/t05-review/nonlaw-source-red.xml`|1|1 failed，0.64s；logic规则夹带未核验synthetic源仍被批准并选中|
|独立rule文件的 `test_overlapping_versions_not_both_automatically_applied`，`--junitxml=.audit-local/t05-review/overlap-red.xml`|1|1 failed，0.67s；同ID两个批准版本条件重叠时同时选中|
|`.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_authorities.py tests/unit/test_rule_scope.py -q --tb=short --junitxml=.audit-local/t05-review/target-final.xml`|0|最终86 passed，17.30s，0 warnings；独立完整目标复跑|
|`.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/t05-review/test_source_probes.py .audit-local/t05-review/test_rule_probes.py -q --tb=short --junitxml=.audit-local/t05-review/probes-final.xml`|0|最终45 passed，10.12s，0 warnings；17 source、28 rule攻击/边界探针|
|`.venv/Scripts/python.exe -X utf8 -m pytest tests/security/test_auth.py tests/security/test_matter_access.py tests/security/test_upload.py tests/unit/test_state.py tests/unit/test_versions.py tests/unit/test_facts.py tests/unit/test_party.py -q --tb=short --junitxml=.audit-local/t05-review/core-final.xml`|0|124 passed，27.87s，1条既有Starlette/httpx弃用警告；core未再变化，不因后续evaluator窄修重复该回归|
|独立重算 `.audit-local/t05-implementation-hashes.json` 指定17份owned文件SHA256|0|17/17与作者冻结hash一致；包括三个窄core、新模块、卡/政策模板/索引、目标测试及作者证据|
|`git diff --check`|0|当前tracked改动无空白错误；不冒称此命令验证未跟踪文件全部内容|

中间独立rule运行8 passed/2测试构造枚举警告，改用正确枚举后22 passed；扩展26 passed。最终重叠修复前独立目标85 passed/23.40s与43 probes/11.99s仅为中间分母。首次source probe因审阅者sys.path错误产生1 collection error；首次原件probe因审阅者误用end_offset字段在DTO准备阶段失败。两者已修正，均不计功能RED，未过滤警告。最终原件攻击确实进入T05服务后由VERSION_CONFLICT阻断。

## 缺陷复验与结论

三组P2已在最终独立探针中关闭，无剩余已知P2：

1. 来源完整性认证过宽。初轮仅非空本地引用和文本就可认证；补URL/位阶/长度门后，声明law仍覆盖明确征求意见稿或检索摘要。现显式草案/摘要/标题壳/未知日期/不可信URL被阻断；证据引用必须是实际服务端UUID，绑定真实追加的exact UTF-8 bytes、source元信息hash和正文hash。任意文件路径、未知UUID、wrong bytes/bytearray/None不能成为证据。上传bytes及字符串候选门不证明现实真实性或实质完整性，仍需真实负责人逐项审定。本次没有认证任何现实法源。
2. 非law规则引用绕行。现所有basis的非空authority_ids都须逐源核验，selection再次核验；logic/practice/client_policy不能夹带未核验synthetic源进入选中规则。
3. 版本条件重叠。正常按事实与逐源窗口过滤后，同rule_id仍有多个匹配版本时全部missing_facts，要求负责人复核版本/时际关系；不取最高version、不删历史。独立互斥条件探针同时确认唯一匹配旧版本仍可选中，不能用最新版本替代。

独立探针还实测：event_dates只能佐证后端已确认date，不能补缺或改日期；metadata中的函数、JSON字段、非bool开关和未知专项拒绝；未确认/拒绝/错误类型/冲突例外不当作false；实际审批人role/disabled/member/grant变化立即重读；policy保存、rule批准和source证据写入在audit失败被caller捕获后继续commit也不留半写或误失效；source后继使当前批准stale/制品superseded而原快照保留。

T05消费document事实复用T04 trusted_parse，确实从授权原件重算完整ParseResult；仅通过T02存入伪解析并确认伪fact不能获得选中规则。旧fact、旧approved政策拒绝。PolicySnapshot内容hash与policy_runtime_sha256分工明确，后者另绑定当前真实案件及准确批准record；非空政策授权撤销后运行hash入口阻断。

## T06交接与限制

选择用ReviewContext.rules必须等于完整服务器RuleSnapshot.rules，以保持snapshot身份核验；模型运行context/prompt只给selection.applied及其实际选中、核验来源。不要为了prompt过滤放松选择服务的完整snapshot校验。当前14卡全draft、9源索引pending；这些不能进入运行法律结论。非空未批准preferences硬阻断；实际存储的空政策明确表示无客户偏好。

代码审阅确认业务DTO仍只在domain.py，未改schema/defaults；无默认账号/global DB或服务内隐藏commit。规则hash/批准依赖包含元信息、逐源hash/认证和固定client/version/hash政策binding；客户政策按具体案件隔离。数学/日期窗口和虚构身份grant只证明工程算法/授权关系，不证明实际中国法时际适用或实际律师批准；没有统一价款30%法定上限结论。

独立工程审阅通过，供父节点继续全套、来源门和阶段集成验证。现实规则批准仍BLOCKED_RULE_APPROVAL；法律金标准、真实法源实质核验、模型运行/生产批准与正式签发没有完成。86正式目标、45独立探针及124受影响回归的分母分开记录；不把84规格编号当tests passed。
