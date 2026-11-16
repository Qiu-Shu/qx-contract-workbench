# 劳动合同 Skill 实际模型评测与根因诊断

**更新：** 用户随后要求“完成修复”。已复现程序缺陷已修复，47目标测试及两路独审通过；实际MCP重放确认保存、Word、聊天同稿。全文模型质量仍未通过，完整Skill继续候选。累计101请求、估算5.854282/10元。见[最新修复报告](repair.md)。以下保留修复前诊断、费用及验证历史，不能将其“尚未实施”当作当前状态；`diagnose_e2e.py --assert-supported` 的原完整正例现已通过，未写周期的对照则应待核。

用户2026-11-16授权本批真实模型总额10元，并取消律师复核前置。全部材料独立虚构，沿用 DeepSeek Flash（思考high），未更换产品主模型。**完整劳动 Skill 内容质量未通过，仍为候选。** [根因报告](root-cause.md)列明已复现原因与未修事项。安装版仍0.2.19，本轮没有构建或安装新版本。

## 实际结果

| 实测 | 数量与结果 | 原始证据 |
| --- | --- | --- |
| 首轮完整审查 | 候选1/8通过；无专项对照1/5通过 | [独审](spec-review.md)，`model/retest1` |
| 修正方法后完整审查 | 候选2/10通过（E、I）；未按重复抽样刷通过 | [输入](retest2-inputs.json)、[独审](spec-review-retest2.md)，`model/retest2` |
| 真实模型→真实MCP | 2例；supported10轮耗尽，保存但未导出；unlinked7轮完成功能链，但Word/聊天仍有错误月工资表述 | [场景](e2e-cases.json)、[独审](e2e-review.md)，`e2e/employment-live-01-thinking` |
| 事实提取诊断 | G/H/C各预定2次，共6次；年薪与考勤核心状态有所保持，但仍有口头媒介、拟改字段、未签署等错误，不计完整审查通过 | [输入](diagnostic-inputs.json)，`model/retest3` |
| 离线根因重放 | 原10次工具调用、9个工资变体及3个保存探针；正例解析仍失败，错误事实可原样保存 | [E2E诊断](e2e-diagnosis.md)、[保存探针](saved-claim-diagnosis.json) |

## 冻结与评分

首次调用前固定 [输入摘要](frozen-inputs.json) 和 [场景](../../../evals/candidates/qx-employment-review/live-scenarios.json)。A—E继承上轮原场景；F检验正常录用条款修改，G检验前句年薪限定，H检验解除前相反证据及可用通知草稿。对照只替换专项指引，不改变系统、问题或模型设置。所有原答保留，修复或复测另存新phase，共享预算。

每例先逐项检查场景expected，再看：材料与执行范围准确、已知事实保留、法律条件不武断、提出可用意见/候选条款。任何事实/来源/工具执行捏造、错误合并工资、无依据最终补偿或竞业解除结论为关键失败。不给出材料支持的业务结果、只作全面拒绝也不通过。13份响应收齐不等于内容通过；不将小样本通过率称统计质量保证。律师未复核据实记录。

指令评测不提供业务工具；E2E另提供真实工具。两者分开记录。原方法及系统指令按phase保存，修复未覆盖首轮输入。supported的`completeNoteReadback=true`来自收尾检查器回读，不能称模型完成回读；模型未调用read_case_note或export_case。

## 运行与预算

在harness内，以已保存凭据通过既有Electron安全存储读取；密钥不进入输出。设置 `QX_REAL_MODEL_TEST=1`、`QX_SKILL_EVAL_CAMPAIGN=employment-live-20261116` 与已安装开发Electron路径，运行 `node scripts/test-suite.cjs quality retest1 evals/candidates/qx-employment-review/live-scenarios.json`。只提交合成原答和费用元数据。预算脚本先RED（1失败/4通过）后GREEN（连同统一入口9通过），退出码分别1、0。

## 费用与最终回归

[台账](budget.json)：**46次请求，保守估算2.527518元，未知或在途0次，上限10元**。46=首轮13+第二轮10+E2E17轮+诊断6。不是账户实际扣费账单。2026-11-16核对[官方费率](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)为高峰输入2元/百万tokens、输出8元/百万tokens，忽略缓存与非高峰优惠；另留0.5元保护余量，未知不退预留。继续本批先读原账本，累计不得超10元。

新活动固定日期、10元及授权Skill，使用共享锁和live显式开关。合成E2E工作目录在`.local/employment-live-20261116/e2e`。独审发现凭据回调吞前置异常导致退出0，已修复错误传播与状态检查。[永久回归](../../../scripts/evaluate-practice-preflight.test.cjs)先2失败，最终相关17通过；中途测试环境映射的路径断言失败也保留，不冒充一次通过。[Standards独审](standards-review.md)确认关闭该项。

最终 `node scripts/test-suite.cjs offline`：**Node723通过/23跳过，Python564通过/5跳过及36子测试，总退出0**。[统计与日志摘要](verification.json)。本机原始日志：`D:/CodexChecks/AI-Shixiong-employment-20261116/live-offline-final.log`。Windows打包/安装本轮未重跑。产品工资解析、金额保护阶段遗漏、自由文字语义问题仍未修复，不能以工程回归通过关闭。

新目录MCP测试先1失败1通过、实现后2通过；独立重复测试不累加为额外覆盖数量。

## 换机复现与模板

工作树 `F:/.codex/worktrees/employment-review/律所项目`，分支 `codex/employment-review`。换机在harness准备锁定Node/Python依赖，`PYTHONPATH`包含bridge和legacy/src。离线运行 `python docs/checks/employment-live-20261116/diagnose_saved_claims.py` 输出实际保存缺口；退出0不表示语义通过。

`diagnose_e2e.py --root <仓库绝对路径> --trace <wage-supported.json> --output <新的输出.json> --assert-supported` 当前应退出1，保留正常工资误拦截的失败断言，不要改断言来关闭问题。真实模型另需显式live开关、campaign、新phase/run和开发Electron/测试Python路径，不能覆盖旧输入或自动重发未知请求。

[官方模板说明](../../templates/official-20261116/README.md)：103原始下载对象，ZIP内20文件另展开；含模板、实例、指南和法规，不是103份空白文书。71DOCX可解析、27旧DOC只验签名，最高法院975页PDF可提取且有226目录；2独立扫描PDF未OCR；6未取得项如实记录，未绕过限制，自检12项通过。

本机便携包 `D:/CodexChecks/AI-Shixiong-templates-20261116/官方常用法律文书模板-20261116.zip`，17,691,758字节，SHA256 `6a0307b71d3c5c61fbfa397509d43c8de117c54ba76feffe410210a7e762ee6f`。仓库仅索引、摘要和采集脚本，未公开上传整套原件。[最新交接](../../2026-11-16-劳动Skill实测交接.md)替代历史等待预算/真实模型/律师前置的描述；其他专项与36停用入口未恢复。
