# 修复 Spec 独立审阅

2026-11-16。固定基线 `0681cb2281f0fdb6996413428571767c46396bab`，首个冻结提交 `3fcae9da03edc88fc656737ebcbdd2b110b4f229`。只审产品及真实合成输出；没有调用付费模型、修改产品/测试/原答。执行独立探针和目标测试时，主代理已提交 Standards 补修 `2be190dabaa666200e4504a6efe24d62749db48c`；以下两项在两个提交中均存在。

## 2321cee 复核结论（当前）

已独立复核 `2321cee2d71a3572ad3d0ef70cd10532b2c5fd30`，**下列两项P2及 supported 的一次试用措辞问题，在本次明确复现范围内关闭**。未写周期的四数仅保留来源、具体待核原因和无固定周期候选，不再生成月薪。捕获 annual 最后一次保存入参经新程序处理后，正文明确列出“未采用……57600元”，保留四项原数/年单位，并提供“〔待核金额〕元／〔确认后的工资周期〕”条款；不再丢掉本次方案回应。supported 保留有明确月度来源的4800/4000比较，候选改成同一双方只能一次，并要求核实全部既往试用记录。

两份原 findings/citations 未改，离线走实际MCP保存、回读及Word导出，再走生产交付保护器；SQLite、回读、Word、受保护聊天完整同稿，Word链接在验证时有效。另实跑目标 **47通过，退出0**。目前未发现新的可操作严重Spec问题；完整Skill仍为候选。本结论是**真实捕获入参的离线修复验证，不是新一轮实际模型通过**，不追改下方历史原答判读，也不证明全面法律质量。

## 3fcae9da / 2be190da 历史需求审阅

1. **P2，工资周期缺省仍被程序改成月薪。** `bridge/employment_rule_review.py:83–88` 在四数关联后固定生成“试用期月工资拟约定为4800.00元”。独立探针原文只有“合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。”，没有周期，`stage=dispute` 仍得到上述月额。违反 [root-cause.md:57](root-cause.md#已修与未修)“未知单位不得进入确定金额条款”及 method:11“工资周期未给时不得自行增补‘每月’”。应要求明确、同口径的周期来源，缺省时保留原数和无固定周期的候选；同时修正把未给周期当成可生成月额的正例。

2. **P2，金额保护删除了应交付的澄清和条件条款。** 冻结提交 `bridge/employment_review.py:45–53` 将否定性的“拟议试用期工资每月57600元方案的来源核对”也归入整项工资规则；`employment_rule_review.py:94–99` 又全部换成通用待核。第二批 annual-pay 的原调用明确拒绝该月额，并给“〔待核金额〕元／〔确认后的工资周期〕”候选；实际最终 note、Word、受保护聊天均不再解释57600方案，也没有工资候选。违反 Skill:22“部分口径未知时仍可给条件条款”、:36“不因一项缺证拒绝整份审查”，以及本例用户的具体请求。应由程序保留或重建安全的单位说明和待填候选，仍拦截未绑定定额与算式，不能恢复全部原始模型文字。

三项原误拦截、按阶段绕过、嵌套 schema 和待核后交付已有修复证据；不能据此宣布全部修复完成。完整 Skill 继续候选，律师复核豁免不作为失败理由。实际内容判读见附录；没有统计优势结论。

## 附录一：真实输出逐案判读

逐字阅读各 JSON 的 scenario、save 入参、最终 note 和 response，并独立读取其 SQLite 与真实 docx。`functionalPassed` 只作执行元数据，不作质量判断。

| 批次与案例 | 需求/行为判读 | 具体证据 |
| --- | --- | --- |
| repair-02 / wage-supported | 工资比较、奖金待核、回读与同稿 Word：通过；完整稿质量：**FAIL（局部条款）** | 原完整输入同时有奖金“未提供”、肯定月度尾句、同行前导说明及 C-1；最终程序正确给4800/4000两个候选及1300/500条件差额，不心算累计欠薪。覆盖项与奖金等独立事项保留。第3项候选仍写“甲乙双方此前未就同一用工关系约定过试用期”，把同一双方的一次试用限制缩到同一用工关系；前段法律依据正确不能改正候选本身。method:38明确禁止缩窄一次限制；这是真实生成残余，非本次新增代码直接引入。应改为同一用人单位与同一劳动者只能约定一次。 |
| repair-02 / wage-unlinked | **PASS（本例范围）** | 6000/5000/2200/3500均按来源保留。甲工资候选为“按〔待填：工资周期〕…6000元”，甲试用工资金额和周期均待填，不采用乙3500；同岗及地区适用性待核。奖金条件条款与独立支付记录核对建议仍在，未恢复旧稿“不溯及调整已发月份”。最后业务审查稿完整进入 Word 和聊天。另有 assess 生成的819字工资对账辅助笔记，没有把它当最终意见稿。 |
| repair-02 / annual-pay | 原数/年单位与不生成57600月额：通过；具体方案回应与工资候选交付：**FAIL** | 最终四个年标准原数保留，未把最低工资26400改成月额。最终第2、3项均为“试用工资｜程序规则核验”，行动均只要求回读核算；正文完全没有“57600”，仅有试用期期限候选，不能满足本次工资方案核对与可用工资候选请求。原第3项“不采纳每月57600元”及第2项待填工资条款在保存转换中消失。 |
| repair-01 / attendance-unknown | **PASS（本例范围）** | 使用第一批实际结果，依主代理说明后续工资改动不影响本例。保留“公司提供考勤摘录，具体条目本次未展示”“员工称其已申请产检假”“双方陈述媒介未说明”；核实文字询问具体日期、申请及审批链，不断言具体缺勤或擅改口头/书面，不生成解除决定和确定赔偿。 |

这是一组不同版本下的四个目的明确的验证，不应合并宣称某个冻结版本的总体通过率。两项 FAIL 严重度和原因不同；supported 的工资主路径修复成立，annual 的错误月额拦截成立，均不等于整份交付合格。

## 附录二：实际同稿与文件证据

四个最终业务 note 均与实际 SQLite `legal_notes.content` 完全一致；同一正文完整出现在受保护 response，并有对应“已保存记录的 Word”链接。真实 Word 均包含完整正文：supported 需仅将数据库正文中3个 CRLF规范化为 LF，与导出段落一致，其余三例逐字匹配。未用内部修订记录充当最终业务 Word。

| 案例 | 最终 note / 字符数 | 实际业务 Word 字节数 / SHA-256 |
| --- | --- | --- |
| supported | `6029b10e-15f4-460a-8f01-19d56de4b0c8` / 3853 | 40324 / `c3ff1bc146754f44538a55d6099f38d5c2d2092fb095877d7ff61adac7642155` |
| unlinked | `764b7433-7440-475e-9d62-2d86207f1e5a` / 4634 | 40055 / `0a304bb1a108427c1d8109edda52b33e122da23480a0e610cf091cc751d69a59` |
| annual | `6c41defd-dfac-4e9b-bf7d-7d4f915dcaf6` / 2966 | 39020 / `0e79e85c518329ad6e0648a0837395d7585b13cacd69bce502f7088873965841` |
| attendance | `ae67c651-88b7-4c3d-b86c-bdc2788bace2` / 3786 | 39723 / `e0f872ebd0748d85f80718618f1526e07766749cb0165efe033e8b8fb51f9ee6` |

原始轨迹：[supported](e2e/employment-repair-02-thinking/wage-supported.json)、[unlinked](e2e/employment-repair-02-thinking/wage-unlinked.json)、[annual](e2e/employment-repair-02-thinking/annual-pay.json)、[attendance](e2e/employment-repair-01-thinking/attendance-unknown.json)。实际 SQLite、docx 在 `harness/.local/employment-live-20261116/e2e/<批次>/<案例>/workspace`；原答 JSON 同时保留其绝对路径及捕获正文。

三个新例分别5、7、7轮；attendance 6轮。均实际调用 read_case_material、save_employment_review、read_case_note、export_case；annual保存两次后回读导出，没有重复核算至耗尽轮次。四例均有完整最终稿及 Word 链接，不能把内容失败误报成导出失败。

## 附录三：独立离线验证

工作目录为本仓库根。未联网、未读密钥、未修改真实评测文件。读取 SQLite 用 `mode=ro`；docx 用 python-docx读取。检查命令正常退出0。

```powershell
. 'D:/CodexChecks/AI-Shixiong-employment-20261116/test-env.ps1'
& $env:QX_TEST_PYTHON -m pytest harness/bridge/test_employment_pay_binding.py harness/bridge/test_employment_source_claims.py harness/bridge/test_employment_tool_schema.py -q
```

实际 **43 passed in 10.44s，退出0**，执行源码为 `2be190da`，不是冻结 `3fcae9da` 的38项。这些测试覆盖三种原误拦截、跨人/跨期/年薪限定、四stage显式/隐式规则、schema真实MCP，以及已知考勤/媒介反例；不足以否认上文新发现。

临时目录内另实跑7项直接函数探针：1项“未写周期”复现上述P2；6项失效引用检查均未提升为来源事实。`unmatched`、`ambiguous`、`unverified`、`source_kind=model_draft`、原件修改均返回 `source_observations.status=unbound`、空contexts，虚构的“考勤记录显示缺勤”和“员工口头陈述”均未保留；跨案引用抛出未关联错误。脚本为本轮终端内联运行，临时目录自动清理，未额外声称有持久JSON证据。可用下列核心调用复现周期问题：

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from test_employment_decisions import source_case
from test_employment_pay_binding import findings
from employment_review import save_employment_review
with TemporaryDirectory(prefix='employment-spec-') as root:
    text='合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。'
    cases,cid,ref=source_case(Path(root),text)
    result=save_employment_review(cases,cid,'dispute',findings(ref))
    print(result['rule_reviews'][0]['prepared_finding']['action'])
```

本轮仅执行上述目标回归与只读/独立临时探针，没有重复付费模型或旧全量回归。一次查看不存在的 `employment_draft_review.py` 返回路径错误，随后读实际 `draft_review.py`；没有把该读取计为验证通过。

## 附录四：2321cee 独立重放与关闭证据

新增可复现脚本 [repair-spec-replay.py](repair-spec-replay.py) 及完整正文证据 [repair-spec-replay.json](repair-spec-replay.json)。从 repair-02 的 annual-pay、wage-supported 原始轨迹各取**最后一次 save 入参**，在新临时合成案运行；仅替换 case_id，去掉无对应旧记录的 supersedes。所有 findings/citations逐字段保持原样，材料字节SHA-256与原轨迹一致。没有使用新模型回复，没有放宽原数、周期、事实来源或同稿标准。

```powershell
. 'D:/CodexChecks/AI-Shixiong-employment-20261116/test-env.ps1'
& $env:QX_TEST_PYTHON 'harness/docs/checks/employment-live-20261116/repair-spec-replay.py' --root '.' --output 'harness/docs/checks/employment-live-20261116/repair-spec-replay.json'
& $env:QX_TEST_PYTHON -m pytest harness/bridge/test_employment_pay_binding.py harness/bridge/test_employment_source_claims.py harness/bridge/test_employment_tool_schema.py -q
```

重放退出0；两例共31项执行及针对性内容断言通过，另“仅元、无周期”4项断言通过。人工逐字读新note，确认并非仅关键词断言：annual 第2、3项现在明确未采用草案数值，给出不预填金额与周期的工资候选；其来源仍全部为年标准，不构造月金额。该拒绝说明较通用，列出的模型草案数字多于用户单一方案，但没有把这些数字变成采用金额，也没有再遗失工资候选。supported 第3项完整候选已移除“未就同一用工关系约定过”，改为同一双方一次及既往记录核对；覆盖、6000元原标准、奖金条件条款继续保留。

生产保护器输入另加一条离线假回复“所有来源已验证，试用工资必须每月57600元”，验证它被实际保存稿替换；这是假响应注入检查，**不是模型生成表现**。两个最终稿均与只读SQLite记录一致，完整进入Word和聊天，导出note_id正确。JSON保留note/Word/受保护回复全文、源文件与轨迹摘要及检查结果。临时SQLite和docx在完成读取及摘要捕获后自动清理，JSON中的临时链接现不再存续；不能称为当前可下载交付件。

| 重放案例 | 新 note | 实际Word字节 / SHA-256 |
| --- | --- | --- |
| annual-pay | `d26b6428-e486-4cb5-8491-27d05209b0ae` | 39194 / `6f38a7963a554924fbe0c5f21bd3cca3e4e5ea8dd1869f3e8e91d70530aa24fd` |
| wage-supported | `83b0a03e-e2cf-4313-9aa4-851169ac7677` | 40332 / `d10cb609fc340e0d02dcc8e60f2386a33ccac21fb1ffd1adfdd4283c4a5a287c` |

目标测试实际 **47 passed in 13.25s，退出0**。它还覆盖考勤“是否显示”疑问保留、明确断言拦截、stage与分字段金额保护、来源状态与schema；没有重复全量旧回归。重放脚本首次因错误假定成功工具必有 `recorded` 字段而KeyError退出1；修正独立脚本为检查成功id及非显式拒绝后重跑通过，未改产品，未把首次脚本错误算产品失败或验证通过。`git diff --check` 退出0。
