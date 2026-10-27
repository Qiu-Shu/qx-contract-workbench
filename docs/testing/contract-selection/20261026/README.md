# 2026-10-26 合同选优实际验证

最终选择：实验排名C4；正式审查保留既有基线，未晋升。完整报告见 docs/experiments/contract-selection-20261026/selection-report.md；用户交付位于原C工作区outputs/contract-selection-report.md。

## 实际命令与结果

- 在原outputs目录：python -X utf8 -m unittest test_contract_pilot test_configure_deepseek test_contract_selection test_selection_transport test_contract_selection_validation test_selection_validation_transport -q；42 tests，30.626s，exit0。
- 在本项目：.venv/Scripts/python.exe -m pytest tests/unit/test_contract_scoring.py tests/unit/test_contract_pilot_replay.py -q；30 passed，2.39s，exit0。
- python -X utf8 verify_contract_selection.py；64响应/请求/用量/评分/冻结/历史源重算PASS，exit0。首次验证脚本glob误包含frozen-refinement，修正后通过；未修改实测结果。
- python -X utf8 verify_contract_validation.py；再8响应/请求/评分/全部旧保护额核验PASS，exit0。
- 新测试先验证等价证据评分失败、成功JSON正文篡改未阻断等真实缺陷，再修复；冻结后不修改已运行调用/评分代码。新阶段使用另立冻结，保留旧结果。
- 独审：第一组32匿名回答96checks；第二组8匿名回答48checks；预算/请求/封印另独立复算。来源文件、SHA和逐项意见均在outputs对应报告。

## 有限结论

72新增真实调用，全用虚构材料；首轮候选经开发后用8场景重复两轮；后续C4只在4新场景单轮测试。C3/C4后组均23/24标签、22/24完整证据；C3有1schema失败、C4无；两版各有一处明确结论/理由冲突。C4不是生产替代批准。

累计成功用量高峰估价0.481598元（含前19次），未知1元保留，账本保护19.103326/20元。全仓/浏览器/安装包/真实客户材料/法律验收NOT_RUN。现有3正式prompt SHA与原快照一致，用户AGENTS改动及其他聊天工作保留。
