# 合同提示词评测 v2：离线诊断验收

日期：2026-10-26。基线 `be26d12fd993b20d096a5562809aad21ce096d03`。

**完成的是评测纠错与回归，不是生产合同智能体的模型效果升级。** 本轮没有 API 调用、费用、前端变更、模型开关变更或正式提示词替换；既有 AGENTS.md 修改保留。首轮试点已取得用户的 DeepSeek 20 元授权，本片不重置其预算或继续扣费。

## 已修复

新增 `acceptance.contract_scoring` 与离线重放脚本，沿用现有 OCR 评分器的工程字典报告形式，未新增业务 DTO 或审批通道。

1. 原判分用“引文集合完全相同”，把相关补引当失败。现在区分必需和可选证据：必需位置不可遗漏，相关补充位置允许；其他补引进入待核队列，不直接等同于错误。
2. 原评分对额外关系提前跳过，可能不再核其引文。现在无论是否属于预设关系，都核对位置、完整原文与重复项；额外观察另外复核。
3. 理由非空不再被当作质量通过。默认 `pending_manual_review`；人工反证绑定输入/输出内容摘要、具体字段、原话与源文，不能套用到别的结果。核对的是反证定位与绑定，不是自动语义裁判；所有报告固定禁止自动晋升、法律未核验。

## 已见输出重放

[原始虚构材料和输出快照](../../../../tests/fixtures/contract_scoring/pilot-v1.json)保存首轮16次样本审查（不含3次提案/组合调用）及原始分数。源记录只包含本聊天编写的虚构合同与模型输出，未导入密钥或请求头。

| 项目 | 实测 |
|---|---:|
| 重放输出 | 16 |
| 原严格评分通过（保留历史） | 12 |
| v2 引用/结构/必需关系检查通过 | 16 |
| 已记录的解释反证 | 1 |
| 理由仍待人工核对 | 15 |
| 额外观察待核队列 | 3 |
| 本轮新增模型请求/新盲测样本 | 0 / 0 |

这些数值属于同一批**已见答案的事后诊断**。从12到16是修正评测口径，不是模型能力提升。原基线与候选输出未改，原 gold 与原分数仍在首轮工作目录保留。

实际反证为 case-02 组合候选把“通知形式、起算方式”说成未明示；原文已写明“书面通知”和“收到涨价通知后10日内书面拒绝续约”。新报告可直接定位该说法与相反原文。其他未约定细节仍需单独判断，不能把本反证扩展成合同全面完备。

主代理另行逐一读取首轮工作目录的16份原始响应文件，核对每份 SHA-256 及解析后的 answer 与导入快照一致，结果全部通过；三份生产提示词 SHA-256 与首轮基线一致。独立审阅没有复核仓库外原文件，保真核验来源为主代理本轮命令。

## 命令与实际结果

- 新评分器27项先失败（模块尚未实现，exit 1），实现后27通过（exit 0）。
- 新评分器与真实已见输出/CLI测试共30项通过（exit 0）。
- 最终目标回归：`.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_contract_scoring.py tests/unit/test_contract_pilot_replay.py tests/unit/test_evaluation_cli.py tests/integration/test_review_flow.py tests/security/test_prompt_injection.py -q --tb=short --junitxml=docs/testing/contract-scoring-v2/20261026/targeted.xml`：**97 passed，38.12秒，exit 0**，见 [JUnit](targeted.xml)。97已包含30新增项，不能相加为127。
- `.venv/Scripts/python.exe -X utf8 scripts/contract_pilot_replay.py --output docs/testing/contract-scoring-v2/20261026/replay.json`：exit 0，[结果](replay.json)如上。输出采用排他创建，不覆盖已有报告；复跑请选新路径。
- `python -m cn_contract.cli schema --check`、`python scripts/verify_defaults.py`、`python scripts/verify_sources.py --mode development`、`python scripts/verify_runtime_dependencies.py --mode development`：均使用项目 `.venv`，均exit 0。来源门保留G01–G13尚未获生产批准提示；运行依赖门55包+1构建包、network_calls=0，native_build_verified=false。
- 独立静态审阅无 Critical/Important 遗留；独立重跑30项通过，119个输出字段变异安全失败、83个人工反证字段变异拒绝，重放与保存报告一致。首次探针误将未改变的false视为无效值，修正探针排除原值后完成119项；未改产品代码。

## 候选及下一步

[第二轮候选方法](../../../experiments/contract-scoring-v2/candidate-method.md)要求缺口报告前查找相反原文，区分材料未提供/合同未约定，计算值与原文值分列，补引须相关，避免重复义务观察。该文件在实验目录，未写入运行 prompts，也未获真实模型复测。

下一步用全新的成对样本覆盖“已明示/确实未明示”，再进行模型验证与解释核对；本轮旧holdout已见，不再称新盲测。没有运行全仓、桌面安装、法律验收或真实数据生产验收；其他聊天的恢复故障及升级状态不受本片影响。
