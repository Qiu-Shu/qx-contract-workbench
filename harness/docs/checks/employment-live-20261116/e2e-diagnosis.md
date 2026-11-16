# wage-supported 实际E2E根因诊断

2026-11-16。本次只读源码、实际评测保存的合成材料及工具轨迹，并在临时合成案件离线重放；未读取真实凭据、未调用模型、未改变在途或已保存评测、未修改产品实现。**三项服务端误拦截均已复现，尚未修复。** 本文诊断工程行为，不作法律正确性验收。

## 结论与层次

实际`wage-supported`停在10轮上限，直接原因是模型把剩余轮次用于重复保存和参数提取，未调用`read_case_note`或`export_case`。其持续待核的原因并非金额对象嵌套错误：首次工资项就传了四个正确形状的`{amount,citation}`对象。相同原始请求在离线实际MCP上仍失败，证实其后主要阻断在服务端来源记录识别。模型另外存在两个可独立定位的传参错误：首次保存的普通审查项缺`source`，以及一次引文结束位置少1字。

| 层次 | 实际证据 | 判断 |
| --- | --- | --- |
| 金额接口说明 | 捕获的工具description明确给出四个字段及`{amount:"原文金额含元/万元",citation:{path,quote,sha256,chunk}}`；首次调用已照此传入 | 不能把本次失败归因为未说明嵌套字段 |
| 普通finding传参 | 首次保存第3至5项缺`source`；程序工资项虽也省略，但由规则生成来源文字 | 模型漏必需字段，下一轮补全后保存成功；不是持续工资待核的原因 |
| 引文位置传参 | 第8轮工资句`start=57,end=101`，实际为`57..102`；另两条位置正确 | 引文校验正常拒绝错误范围；下一轮去掉错误offset后恢复保存 |
| 服务端来源归属 | 仅分别添加奖金缺失、正面月度尾句、同一行前导说明即可使完整工资行失去比较结果 | 三项独立误拦截，见下表 |
| 交付编排 | 10次工具调用中get_case 1次、read_case_material 1次、save 5次、assess 3次，回读/导出均0次 | 反复保存耗尽轮次；没有导出请求，不能称导出器执行失败 |

结构化JSON Schema的`findings.items`仍是`additionalProperties:true`的普通object，没有逐项typed properties/required；文字说明已经覆盖要求。这是可改善的接口校验边界，不能据此声称模型本次未收到金额用法说明。保存成功后的回读和指定`note_ids`导出也已经写在同一description中。

## 三项独立来源误拦截

最小控制行固定为原文四个金额，未改数：`合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。`。控制组可生成条件比较。

| 最小变化 | 实测结果 | 当前实现触发点 |
| --- | --- | --- |
| 另起一行加`奖金按员工手册支付，员工手册本次未提供。` | 工资比较消失；单独工资行提取本身仍有比较 | `employment_rule_review.py:39`把完整片段交给`parameter_context_warnings`；`employment_parameter_extraction.py:58`匹配奖金行的“未”，没有把否定范围绑定到奖金字段 |
| 工资句后加`上述四项均为税前月工资标准。` | 无全局否定/期间警告，但工资组报“字段之间或尾部存在未解析的主体、条件或数值” | `employment_parameter_extraction.py:37`的`_plain_gap`不识别该明确月度说明，`:109`把整行尾部作为未解析条件阻断 |
| 上一行写`独立虚构测试，均为同一员工同一工资期间的数据。劳动者：测试甲；合同编号：C-1` | 工资行本身可算，但全片段出现带符号数值警告 | `employment_parameter_linking.py:73`只对完整一行匹配身份头；前导说明使头未被识别，`employment_rule_review.py:31–39`因此未豁免合同编号，`C-1`被当作带符号数值 |

把前导说明独立换行，或只保留标准身份头，均恢复比较；`C-1`本身无需改成另一个编号。仅删除原样本奖金及月度尾句，仍被未识别身份头阻断；同时恢复标准身份头后通过。原完整样本同时具备三个阻断点，修其中一处不能证明正例恢复。

这里所称正例通过，限于产生原来源条件下的程序比较；来源身份、工资构成、适用地区和时期、法律评价及实际欠薪仍需另核。没有把条件算术当作事实或法律认定。

## 原始轨迹与离线重放

来源：[wage-supported.json](e2e/employment-live-01-thinking/wage-supported.json)。逐轮编号以下从1开始；JSON中的`round_zero_based`从0开始。

| 轮次 | 工具 | 重放一致的结果 |
| --- | --- | --- |
| 1 | get_case | 成功 |
| 2 | read_case_material | 完整读取1片段、138字；原始SHA-256一致 |
| 3 | save_employment_review | `source须提供文字`错误；工资参数四项均已有amount/citation |
| 4–6 | save_employment_review | 成功保存；每次工资`comparison=null`，均提示无法关联到同一可核算记录 |
| 7 | assess_employment_terms | 保存成功；期限可比较，工资月度尾句被判未解析条件 |
| 8 | assess_employment_terms | 引文范围错误，工资句end少1字，拒绝保存 |
| 9 | assess_employment_terms | 删除错误offset后保存成功；仍有工资尾句警告 |
| 10 | save_employment_review | 保存成功；工资仍待核，之后达到round-limit |

缩小citation.quote不能消除上述检查：来源绑定仍读取完整片段进行上下文核验，所以第5、6、10轮改变引文范围没有改变服务端判断。此行为避免通过只引用数值绕过限定条件；本次问题在于限定条件的作用范围和类型识别不足。

重放只重映射新案件`case_id`和新笔记`supersedes` UUID，保留所有原请求的其他参数；原材料字节SHA-256保持`234456b5eadf042cd75008f6fd1da479b129029363b32dd12dd28747b56aa460`。10次实际MCP调用的报错轮次与捕获结果完全一致。

重放后额外明确调用最后一份笔记的`read_case_note`及`export_case(note_ids=[id],audience="internal")`：成功产生40,332字节Word，回读完整、导出note_id正确、已保存待核原因出现在Word、材料字节未变。临时案件和Word随后清理。此检查证明这份待核稿可被导出，不声称Word与整段Markdown字节相同；没有实际模型参与新增的回读/导出。

## 建议修复位置，尚未实施

1. 在现有参数提取/记录关联层统一返回“工资记录范围、已识别主体、期间说明、限定条件及各自原文offset”，让`_same_wage_record`消费同一份结果。当前一处扫描全片段、一处按行检查尾文、一处仅认整行身份头，范围不同才造成三次互相独立的阻断。优先复用现有groups、linked_groups、source_spans；不先建通用自然语言引擎。
2. 对明确奖金资料缺失，只影响奖金事项；对有明确指代的四项税前月工资说明，保留为工资期间属性；合同编号符号只在已确认标签及原文span内豁免。仍需保留真实金额负号、非月度口径、否定/跨人/跨期限定和不明指代的阻断。不能把“其余所有句子”直接剔除，也不能全局放行连字符。
3. 工具结果可区分“已保存且本项待核”和“可通过补参数重试”，用稳定原因码及受影响span说明。重复缩短引文无法修复完整来源记录的识别问题，应允许模型按当前已保存待核稿完成回读、导出并明确局限。只增大10轮上限或调prompt不能修复服务端误拦截。
4. 接口边界可逐步明确普通finding的必需字段以及规则finding的参数类型，减少缺`source`重试；这是传参质量改进，与本次正确金额参数仍被拒绝的根因分开处理。

`wage-unlinked`的自由文字工资结论旁路由另一路审阅确认；主代理核对其实际stage为`dispute`且未显式传rule，因此未触发`hiring + pay_topic`保护。该问题不计入本脚本的9个变体，也不据此伪称本脚本覆盖其他语义改写。

## 可重复证据

脚本：[diagnose_e2e.py](diagnose_e2e.py)。只依赖现有业务测试环境，不读取模型密钥。输出：[e2e-diagnosis.json](e2e-diagnosis.json)。从仓库根目录运行，`$env:QX_TEST_PYTHON`应指向已有pytest/MCP/python-docx等业务依赖的Python；其余路径使用相对路径，换机时不需改脚本。

```powershell
. 'D:/CodexChecks/AI-Shixiong-employment-20261116/test-env.ps1'
& $env:QX_TEST_PYTHON 'harness/docs/checks/employment-live-20261116/diagnose_e2e.py' --root '.' --trace 'harness/docs/checks/employment-live-20261116/e2e/employment-live-01-thinking/wage-supported.json' --output 'harness/docs/checks/employment-live-20261116/e2e-diagnosis.json' --assert-supported
```

本机最终实际运行：10次原调用重放一致，额外回读/导出成功；9个最小变体中4个控制组有工资比较、5个受阻样本无工资比较；最后的原正例断言失败，**退出码1（保留RED）**。省略`--assert-supported`可只输出诊断而不对正例断言；该模式不是正例修复验收。没有把受阻案例计作通过，也没有用重放替代新的实际模型评测。
