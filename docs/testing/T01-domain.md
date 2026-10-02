# T01 领域模型实际记录

日期：2026-10-02。实现范围：`src/cn_contract/domain.py`、包公开接口、`tests/unit/test_domain.py`。所有输入均为本任务独立编写的虚构材料，没有读取原包 A、真实合同、企查查结果、账户或密钥。本模块无文件、网络、数据库或工具执行。

## 已实现的模型边界

- `DomainModel`统一 Pydantic 2 校验，`extra='forbid'`；全部实体及 DTO 冻结，序列集合用 tuple/frozenset；JSON 快照及参数中的嵌套字典/列表拒绝常规原地修改，JSON 序列化仍保持对象/数组。
- 内部对象 ID 均用 UUID。位置/立场必须显式提供；建案阶段允许显式 `null`，不默认甲方。字段声明为 `T | None` 且没有默认值时，仍要求调用者传入该字段。
- Actor 的 Role 严格采用规格§1的 admin、handling_lawyer、reviewing_lawyer、assistant；拒绝另造的角色词汇。角色和案件授权的数据库真实性由后续 T02 校验。
- 货币、积分、比例及运算数值采用 `Decimal`；精确字符串、整数或 Decimal 可输入，二进制 float、bool、非有限值不可作为 Decimal 输入。积分非负；JSON 中 Decimal 序列化为精确字符串。
- Fact.typed_value 与 FactDecision.confirmed_value 使用 `{kind,value}` 判别 DTO：text、bool、integer、decimal、date、datetime、null。禁止无标签的裸值；字符串“0.1000”不会被猜成数值，Decimal/date/datetime不会在 JSON 往返后退化为字符串。Decimal事实必须有非空 Fact.unit。FactDecision仍绑定已有事实，T04处理更正时须保留或重新确认该事实的单位。
- 时间字段使用 timezone-aware datetime，拒绝无时区输入，规范化为 UTC。法源业务日期使用 date，与获取时间分开。
- `sales/service/lease/nda` 保留原类型并走 `full`；`unknown` 走 `specialist`，不接受上游 `general`。分流通过 Matter/RunManifest 的只读 `review_route` 属性取得；执行范围仍须由审查服务核对。
- ReviewRun 恰好有 C01–C18 共18个不同维度；拒绝缺项、重复、未知/伪造编号。Finding/coverage 双向关联、run_id 归属及 Finding ID 唯一性在模型内校验。`not_applicable` 和 `reviewed_no_issue` 必须有非空理由，不能关联风险发现；`reviewed_issue` 必须关联发现。
- Anchor 原文 SHA-256 与 `[start,end)` 字符范围验证；表格坐标必须完整且从0开始；PDF须从1开始的页码和有限有序 bbox。ParseResult 不允许混入其他文档版本锚点；EvidenceBundle 键必须等于对象 ID；FactSnapshot 不允许重复事实、错版本或混案事实。
- 确认事实要求确认人/时间；批准规则要求批准人/时间，法律规则还须有法源引用；开启工具绑定要求批准人/时间/价格快照引用；批准/应用补丁要求批准人并核对旧文本哈希；正式制品要求 approval_id。这些是结构条件，不能替代数据库权限、实际证据核验或批准服务。
- SafeExpression 是带 discriminator 的白名单 AST，只允许 literal、variable、binary 及明确运算枚举；它不会执行代码或公式。VerificationResult/ValidationResult 不允许有 errors 却声称 ok；验证不会改变业务批准状态。

## 规格对象盘点

§5表的17个主实体已定义，最低字段全部保留：Matter、DocumentVersion、Anchor、Fact、Party、Authority、Rule、Finding、CoverageItem、ReviewRun、ToolBinding、QueryPlan、QueryReceipt、Patch、Approval、ExportArtifact、AuditEvent。

规格附加对象 GateIssue、§9的 BudgetEntry 以及具名 RunManifest 已定义。

§5.3 的41个具名 DTO 全部定义：

|规格行|规范模型|
|---|---|
|参与人|Actor|
|上传|VersionInput、UploadMeta|
|解析|ParseResult、AnchoredSpan|
|事实|FactDecision、FactSnapshot|
|计算|SafeExpression、CalculationResult|
|主体|PartyCandidate、PartyDecision|
|上下文/证据|ReviewContext、EvidenceBundle|
|规则|RuleSnapshot、RuleSelection|
|法源/批准|AuthorityInput、ApprovalEvidence|
|模型|ModelRequest、ModelResponse|
|供应商/工具/绑定|ProviderConfig、ToolCatalog、BindingInput|
|供应商结果/对账|ProviderResult、BillingEvidence|
|查询/预留|QueryPlanInput、Reservation|
|补丁/制品|PatchResult、ArtifactBundle|
|校验|VerificationResult、ValidationResult|
|任务|JobInput、JobStatus|
|验收|AcceptanceCase、EvaluationReport|
|发布|ReleaseConfig、ReleaseManifest|
|外传/备份|EgressPolicy、BackupConfig、BackupReport|
|就绪|ReadinessEvidence、ReadinessDecision|

`Audience = Literal['internal','client','counterparty']` 与 `EvaluationMode = Literal['offline','approved_model','live_guarded']` 另行定义，不计为 Pydantic 模型。

61个规范模型加22个结构化嵌套模型，共83个模型，不含基类。嵌套模型为 HumanDecision、ModelUsage、QueryItemInput、QueryPlanItem、LiteralExpression、VariableExpression、BinaryExpression、CalculationInput、RoundingSpec、PolicySnapshot、RuleExclusion、ModelUsageLimit、ToolDefinition、EvaluationCaseResult、ExecutionEvidence，以及 TextFactValue、BooleanFactValue、IntegerFactValue、DecimalFactValue、DateFactValue、DatetimeFactValue、NullFactValue；它们承载辅助 DTO 的复合字段，不是新业务流程。

本次在首次自有 v2.0 schema 基线明确了两个必要字段：RunManifest 的 required `contract_type`，使审查 schema 保留首发四类和专项分流；AuthorityInput/Authority 的 required nullable `fetched_at`，满足来源业务时间与获取时间分开保存，fetch_status=fetched 时不得为空。RunManifest 保留全部文档/事实/规则/偏好/模型配置/总配置哈希及 model_provider；默认 schema_version=2.0、model_provider=mock。未来对已发布基线的字段扩展须升级 schema 版本。

DTO复合字段使用上述结构化模型。原始工具 JSON schema、供应商 payload、工具参数等外部数据仍是受 JSON 类型约束的字典；它们是待校验数据，不是执行授权。ModelRequest 的 Python 字段名 `output_schema` 用 `schema` 作为外部输入/输出别名，避免覆盖 Pydantic 的方法名；该模型配置 `serialize_by_alias=True`，标准 `model_dump_json()` 与 `model_validate_json()` 可直接往返。

独立审核后在尚未发版的 v2.0 基线内明确了事实值字段的内部结构。例如：`typed_value={"kind":"decimal","value":"0.1000"}` 且 `unit="CNY"`；文本形式为 `{"kind":"text","value":"0.1000"}`，未知值形式为 `{"kind":"null","value":null}`。七种值模型均禁止额外字段；bool/integer/text不互相强制转换；date只接受date或YYYY-MM-DD，datetime要求带时区时间戳并规范化UTC。不改变已固定的 defaults schema_version 或配置哈希；未来已发布基线的结构变更仍须升级schema。

## TDD 实测命令与结果

以下均在 Windows PowerShell、项目 `.venv` 执行，未运行命令不记 PASS。

|步骤|实际命令|退出码|实际数量/摘要|
|---|---|---:|---|
|首轮 RED|`.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py -q --tb=short`|1|56 failed，全部为明确断言 `T01 domain implementation missing`；无语法或 collection 错误|
|首轮 GREEN|同上|0|56 passed in 0.18s|
|manifest绑定类型 RED|同上|1|1 failed、56 passed；contract_type 被 extra_forbidden 拒绝|
|manifest绑定类型 GREEN|同上|0|57 passed in 0.20s|
|DTO关系/深层参数冻结 RED|同上|1|5 failed、57 passed；预期 TypeError/ValidationError 未发生|
|DTO关系/深层参数冻结 GREEN|同上|0|62 passed in 0.19s|
|来源时间分离 RED|同上|1|1 failed、62 passed；fetched_at 被 extra_forbidden 拒绝|
|来源时间分离 GREEN|同上|0|63 passed in 0.19s|
|第一次全套回归|`.venv/Scripts/python.exe -m pytest -q --tb=short`|1|104 passed、3 failed，详见下方|
|76个模型 schema 检查|见下方实跑 Python 命令|0|`76 model schemas serialized`|
|审核前领域目标回归|`.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py -q --tb=short`|0|63 passed in 0.19s|
|CLI修复后审核前全套回归|`.venv/Scripts/python.exe -m pytest -q --tb=short`|0|108 passed in 1.84s|
|审核前76个模型 schema 检查|见下方实跑 Python 命令|0|`76 model schemas serialized`|
|Role审核修正 RED|`.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py -q --tb=short -k 'spec_roles or role_vocabulary'`|1|11 failed、1 passed、63 deselected；三个规范角色不接受、八个另造角色未拒绝|
|Role审核修正 GREEN|`.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py -q --tb=short`|0|75 passed in 0.21s|
|事实判别值审核修正 RED|同上|1|20 failed、90 passed；tagged值不接受且裸值未拒绝|
|事实判别值审核修正 GREEN|同上|0|110 passed in 0.23s；14项七类Fact/FactDecision JSON往返实际断言值类型与数值|
|ModelRequest别名审核修正 RED|`.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py -q --tb=short -k 'model_request_standard'`|1|1 failed、110 deselected；自身序列化后无法校验，缺少外部schema键|
|审核修正后最终领域目标回归|`.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py -q --tb=short`|0|111 passed in 0.24s|
|审核修正后最终全套回归|`.venv/Scripts/python.exe -m pytest -q --tb=short`|0|158 passed in 2.31s|
|审核修正后全部83个模型 schema 检查|见下方实跑 Python 命令|0|`83 model schemas serialized`；ModelRequest仍继承extra forbid/frozen/validate_default|

第一次全套回归时 CLI 同时在开发，失败名称：

- `tests/unit/test_cli.py::test_verify_defaults_reads_the_requested_file`
- `tests/unit/test_cli.py::test_verify_defaults_rejects_invalid_requested_file`
- `tests/unit/test_cli.py::test_verify_defaults_changed_file_is_not_baseline`

三项均为 `scripts/verify_defaults.py` 尚未读取所请求配置路径，返回码错误为0；领域任务没有修改该脚本。父任务随后修复该脚本，本任务重跑全套得到108 passed、exit0；保留上述失败证据。

实跑 schema 命令（逐一生成全部模型并交给 json.dumps；审核修正后实际83个）：

```powershell
.venv/Scripts/python.exe -c "import inspect,json;import cn_contract.domain as d;from pydantic import BaseModel; models=[c for c in vars(d).values() if inspect.isclass(c) and issubclass(c,BaseModel) and c.__module__==d.__name__ and c is not d.DomainModel];[json.dumps(c.model_json_schema()) for c in models];print(f'{len(models)} model schemas serialized')"
```

## 对外接口及未完成范围

包公开导出 Actor、ContractType、CoverageItem、Finding、Matter、ReviewRun、RunManifest、validate_review。所有其他规范类型在 domain.py 中单一定义；`validate_review(payload: dict) -> ReviewRun` 调用 `ReviewRun.model_validate`；审查 schema 从 `ReviewRun.model_json_schema()` 生成。

此记录只证明领域类型、局部关系和 schema 可生成。T02–T13 的持久化、对象级鉴权、合法状态转换、来源/许可/法源实际批准、预算原子账本、工具实际发现、模型请求、完整事实/规则适用核验、签发/审批哈希绑定、备份恢复及上线门禁尚未由本模块实现。ReadinessDecision 的 GO 必须有全部分类的证据引用，但引用真实性仍由后续服务核验；模型对象不能批准上线。Pydantic `model_construct`/未校验的 `model_copy(update=...)` 是内部逃生接口，领域服务应使用 `model_validate` 创建更改后的快照。

工程演示、法律样本验收、真实试点批准、生产完成仍为独立状态。模型默认 mock，企查查关闭，mock 不得正式签发；本任务没有执行真实查询、付费操作、真实材料外传或法律样本验收。
