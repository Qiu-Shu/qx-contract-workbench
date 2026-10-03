# T06 独立审阅：受控虚构材料闭环

日期：2026-10-03；workspace `D:\Documents\ChatGPT\律所项目`；分支 `codex/contract-review-v2`；冻结基线 `8ffa6b1f556666614057e8cd1490e2b7c88cf3c6`。独立代理只修改本记录和被忽略的 `.audit-local/t06-review/`，未修改业务源码/正式测试/依赖/锁/任务状态，未提交、联网或访问私人 Vault。父节点统一处理 Obsidian、完整套件和四份独立 CLI 演示。

结论：冻结实现的官方目标 80 passed、独立攻击 77 passed、必要受影响回归 42+22 passed，全部退出 0；无未闭合 P1/P2。仅支持 T06 离线 mock 工程集成，父节点最终全套、四份演示、配置/schema/来源门及提交仍应按实际证据另记。法律样本验收、真实试点和生产继续阻断。

## 审阅范围与实际优点

读取 AGENTS、TASK_STATUS、v2.0 §5–8/T06、细化计划及实际 T02–T05 接口。T06 服务重新核验真实 session/roles/member 和服务器当前案件/文件/事实/规则/政策，对完整 ParseResult 复用 T04 从不可变原件重算；独立伪 quote、anchors、parts、unsupported、quality 五类攻击均拒绝。

规则选择使用完整存储快照，模型输入只含实际 applied 规则；独立真实批准 logic rule 与十四份 draft 共存时，所有实际 request 仅包含已选规则，x-input 与服务器精确 parse 一致，manifest 绑定完整规则依赖和 policy_runtime_sha256。真实 provider 或可携带工具的 subclass 未获执行。

严格 raw JSON 与受限操作保存实际输入 hash、usage、输出 hash/ref。保护读取和 SQL 不可变门覆盖 run、尝试及预确认/结束拒绝技术记录。67 个精确锚点的末块、相同 quote 不同位置、跨块保密与训练关系保留；18 维不足/未支持不冒充 reviewed_no_issue。伪 manifest/anchor/法源/任意法律分析/人决定/缺证据均校验失败。

## 实证问题与关闭

|组|实际问题/影响|修复与独立关闭证据|
|---|---|---|
|P2 深度 JSON|json.loads 的 catch 未覆盖 finite 递归；深层真实 raw 抛 RecursionError，服务失败 usage 丢失|改显式栈与64层上限；deep-fixed.xml 23 passed，含服务原始+修复两次 usage/hash/ref；最终77再次覆盖|
|P2 风险去重|67锚点首/末两处相同保证生成2条 finding，违反合并保全部来源要求|按受控语义 key 合并，1条 finding 含两个准确位置；最终77覆盖|
|P2 实际调用记录|成功 intake、失败 intake+repair 和结束当前性拒绝均丢失所有已执行尝试；intake-initial.xml 3 failed/0 errors|新增不可变 operation records，原始输出只受保护读取；caller catch+commit保全部实际usage，不制造current run。独立67、额外3项权限/SQL/hash/ref及最终77覆盖|
|P2 客户限制|真实 objectives 明示无谈判空间仍建议协商修改；business-initial.xml 1 failed|读取服务器目标与实际立场，建议接受/拒绝风险及履行证据，由律师决定；business-fixed.xml覆盖及最终77|
|P2 义务方向|供应商不续约被认成客户义务、客户调价被认成供应商义务，同段第二通知被elif漏掉；direction-initial.xml 3 failed/0 errors|仅原文明示窄主体才定方向，否则待确认；逐事项保留。business-fixed.xml 4 passed及最终77|
|P2 Decimal|已确认100+1e-90被80位精度舍入为100；全局Inexact trap使服务崩溃；decimal-initial.xml 2 failed/0 errors|复用T04有界AST/已确认事实/单位/独立Decimal Context，采用精确输入指数步长；超限明确数学不足。decimal-bound-fixed.xml 3 passed，含1e-300不足/C06+C18不足/usage，最终77及22项计算回归|

预读时另发现候选编号 str+int 明确异常并通知作者；作者自行实跑修正，未将其冒记为本代理功能 RED。作者另外补实证让三份原创 prompt 真正进入 request 并核当前 hash；最终官方80包含该行为。

## 最终实际命令

所有命令使用 `.venv/Scripts/python.exe -X utf8`；JUnit 与源码封存均在 `.audit-local/t06-review/`。

|命令|退出码|实际结果|
|---|---:|---|
|`-m pytest tests/unit/test_model_schema.py tests/integration/test_review_flow.py tests/security/test_prompt_injection.py -q --tb=line --junitxml=.audit-local/t06-review/final-target.xml`|0|80 passed，0 warnings，32.07s|
|`-m pytest .audit-local/t06-review/test_raw_layer.py .audit-local/t06-review/test_independent_review.py .audit-local/t06-review/test_service_edges.py .audit-local/t06-review/test_intake_accounting.py .audit-local/t06-review/test_policy_and_records.py .audit-local/t06-review/test_business_constraints.py .audit-local/t06-review/test_decimal_review.py -q --tb=line --junitxml=.audit-local/t06-review/final-independent.xml`|0|77 passed，0 warnings，26.80s|
|`-m pytest tests/security/test_auth.py tests/unit/test_versions.py tests/unit/test_state.py tests/unit/test_cli.py -q --tb=line --junitxml=.audit-local/t06-review/final-affected.xml`|0|42 passed，1既有Starlette/httpx弃用警告，10.15s；未隐藏|
|`-m pytest tests/unit/test_calculate.py -q --tb=line --junitxml=.audit-local/t06-review/final-math-affected.xml`|0|22 passed，0 warnings，1.19s|
|父作者23个冻结文件实际SHA256/bytes重算比较|0|23/23匹配，mismatches=[]|
|`.audit-local/t06-review/seal.py`|0|29源码/运行数据/依赖文件及4最终JUnit封存；seal SHA256 `6688674042a2659bda64bc2bfd3b2f16532df0b7c2a7b6641efdc865c5d9d7d6`|

`final-seal.json` 保存每个实际文件 SHA256、UTC封存时间、基线、结果XML hash与suite数量，以及七个独立probe脚本的hash。正式目标内既有单份CLI测试照常执行；本代理没有另跑四份CLI或完整套件。

## 辅助错误与分母

首次 raw 隔离命令在作者尚未创建 workflow 时出现1 collection error、0 executed，不计功能RED/PASS。第一次独立组合输出36 passed/4 failed/2 errors：3失败是真实深度缺陷；1是本代理误以完整法律请求必抛异常（实际failed/RULE_UNAPPROVED合法，已修正预期）；2是超长pytest参数ID触发Windows环境长度限制，已改短IDs。初次service输出19 passed/4 failed/1 warning：2是真实深度/去重缺陷，2是本代理HumanDecision字段错误及单字符raw与普通JSON日志比较失当，均修正；warning为probe以string替enum，已改正确enum。最终受影响命令首次误写 `test_calculations.py`，退出1/0 tests；随后以上四文件42项和真实 `test_calculate.py`22项实际执行。辅助错误均不是业务RED，不隐藏为通过；完整历史位于PLAN.md及各轮XML。

## 未评判与限制

- 真实模型/供应商账单耐久性、QCC账户/许可/价格、现实法源/法律规则批准和正式签发：当前明确关闭或后续T07–T13，不因工程审阅放行。
- 独立模拟期间的server变更探针通过测试 instrumentation 改变真实服务器状态，provider自身没有任意callable hooks或工具。旧session持久撤销后结束拒绝保三次usage，原session读取raw仍被拒。
- operation记录加入调用者事务，外层rollback仍会回滚；这是有限mock事务模型，不是现实付费请求的账单保证。失败写保存点由caller捕获再commit时，无半写run、attempt或review audit，案件仍ready_for_review。
- 没有律师金标准、OCR/全面视觉等价、Word正式制品/修订、T10 UI或生产运行验收。原件和源笔记保持不覆盖。
