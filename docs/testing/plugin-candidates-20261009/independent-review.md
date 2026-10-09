# 插件候选提交独立审阅（2026-10-09）

范围：HEAD b8da6d7之上的候选提交功能未提交变更；不改产品代码、不使用真实合同、不占用8767/18768。按本项目AGENTS与Ponytail读取计划，通过CodeGraph检查调用结构及实际源码。源绑定刷新与真实HTTP/STDIO/浏览器由主实施负责。

## 两项可复现Important / P2（初审）

1. `CaseBridge.read`（原174–177、198–200行）：首次候选POST成功201后，正常读取context以ready-only上下文校验遇到awaiting_lawyer，返回409 STATE_CONFLICT并close当前grant；随后完全相同输入重放401。这让一次只读调用意外撤销未过期未撤权的有效提交授权，破坏同输入返回原收据的承诺。建议复用提交后allow_finished重验路径，保留当前来源、版本、授权核对。
2. `CaseBridge.read`来源字段和limitations（原187–190行）及`AssistedReviewContextView`：已允许插件候选的读取响应仍声称manual_synthetic、真实模型推理NOT_RUN/真实模型调用0。插件来源未核验，不应将上下文或未来/已提交插件候选标为人工，也不能认证聊天模型未调用。建议插件桥单独投影来源未核验及工作台本身0调用，普通人工入口和历史快照保持兼容。

两项由独立探针有效RED确认，修复由主实施处理；下文以最终复验补记为准。

## 实际执行记录

- 初始运行：`.venv/Scripts/python.exe -m pytest .audit-local/plugin-candidates-review-20261009/test_review_probes.py -q --junitxml=.audit-local/plugin-candidates-review-20261009/initial.xml`，exit1，5个测试：2产品失败、2审阅探针设置错误、1通过。探针错误为ServiceError字段名及重新打开数据库需显式初始化；不列为产品缺陷。
- 修正探针后的有效RED：同命令改输出`corrected-probes.xml`，exit1，5个测试：2 failed、3 passed，19.42s。通过commit失败无幽灵收据且后续可提交、校验和写入间撤销阻止落库、重开同一数据库后候选收据保留而旧grant拒绝。
- 兼容与原生导出：`.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/plugin-candidates-review-20261009/test_review_probes.py::test_lawyer_disposition_preserves_replay_and_native_redline_is_not_manual_claim tests/integration/test_assisted_review.py::test_new_fiction_complete_manual_candidate_lawyer_draft_journey -q --junitxml=.audit-local/plugin-candidates-review-20261009/exports-manual.xml`，exit0，13 passed，192.74s。包含12个历史人工路径完整旅程与1个插件候选→律师处置→重放→原生红线批准/实际下载。

原生红线页眉页脚使用通用DRAFT MOCK/非正式法律意见标识，实际下载没有manual_synthetic、人工/合成、NOT_RUN或推理未运行断言，因此没有按人工来源误标提出问题。

未独立执行完整回归、实际网络MCP、浏览器、原生Word视觉或真实法律质量验收；不据本审阅声称生产完成。

## 针对修复的独立复验

主实施修复allow_finished读取与来源投影后，独立原6探针复跑：`.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/plugin-candidates-review-20261009/test_review_probes.py -q --junitxml=.audit-local/plugin-candidates-review-20261009/final-probes.xml`，exit0，6 passed，35.83s。该文件名仅为当时六项复验，不代表后续并发问题已闭合。

继续仅针对allow_finished修复检查，发现同一P2的两个并发残余，并新增两项确定性交错探针：

- `test_read_during_submit_does_not_use_precommit_finished_flag`：正在提交且commit前启动读取，read在取得SQLite事务前已读到submission=None；提交成功后仍使用allow_finished=False，409并撤grant。独跑exit1，1 failed，4.98s，`concurrent-read-red.xml`。
- `test_identical_replay_waits_for_postcommit_receipt_publication`：首次commit已完成但receipt缓存尚未发布时启动相同提交，后者取得SQLite事务却读到previous=None，错误409。独跑exit1，1 failed，5.04s，`publication-race-red.xml`。

建议read和submit都先取得SQLite事务，再短持既有锁核对当前active并读取submission，以同步commit后缓存发布；不能在持锁时等待SQLite。产品代码由主实施修复。当前等待8探针最终复验，未重跑大套件。

## 最终结论

主实施已将read/submit两入口调整为先取得SQLite事务，再短持锁核对active并读取submission；commit和receipt缓存发布保持在同一锁内。独立检查修改后，执行：

`.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/plugin-candidates-review-20261009/test_review_probes.py -q --junitxml=.audit-local/plugin-candidates-review-20261009/final-eight-probes.xml`

实际结果：exit0，**8 passed，45.52s**。两项P2（包括同输入重放相关两个并发残余）均已关闭，当前审阅范围未发现未解决的Important/Critical问题。该结论只覆盖所审变更及上述实际测试；父会话的HTTP/STDIO/浏览器、源绑定和更大范围回归不计入本独立分母。原13项人工兼容/原生下载通过记录仍保留，未重复大套件。产品代码始终由主实施修改，独立审阅仅增加本地审计探针和报告。
