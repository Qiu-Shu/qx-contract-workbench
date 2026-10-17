# CH-03 建案前附件：复用核对与首个实施切片

日期：2026-10-17（Asia/Shanghai）。只读规划基线：`e46ce3c03565d1c60666ffa2151ed9a4ce972eb0`，含当前尚在验证的 CH-02A 首页工作树。实际工程：`D:\Documents\ChatGPT\律所项目`。

本文只新增实施准备记录，未实现附件、未运行测试、未读取业务材料、未启动模型。首页的当前通过数量由主执行记录管理，本文不预报其完整回归结果。依据为 [v2.1 规格](chat-first-architecture-v2.1.md) 第 4.6、5、6、10、12 节及 CH-03；旧 [迁移设计](chat-first-schema-migration-notes.md) 的“尚未实现”是历史状态，当前已实现部分以源码及 [迁移记录](../testing/chat-storage/20261017/migration-report.md) 为准。

## 1. 结论：解析与保护机制可复用，案件材料对象不能原样复用

当前未发现已实现的跨对话、接待、案件共享 `MaterialRef`／`SharedMaterialRef` 存储抽象。存在的是案件 `DocumentVersion`、接待材料名称清单、法库来源对象，以及对话的材料修订号占位。它们的权限和生命周期不同。

直接把现有合同上传改一个 URL 不成立：`DocumentVersion.matter_id` 必填，上传、读取、解析保存均授权到真实案件；旧 `AuditEvent` 与 `.cnbak` 文件证据也要求 `matter_id`。不得生成空案件、零 UUID 案件、虚假案号或把 conversation UUID 填进这些字段。

新增 `assistant/attachments.py` 负责对话收件、不可变原文及解析修订，调用现有纯解析器。HTTP 只处理认证、有限输入和 DTO；业务 DTO 仍集中于 `domain.py`。不另建通用文件平台、不复制解析器、不引入新运行依赖。

## 2. 已有能力与实际复用方式

| 当前实现 | 可复用内容 | 不可直接套用的部分 |
|---|---|---|
| `documents/docx_adapter.py::read_package/parse_docx` | ZIP 结构、真实解压量/CRC、XML、外链、修订、样式可见性、表格、未读项检查 | DOCX 解析需要 `id` 与 `baseline_view`；不能以虚假的 `DocumentVersion` 提供这两个值 |
| `documents/pdf_adapter.py::parse_pdf` | 原生 PDF 逐页文本、坐标、可见性和需人工核对状态；保留按需加载 | PDF/OCR 不作为首个附件切片的新增承诺；现有合同 PDF 能力不删除 |
| `documents/anchors.py::make_anchor`；`domain.py::Anchor/ParseResult` | 精确 quote、UTF-8 摘要、位置、具体版本 UUID；原 DTO 可保留 | UUID 身份不等于已授权；解析结果还须由对话所有权和解析修订约束 |
| `documents/ingest.py::_type/_settings` | 扩展名＋MIME＋签名三重检查、服务端资源上限思路 | `ingest/parse_document/resolve_anchor` 依赖案件授权及存储，不能直接成为对话入口 |
| `persistence.py::create_version/_remember_original` | 独立文件、排他创建、fsync、事务回滚只清理本次文件的模式 | 案件配额、状态失效、案件审计和持写事务读文件均不适用于新收件流程；不直接调用私有回滚助手冒充跨文件原子性 |
| `assistant/service.py::_owned/_snapshot` | 当前会话、律师角色、workspace、owner、已绑定案件/接待/投影接待权限，以及版本快照 | 当前 `save_message` 明确拒绝非空 `attachment_ids`；材料修订号还没有材料实体支撑 |
| `web/request_context.py` | 同源、CSRF、读入上限、认证上下文 | JSON 请求器不能直接发 multipart；前端需保持同源错误语义并新增有限上传通道 |
| `ops/workspace_backup.py`、`ops/backup.py` | 原归档格式、加密、路径/硬链接检查、引用完整性、恢复隔离 | 扫到 protected 文件不证明数据库引用完整；须加入新引用类型和归属验证 |
| `storage_schema.py`、`schema_migrations.py`、`web/workspace_upgrade.py` | 已知 schema、有序迁移、独立备份、pending 回执与恢复 | `assistant-v1` 已实际使用，不可原地改变四表结构并仍叫 v1 |

`IntakeMaterial` 只有名称与 `needed/received/checked`，不能拿它当 blob 登记；法库 `LibrarySource/LibraryOriginal` 的来源范围也不能被个人附件复用为共享公共来源。

DOCX 最小解析适配建议：在 `domain.py` 定义无案件身份的冻结解析输入，至少含 `id`、`baseline_view`，由服务器构造；原样调用 `parse_docx`。现有函数实际只读取这两个版本属性；若实施时发现新增属性依赖，应收窄提取解析输入，不使用 `model_construct` 绕开 `DocumentVersion` 校验。`ParseResult` 和 `Anchor` 可按原结构保存，无需另造一套段落定位。

## 3. 最小材料 interface 与所有权

以下为待实现契约，名称可随现有风格调整；不能据此称路由已存在。

| 操作 | 最小输入 | 结果与不变量 |
|---|---|---|
| 收件 `ingest_attachment` | 当前会话标识、conversation ID、request ID、预期 binding/materials 修订、单份文件及本机处理政策 | 返回同一不可变附件 ID/版本、服务端摘要/长度、真实读取状态；不接收 owner、物理路径或任意 matter ID |
| 请求核对 `find_attachment_request` | conversation ID、request ID | 当前权限下返回既有收件回执或未找到；未知结果先查询，禁止换键自动重传 |
| 读取 `read_attachment/read_excerpt` | conversation ID、附件版本、具体 parse revision、具体 anchor ID | 复验当前会话及归属，核对文件与 quote；不接受客户端任意 quote 当证据 |
| 原件下载 | conversation ID、附件版本 | 受控字节响应，固定安全文件名/下载头；不返回磁盘路径，不由浏览器直接打开任意文件 URL |
| 材料集合变更 | request ID、预期 materials revision、明确增减的附件版本 | 追加集合快照，比较并更新 revision；解除未使用关联不删除原件或历史来源 |

最小持久化职责建议分为三类，不扩展成通用资产系统：

1. `assistant_attachments`：不可变原件与收件回执。包含 workspace/conversation/owner（服务端填）、附件版本 ID、原文件名、MIME、byte size、SHA256、内部 blob ref、request ID/请求摘要、操作者及 UTC、政策标识、可选被替代版本；同 conversation＋request ID 唯一。相同哈希只证明字节相同，不能免授权或跨对话合并。
2. 追加式解析修订：附件版本、parse revision、解析器/规则版本、baseline、结果摘要、完整 `ParseResult` 或受保护结果引用、读取状态、待核状态、操作者/时间。重新解析不覆盖旧锚点和旧质量问题，旧引用仍可回查；解析成功不写“事实已核实”。
3. 追加式材料集合快照/操作回执：conversation、materials revision、明确的附件版本及解析修订列表、动作、request ID/摘要、操作者和 UTC。当前对话只指向最新集合；历史任务仍引用其原集合。它同时承担首次收件、解除关联、重解析改变可用来源的审计，不能借用要求 matter ID 的 `AuditEvent`。

业务类型全部在 `domain.py`；底层固定 SQL 及事务代码放 assistant 自己的模块。各版本/快照有数据库外键、唯一约束和不可变触发器。原件/解析/集合三个版本各自有含义，不把“同文件名”“同 hash”“同 anchor UUID”混为一个版本。精确引用至少包含 conversation、附件版本、parse revision、anchor ID 和 quote hash；锚点生成算法按版本与位置产生 ID，解析器升级后同位置内容可能变化，不能只凭 anchor ID 接受旧引文。

读取与写入都调用当前 `_owned` 等已有检查；归档对话拒绝新写。上传前认证、耗时步骤后再认证，服务层也检查恢复 fence。只有 conversation owner 并不足以读取后来被撤销的关联案件材料。第一版保持当前律师角色范围，不因新增附件向其他角色扩权。

## 4. 上传、解析和草稿不能形成半成品“成功”

### 4.1 原件收件与数据库登记

采用已有 SQLite＋受保护文件；不引入对象存储或消息队列。文件系统和 SQLite 不是同一事务，应按可恢复状态明确描述，不能承诺任意断电下的跨介质 ACID。

1. 短事务检查当前用户、conversation 和恢复 fence 后释放事务。可以查询已有 request ID 作为核对线索，但不能在请求摘要尚未核实前认定相同请求；也不能先用旧预期修订号或“新增附件配额已满”挡住既有成功请求的核对。
2. 在工作区同一卷的、服务器独占且不属于 protected 清单的临时位置有限读入。计算实际 hash/size，检测不完整读取、错误类型、ZIP 上限等；此时不增加材料 revision，不创建可引用原件。限额使用实际字节，不能相信 Content-Length 或文件扩展名。
3. 再开短事务，严格按此顺序执行：**复核当前会话/所有权/恢复限制 → 按 request ID 查原回执并比较完整请求摘要 → 仅对没有成功回执的新请求检查预期版本、新收件政策和新增配额**。摘要包含原请求的目标、文件实际摘要/长度、政策、元数据和预期版本，重放不得擅自换成最新版本。同键同请求返回原回执，不重新发布文件、不增加配额或材料 revision；同键不同请求返回冲突。第一次上传已经增加材料 revision 或恰好用完配额，不能使它的同键重放失败。当前授权已撤销则仍拒绝；恢复副本通过只读查询核对历史回执，不因幂等放开 POST。并发两个上传可以各自产生临时文件，最终只允许一个持久原件和回执。
4. 把已完成并 fsync 的文件以服务端 UUID 路径、独立文件方式发布到 `protected/assistant/<conversation>/<version>/original.bin`，登记不可变原件、材料集合快照、审计/回执并更新 materials revision，同一数据库提交。只在此后返回“已保存在本机”；不修改文字草稿，不建立接待或案件。
5. 正常回滚只清理本次受控创建文件。进程崩溃可能留下无引用文件：重启只能按明确上传路径/回执核对并隔离或报告；未证明归属前不得扫库删除。任何“数据库引用存在但文件缺失/摘要不符”必须阻断读取及成功备份。未引用孤立文件不得被自动当成成功附件。

备份与文件发布必须遵循现有运行实例/维护锁规则；不能拿一个仅供临时上传使用的进程锁替代备份一致性检查。首轮故障注入覆盖临时写入、发布前后、数据库提交前后和响应丢失，记录保证范围。

### 4.2 解析的独立结果与重试

登记原件后，在写事务外读取/解析；结果提交另开短事务重新检查当前会话、绑定与材料快照。解析失败保留原件和明确状态，不把上传整体伪装失败后让用户反复传一份文件。

首个切片只开放 DOCX，沿用原有不支持项与质量标记；有修订但没有明确 baseline 时显示需选择，不能默认接受修订。可以保存收到的原件而保持待解析；这与旧案件 `ingest` 的拒绝准入语义不同，须由新附件政策与 DTO 明确区分。输入文件中的指令始终只是原文。

解析状态至少区分已保存/待解析、解析中、可读、部分可读或需核对、失败/不支持。读取状态与律师核验状态分别保存。已有原件不得因为取消、解析失败、解除当前关联或转案被删除。中断任务记录真实中断或待重试，不在重启/恢复时自动启动模型、外部 OCR 或网络。

显式重解析基于固定原件版本和 baseline，生成新的 parse revision；不得复用旧成功回执覆盖不同解析配置。失去权限时不再提交可见结果，停止下一阶段；已保存的原件保留。

### 4.3 文字草稿、附件集合与发送

当前文字草稿自动保存检查完整 `ScopeSnapshot` 和 composer revision。上传会改变 materials revision，因此必须接到同一个前端写入/冲突控制机制；不能另开一条独立“成功后刷新整个表单”的异步通道覆盖正在输入的文字。

- 只有附件的首次操作也可以建立 conversation；复用原 create request ID 和未知结果核对，不能为了选择文件先建合同 matter。文件选择取消不产生空记录。
- 材料集合必须服务端持久化，刷新不能把所有历史上传重新当作本次待发送附件，也不能丢失尚未发送的选择。
- 上传登记＋材料快照＋revision＋成功回执同事务；文字编辑仍使用 composer revision，附件操作不能以旧文本更新草稿。发生文字/材料版本冲突时保留当前文字与文件选择，展示核对结果后再提交。
- CH-03A 可交付“对话收件、阅读及回查”，发送仍按真实能力关闭。不能仅删除 `save_message` 中的附件拒绝分支。
- 后续启用带附件发送时，须在原 `save_message` 原子事务内校验附件属于当前 conversation、绑定和材料修订一致、解析状态满足当前操作，然后固定到该条 message/run 的附件版本＋parse revision。消息、任务、来源快照、清除已发送草稿/附件选择一起提交；失败全部保持。文本为空但确有合法附件的发送语义也需同步改 DTO，现 `nonblank_message` 仍拒绝空文字。
- 服务器校验成功并不等于模型已执行；当前 queued 仍是意图。跨对话切换沿用 view epoch，晚到的上传/解析回执不能加入新对话；撤权按 CH-02A 已修复的清空规则处理。

## 5. 迁移与备份必须属于首个可交付附件切片

### 5.1 新 schema 版本，不改写 assistant-v1 历史

当前 `storage_schema._ASSISTANT_ROWS` 由 `assistant.schema.expected_objects()` 生成，`schema_rows` 还用 `version == CURRENT_VERSION` 决定追加对象。直接把 CURRENT_VERSION 改名再扩展当前 STATEMENTS，会使旧 assistant-v1 的识别错误；这是接下来必须一起修改的调用点。

建议新版本名 `assistant-attachments-v1`，保留确切 assistant-v1 四表/索引/触发器基线；schema catalog 改为明确累计每一步，而不是“只对当前版加 assistant”。`schema_migrations.statements_for`、native `workspace_upgrade`、bootstrap 和标记同步接入新步；每一步独立备份与回执，不覆盖旧 `upgrade-assistant-v1.json`。

历史两种 schema 摘要算法继续分开：native 原始 sqlite_master 与归档规范化摘要不得互换。未知表、缺触发器、伪造 marker 仍拒绝；不能用 `create_all` 自动补齐损坏。旧有效归档先完整核验原字节/原 schema/引用，再在独立恢复 staging 中升级，最后设置 fence。旧安装器不能直接打开升级后的库，回退依既有迁移前备份，并保留升级后新增资料。

### 5.2 首片完整附件恢复走 qxbak；cnbak 保留原契约

| 路径 | 当前事实 | 首个切片的可承诺范围 |
|---|---|---|
| `.qxbak` / `workspace_backup` | 枚举 protected，验证文件、工作区、已知 schema，调用共同 `_file_references`；恢复隔离且撤销旧会话 | 将附件原件、外置解析结果/衍生文件加入引用；核对 conversation/workspace/owner、版本、路径/hash/size；恢复副本可读历史附件但禁止上传/重解析/移除 |
| `.cnbak` / `backup` | 仅合成登记材料与 SyntheticKeyStore；创建及恢复使用 `normalized_schema(..., native=False)`，不含 `local_workspace_identity`；文件证据 `BackupFileEvidence` 必须 matter_id，kind 仅 original/export/patch | 保留现有合成归档、已支持旧包与已知非原生 schema 升级的回归；**不承诺原生对话附件经 cnbak 恢复后可由附件服务读取**。不为此直接新增附件证据类型或放宽旧 DTO；出现不在声明范围的附件引用必须明确拒绝，不能静默遗漏后宣称完整恢复 |

原因是附件服务复用 `_owned → _workspace_id`，后者要求 `local_workspace_identity` 恰好一行并与 conversation 匹配；把 native 工作区直接交给现有 cnbak schema 校验会失败，而仅恢复非原生数据库也不能自动满足对话服务身份。不能删身份表凑归档、临时生成新 workspace UUID、跳过服务身份校验，或把 native=False 改成宽松识别来假接通。

首片扩展共同 `_file_references` 的内部引用，让 qxbak 核对附件所有权、路径、hash、size 并进入 relocation；它不等于扩展 cnbak 的归档 DTO。调用方须明确支持的引用种类，cnbak 对不支持的附件引用拒绝而不是过滤。`.qxbak` 的 manifest 仍用既有文件清单，不另造附件备份格式。新附件 schema 在非原生合成库中为空的现有路径可继续严格迁移/回归，不能仅因表已存在就声称有附件服务可读性。

若以后确需 cnbak 承载对话附件，另行定义并验证原生/非原生身份与 schema 契约、恢复后的服务入口，以及区分所有权的文件证据变体；保持旧 format-1 读取，并将新增原件种类纳入合成 hash 政策，不能因 kind 改名绕过准入。此项不属于 CH-03A，不阻塞先完成原生 qxbak 闭环。

若解析结果全部在数据库中，首个切片不为了 source_map_ref 再存重复文件；若存文件则必须登记引用，不能靠目录恰好被打包。

旧 schema 没附件表只能在已识别支持版本下跳过附件查询，不使用宽松“缺表就略过”。恢复 fence 除拦截 HTTP 还拦直接服务写入；附件读取路由加入精确只读白名单，路径前缀不能放开所有 assistant API。恢复时不自动重解析或继续未完成上传。

## 6. 转入合同与后续方法卡的接口

首个切片不自动转案。用户明确转入已有/新建的真实办理事项后，仍经过既有接待转换及案件权限；同时检查源 conversation 读取权限和目标 matter 上传权限。

交接用校验后的同字节独立复制，调用目标现有登记与解析，不用硬链接、共享同一路径或绕过目标 `LocalMaterialPolicy`。保存固定交接回执：源 conversation/附件版本/parse revision、原件 hash、目标 matter/document version、映射规则版本、请求 ID/摘要与操作者。目标原件 UUID 变化会导致 `make_anchor` 的锚点 ID 变化，不能把源 anchor ID 原样当目标 ID。按部件/位置/quote hash 复验并记录映射；找不到唯一匹配就标记无法映射，不伪造来源。

原始资料和解析可读性不等于外发许可。主模型、Jev、持衡、方法卡使用均引用明确版本及允许内容集合；本机脱敏衍生版本另留 source mapping、脱敏规则版本及审阅状态。首片不做自动脱敏或外发；没有可靠映射不得把材料送给 Jev，旧本机人工政策 `external_processing=False` 不改。

## 7. 首个实施切片：CH-03A 本机 DOCX 收件与可核对读取

顺序以当前首页回归完成、源码解除冻结后开始；不与正在运行的回归抢写源码。

1. 固定旧 assistant-v1 schema，新增材料 schema、DTO、版本识别/受控迁移；写旧库/旧归档兼容及中断失败用例。
2. 新收件 module 复用当前对话授权、资源上限及 DOCX 解析；实现同请求去重、受保护原件、追加解析状态、集合快照和精确片段读取。不改旧案件路径。
3. 完成原生 qxbak 的附件引用与只读恢复，证明确切原件、工作区身份及解析修订恢复一致后再开放上传；cnbak 保留既有严格契约和回归，对未支持附件引用明确拒绝。此步骤不通过扩大 cnbak 归档范围来替代原生恢复验证。
4. 接同源上传、按 request ID 核对、附件列表/下载/片段接口；UI 显示真实附件卡片及本次集合，结合现有状态控制处理文字/附件竞争、重载和撤权。没有模型输出的按钮保持真实状态。
5. 独立复核实际变更；只用合成 DOCX 在新隔离工作区跑目标回归、当前冻结程序/实际 Electron 路径、备份恢复，并保存命令/退出码/计数及源摘要后提交。

必要验证按行为组织，不为所有实现细节造测试：

| 行为 | 应看到的证据 |
|---|---|
| 无案件收件 | 仅 conversation/附件/快照增加，matter 与 intake 行数不变；空白打开/取消选择不建记录 |
| 原件及来源 | 中文路径与文件名、摘要/长度、原文精确回查；原文件未改；修订/隐藏样式/复杂对象沿现解析器保留未读项 |
| 身份隔离 | 同 hash 的他人/其他对话文件仍不能读；会话撤销、案件成员移除、接待已转案权限变化在提交/下载前均重新检查 |
| 输入与资源 | 错 MIME/签名、未知格式、超限、截断/坏 ZIP/不完整 stream 明确失败，配额/原件/快照不残缺提交 |
| 幂等和崩溃 | 同键同内容仅一个持久文件与回执；首次已增加修订或用满配额后仍返回原回执；同键不同内容冲突；撤权/恢复限制仍生效；响应丢失查回原记录；崩溃孤立文件不会被视为成功材料 |
| 短事务 | 慢上传/慢解析期间另一对话合法草稿可完成；无 BEGIN IMMEDIATE 跨整个读取或解析；结果回传前撤权不提交 |
| 文字/附件竞争 | 打字中上传、上传中切换技能/对话、重载、两窗口冲突，不覆盖文字、不丢附件选择、不跨对话显示 |
| 历史引用 | 重新解析产生新 revision，旧 message/run 引用保持原映射；取消/解除关联不删除原件和已使用来源 |
| 备份恢复 | 原生 qxbak 恢复后身份、原件和解析修订可由当前授权服务读回；缺原件、错误 hash/size、路径重定向/硬链接、缺解析文件均拒绝；受支持旧包仍可读；恢复副本不得写、重跑或联网；cnbak 未支持的附件引用拒绝，不能冒称附件服务恢复成功 |

复用现有 `test_document_reparse.py`、`test_docx_office_parts.py`、`test_local_material_boundaries.py`、`test_assistant_storage.py`、`test_assistant_control.py`、`test_assistant_routes.py`、`test_assistant_backup.py`、`test_storage_schema_versions.py`、`test_workspace_upgrade.py`、`test_workspace_backup.py` 与 `test_backup_restore.py`；新增仅覆盖对话附件新 interface 的用例。不要无变化重做真实法库导入、旧全套或已有解析器所有样本。新增附件影响面收敛后再选择合适完整回归。

## 8. 执行前需落实的工程选择与明确未实现项

以下不是向用户重复请求批准，执行者可依据既有授权与源码完成最小选择，并记录实际决定：

- **收件政策**：定义独立、本机处理且外发关闭的 assistant 政策和可审计接纳动作；开发/普通 CI 只允许独立合成材料。不得沿用用户开发工具权限为全部产品用户授予真实材料外发。真实工作区启用前须满足该产品政策，不能只因测试通过默认开启。
- **配额**：首片复用现有服务器文件大小、解压上限；为 conversation 文件数/总量使用有明确名称的有限上限。可从当前案件上限取保守值但不能让 UI 自由提高；具体数值与测试一起固定。
- **资料 revision 时点**：收件、解除选择、有效解析修订分别何时增加 materials revision，在一个 module 中定义，避免三个 caller 各自加一；建议每次改变有效来源集合只增一次。原件已登记但解析未完成必须仍可见，不能以延迟 revision 隐瞒材料变化。
- **恢复/审计证据**：新附件 schema 名称、三类持久化的物理表名及 qxbak 内部附件引用规则须在首片定稿；cnbak 附件身份/schema/证据契约另列待办，旧 schema 和旧 manifest 的精确校验不弱化。

明确未实现：CH-03A 本身、cnbak 对话附件服务可读恢复、带附件发送、PDF/OCR 的对话入口、自动脱敏衍生版本、主模型/Jev 调用、自动档案投影、合同同字节交接、持衡接收与方法卡引用。本文的设计不使以上能力变成完成状态。缺这些后续能力不阻塞先实现本机 DOCX 的安全收件与回查；首片完成也不能宣称 CH-03 全部完成。

## 9. 本次核对来源

- 产品/架构：[v2.1](chat-first-architecture-v2.1.md)、[模块职责](chat-first-boundaries.md)、[迁移实施记录](../testing/chat-storage/20261017/migration-report.md)。
- 当前材料：`src/cn_contract/documents/ingest.py:40`、`documents/docx_adapter.py:370`、`documents/pdf_adapter.py:17`、`documents/anchors.py:8`、`persistence.py:268/294/515`；CodeGraph 以实际仓库路径定位，具体约束由返回的当前源码核对。
- 当前对话：`assistant/schema.py:5`、`assistant/service.py:32/61/80/211/225`（233–245 的既有消息重放先查同键回执，再检查新增运行条件与预期版本）、`domain.py:2505/2529/2535`，以及当前首页模块；附件 ID 输入存在但服务明确拒绝非空，不能称附件已接通。
- 备份/恢复：`ops/backup.py:143/159/184/192/283`（schema reference 与恢复匹配均未传 native=True）、`ops/workspace_backup.py:87/129/243/295/330`、`ops/storage.py:37/50`、`web/recovery.py:19`、`domain.py:2294`。
- 版本/迁移：`storage_schema.py:6/18`、`schema_migrations.py:9/19`、`web/workspace_upgrade.py:83`；业务 DTO 和案件审计为 `domain.py::DocumentVersion/Anchor/ParseResult/AuditEvent`。
- Obsidian 当前项目记录与 TencentDB 项目快照已检索；所记 cfc3801、旧回归和首页未接通属于历史，使用当前 e46ce3c 及工作树核对，不拿记忆回执代替本轮实测。

本次未运行测试、未联网研究或下载依赖，未修改冻结源码/测试/桌面资源。下一执行阶段须按实际实现另行取证。

独立规格复核提出两处必要澄清：幂等回执需先于新请求版本／配额检查；cnbak 不能凭文件证据扩展就宣称满足原生对话身份要求。两处已据源码修正并限定复核关闭，0 未关闭问题；这是规划复核，不是附件实现或运行验收。
