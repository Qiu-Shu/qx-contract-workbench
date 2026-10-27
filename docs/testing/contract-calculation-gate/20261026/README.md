# 合同候选计算与证据校验：实际验收

2026-10-26。沿既有 C4 实验候选继续处理实测问题。本片新增的是独立离线评测模块，没有接入正式审查或已安装桌面版，不证明生产入口原来存在同样缺陷。没有新模型请求、真实合同上传、前端改动或生产晋升。

## 已实现

- `acceptance.contract_calculation_gate.check_calculations` 复用既有 `facts.calculate.calculate_expression`、SafeExpression、CalculationInput 和 RoundingSpec。金额使用 Decimal；不执行文本公式，不新增业务 DTO。
- 原文、完整断言、数值片段、单位、人工解释及公式绑定到案例 SHA；严格限定字段、节点数、深度、数值大小。模型答案结构不符、引用不符、计算标签不符或必需证据缺失均触发复核。有限中间计算精度不自动放行。
- 不更改原答案；输出案例、计划和答案摘要。未覆盖内容保留 `not_covered`，理由文字仍为 `pending_manual_review`；所有报告 `promotion_allowed=false`。
- 新离线 CLI 使用固定合成快照 SHA，输出采用排他创建。既有选优封印、评分、账本和三个正式提示词没有被修改。

## 计划的可信边界

独立整理者只读合成案例原文和现有计算器，未读模型答案、gold、候选提示词或密钥，整理 4 案例、8 独立断言、9 比较。根代理另核对计划。计划仍是人工可信输入：片段存在不能证明其中文数值转换、公式含义或法律解释自动正确。模型不能自备计划进入可信通道；目前也没有自动提取计划的实现。见 [整理记录](../../../experiments/contract-calculation-gate/curation.md)。

所有计划的 fact_ids 为空，计算器保留未绑定全部已确认事实的限制。不能将这个工程回放当成已确认案件事实或签发许可。

## 已保存真实响应回放

这里的“真实响应”指先前 DeepSeek 对独立虚构合同的实际 API 输出；不是客户真实合同。

| 实测项目 | 数量 |
|---|---:|
| 响应 / 不同案例 | 12 / 5 |
| 断言检查次数（含不同候选、重复轮次） | 60 |
| 有计算计划的检查次数 | 18 |
| 计算与证据一致 | 9 |
| 触发复核 | 9 |
| 未覆盖，仍待人工审阅 | 42 |
| 新模型调用 / 新费用 / 新盲测 | 0 / 0元 / 0 |

9 条复核包括 5 条金额结论标签冲突、2 条计算证据链缺项、2 条因整份答案结构不合规而阻断。最后两条来自同一份 C3/n20 回答；其中一条本身算对也保守阻断，不能把 9 都说成 9 个独立算术错误。原始 C3/n20/q2 同时有标签错误，但结构拒绝优先，不重复计入 5 条标签统计。

例：C4/n17/q2 理由算出 970.20 元，却把“945元”标为支持；校验独立算得 970.20 并判不一致。n18/q4 的 4% 不大于 4% 计算正确，但两候选缺少分母和分类依据，仍须复核。n12/q2 对两个金额同时比较。

这是已见答案的事后防护验证，不是新盲测或模型能力提升；通过的 9 条只通过已整理的计算/证据检查，不能说整份回答或解释已正确。

## 命令与证据

- 先新增 31 个计算门回归：模块尚未实现，pytest 收集因 ModuleNotFoundError 失败，exit 1；实现后 31 passed，exit 0。再补精度、循环输入、Unicode及CLI测试，共38个新增测试。
- 最终命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_contract_calculation_gate.py tests/unit/test_contract_calculation_replay.py tests/unit/test_calculate.py tests/unit/test_contract_scoring.py tests/unit/test_contract_pilot_replay.py -q --junitxml=docs/testing/contract-calculation-gate/20261026/targeted.xml`：**90 passed，5.06秒，exit 0**。90 包含38新增项，不重复相加。[JUnit](targeted.xml)
- 四开发检查：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`，均使用项目 `.venv/Scripts/python.exe -X utf8`，均 exit 0。来源门仍提示 G01–G13 未获生产批准；依赖门55包+1构建包，network_calls=0、native_build_verified=false。
- CLI 实际运行 exit 0；回放内容已与正式保存报告逐字段一致核对。自动测试从不同工作目录执行CLI，第二次同路径写入被 FileExistsError 拒绝且文件字节不变；两输入快照的单字节漂移均被拒绝。
- 根代理实际核对12个仓库外原始响应的字节SHA、模型、标签、完整answer及原始request案例，与fixture一致；重新执行原72调用封印/预算核验，通过。三个正式提示词SHA与最初snapshot一致。
- 独立审阅核对8条计划/9比较与原文、33项当时计算门测试、621次答案及2052次计划类型变异、CLI固定快照，未发现需修问题。后补Unicode回归由根代理验证；独立审阅没有检查仓库外原始来源或CLI落盘保护，后两项由根代理验证，不能混称独立验收。

## 本轮交付和未完成项

正式交付位于原任务 outputs：`contract-calculation-gate-report.md`、`contract-calculation-replay.json`、`contract-calculation-verification.json`。未覆盖/未验证项：任意合同自动生成可信计划、解释语义自动核验、新盲测、正式审查接线、已安装版、全仓测试及法律/生产验收。下一步应先实现可信计算计划如何绑定后端已确认事实的接线契约，再做新合成案例验证；不把模型自述或引用片段当成事实确认。

原 C4 仅保留实验候选第一，正式提示词仍是原基线。历史91成功调用峰值估价0.481598元；旧未知请求及预留继续保留，累计保护额19.103326/20元。本片没有重置或释放预算。
