# A1/A2：新虚构合同与离线人工候选通路

记录：2026-10-05。依据用户确认的 CR-01 律师辅助工作稿路线，复用当前案件、原件、事实确认、C1 处置及导出服务。这里只登记已执行的工程范围；独立审阅和根完整回归另记。

## 实际行为

服务端显式选择 `purpose='assisted_draft'` 并提供固定 hash 的 `SyntheticAssistedPolicy`。默认 `mock_demo`、原四份演示和 mock 注册门保持；辅助模式缺政策、mock 携带辅助政策及正式模式分别拒绝，不靠客户端字段启用。

辅助解析保留原文与锚点，保存空的未确认事实快照，不静默调用固定 mock 提取。事实候选绑定当前文件 UUID/hash 与预期事实版本，只追加未确认值，复用原文信任与完整快照确认；视觉疑点 PDF 来源不能被人工输入绕过。

意见候选绑定服务端当前案件立场、目标、文件、确认事实、规则、政策和辅助政策的上下文 hash。实际检查锚点必须属于当前可消费原文；候选无确认人、批准、供应商 usage 或执行收据字段。服务端保存不可变 `ReviewProposal` 与 `ReviewRun`、实际人工来源收据；当前读取及导出重建 proposal、manifest 和意见，不能仅改 provider 字符串。

每条意见在结构 proposal 中保存依据类型、待核引用和未知事项，同时由后端附到业务影响，律师编辑分析及建议后仍可读。待核引用不进入批准法源或规则登记。未涉及维度保持材料不足；全18维不能因保存成功变成“已审无问题”。人工来源和真实推理未运行的标识贯穿 API、实际 DOCX 正文及页眉页脚。

工作台增加原文选择、有限事实/意见字段和候选清单；不要求律师编辑 JSON。工作稿确认接线复用另一个 C2 切片，详情由该切片单独登记。本记录不是浏览器视觉验收。

## 实际执行账本

执行脚本保留逐阶段完整命令、退出码、时间与 JUnit，目录为 `.audit-local/assisted-a2-20261005/`。

|阶段|退出码|实际结果|解释|
|---|---:|---|---|
|初始 `test_assisted_review.py` RED|1|35 failed / 1 passed / 0 errors|多数为同一服务端入口缺能力，不是35个独立缺陷；默认演示拒绝全部12新源已通过|
|显式目的补充 RED|1|38 failed / 1 passed / 0 errors|三个目的和新路由尚未实现，原默认拒绝行为通过|
|模式/接口/空解析接入后的 RED|1|29 failed / 10 passed / 0 errors|有效候选尚无实现、完整旅程止于候选保存；PDF来源错误码及UI未完成|
|首轮候选实现检查|1|12 failed / 27 passed|12个失败均为测试把 `read_original` 的 bytes 返回值误当 BytesIO；均发生在实际草案下载后，不计产品缺陷|
|A2目标最终检查|0|39 passed / 0 errors / 0 warnings，225.70秒|12个新旅程、权限/版本/锚点/边界/回滚/实际输出通过|
|显式本机启动补充 RED→GREEN|1→0|2 failed → 2 passed|固定12文件清单、逐件hash/size核验、新.local目录及原单worker生命周期；修改清单拒绝|
|领域/事实/原workflow/API/C1/导出关联|0|323 passed / 0 errors / 0 warnings，183.27秒|11个明确目标文件；不是根完整测试集|
|报告schema检查、JavaScript语法检查|0 / 0|实际检查通过|默认配置 bytes 与 HEAD 相同|

39项与启动补充2项分别执行，不伪造为一次41项运行。首次 `PDF_MIME` 测试导入笔误造成的收集错误独立保存在 `aux-collection-error.*`，不计功能 RED。

## 12份实际新旅程

`tests/fixtures/assisted-v1/manifest.json` 只作为输入清单；原 `journey_status=NOT_RUN`、`model_inference=NOT_RUN`、`legal_gold=NOT_APPROVED` 元数据保留。实际结果在独立 `journeys/`，不能用修改输入清单制造成绩。

实际四类型各3份（sales/service/lease/nda，01—03）均从新文件上传开始：解析事实版本1 → 原文绑定候选版本2 → 明确确认版本3 → 保存与旧 mock 不同的两条人工意见 → 律师明确改写第一条、驳回第二条 → 实际客户 DOCX 下载及句子/字节 hash 核对 → 新处置后旧下载409 → 本案虚构复核者正式签发仍 `BLOCKED_LIVE`。原件 bytes 均等于各自输入，重复句使用第二处独立锚点；金额单位和月份按原文保留。

12个实际下载 DOCX、12个观察 JSON 均在 `.audit-local/assisted-a2-20261005/journeys/`。每个观察记录原件 hash、文件 UUID、事实版本、上下文/proposal/run hash、制品 hash、真实下载后验证、旧成果拒绝、形式签发阻断及人工收据。作者封证 `implementation-evidence.json` 重算了全部12下载的 hash，记录16个源/测试/schema的当前 hash。

每个案件实际 QCC ledger 0、model attempt 0、model operation record 0；后端人工收据明确 `manual_synthetic`、真实模型调用0、QCC调用0、推理 `NOT_RUN`。没有伪供应商 token、账单或真实模型使用量。

## 可运行本机入口

在项目目录显式启动：

```text
.venv/Scripts/python.exe -m cn_contract.web.assisted_demo_server --port 8766
```

仅监听 `127.0.0.1`，每次创建本项目 `.local` 内新的独立目录，保留既有生命周期与单后台worker。启动前核固定清单 SHA256 和12个实际文件 SHA256/size；只接受首批独立虚构文件。材料目录为 `tests/fixtures/assisted-v1/`；用户名和虚构演示密码由启动说明显示。此命令未在作者阶段绑定真实网络端口，启动构造与生命周期通过 TestClient 实际执行；真实浏览器页面操作另行验收。

真实合同、真实 DeepSeek/宿主推理、企查查、真实账户/费用/协议、法源批准、双律师 gold、网页 ChatGPT 桥、宿主调用和生产均未完成或未批准。本机人工候选工程通路不解除这些阻断。

## P2追加：页面审查维度与实际报告一致

根浏览器检查及独立审阅发现原 `workbench.js` 另一套手写18维名称错套到固定 C01—C18。例如选择 C05 时页面显示“履行义务与验收”，但实际报告 C05 为“标的交付”；C08、C09 同样错套。这是已确认的显示与选择误导缺陷，原浏览器旅程不能据此标为通过。

唯一既有中文映射为 `exports/audience_filter.py::DIMENSIONS`，与 `sources/specification-v2.0.md` §5.2 一致。`config/defaults.json` 不含中文维度，报告 schema 只锁编号；没有为迁就页面修改默认配置、schema、领域枚举、规则、报告标签或历史数据。后端将既有映射与真实 `CoverageId` 配对，向受授权页面渲染惰性 template。页面覆盖卡和人工候选下拉共同按实际 ID 读取该映射，选项可读地显示编号及名称；登录页不要求此映射。

本修复仅改 `web/app.py`、`web/templates/workbench.html`、`web/static/workbench.js`，新增 `tests/integration/test_coverage_taxonomy_ui.py`。逐阶段实际命令、退出码、时间、JUnit 和源 hash 独立存于 `.audit-local/assisted-a2-taxonomy-20261005/`，保留此前 A2 作者封证作为历史状态。

|阶段|退出码|实际结果|范围|
|---|---:|---|---|
|初始正式 RED|1|5 failed / 0 errors|HTTP 页面缺服务端映射；执行实际提供的生产 JS，C05/C08/C09 名称与规范错套|
|补登录与实际表单边界后的 RED|1|5 failed / 1 passed / 0 errors|登录通过；默认页面只检查覆盖卡，辅助页面检查候选表单。以上是同一 P2 的不同层面，不计5个独立缺陷|
|修复目标 GREEN|0|6 passed / 0 errors / 0 warnings，11.22秒|18名/ID与规范、现有报告及schema枚举一致；覆盖项打乱顺序；默认与辅助页面；登录；实际选项→API→DOCX|
|有限关联回归|0|7 passed / 0 errors / 0 warnings，21.95秒|既有六页转义与本机资源、cookie/同源、人工字段、旧四类型API旅程|
|生产 JavaScript 语法|0|实际检查通过|新增惰性 template/Map 读取语法；未重跑原323项或39项目标|

目标测试通过真实 HTTP 获取页面和生产脚本，使用 Node 的小型 DOM 适配执行生产函数；这不是浏览器或视觉验收。实际辅助案件从原文绑定事实确认开始，选取 C05 标的交付、C08 期限顺序、C09 验收质保，保存对应编号的候选并由虚构律师逐条采纳，实际下载客户 DOCX；核对全部18个报告标签、3条对应候选句子及制品 hash。下载及观察分别保存为 `observations/selected-dimensions-client.docx` 和 `selected-dimensions.json`。法律质量仍 `NOT_EVALUATED`，本切片浏览器 `NOT_RUN`；根将用修后新服务单独检查，不把旧服务结果冒充修复后的通过。
