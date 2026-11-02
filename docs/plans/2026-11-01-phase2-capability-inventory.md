# 阶段 2：能力来源与接入前置清单

后续状态：本清单以下是实施前盘点。阶段 2 已完成源码及隔离配置验收，实际接入与测试见 [阶段 2 结果](../testing/unified-plan/20261101/phase2-results.md)；未更新安装版，统一知识检索继续在阶段 3 实施。

2026-11-01，本机源码核查。本文是阶段 1 回归期间准备的接入清单，不是 Skill Registry 已运行的证明。按用户后续六阶段方案，知识统一属于阶段 3；本阶段先固定能力来源与适配边界。

## 已有能力和复用位置

四项业务均沿用 `domain.py` 的 `BusinessInput → BusinessResult` 和 `MainMaterialSelection → MainMaterialSendBasis → MainMaterialOutputView`，保留 `ScopeSnapshot`、任务 ID、材料摘要、模型账本与内部待核成果。不新增第二套会话和收费系统。

| 能力 | 当前运行入口 / 版本 | 应接来源 | 接入状态与输出边界 |
| --- | --- | --- | --- |
| 客户接待 `sales` | `assistant/business.py`；`material_codec.system_for` 的 `reception-output-v1` | 用户现有“超级销管智能体”，本机登记“超级销冠智能体”，id `gpt-958c124d339690e7de1ff546b82df4fe`；律师接待派生包 `legal-client-reception` 0.4.0 | 当前本地提示词不等于已加载该 Skill。保留源身份、知识索引和九份资料关系；成果为内部接待底稿和客户回复草稿，不自动发送 |
| 案件整理 `case` | `material_codec.system_for` 的 `task-output-v1`；现有事实/证据/跟进工作表 | 家事及通用办案本地 0.2.0 工作树 | 用户已确认自行研发并授权本地接入；适配器尚未实现。输出事实、时间线、争点、待补证据和文书草稿 |
| 合同审查 `contract` | `assistant/contract_method.py`、材料装配及现有合同成果链 | 主仓现有实现；后续按任务需要接入已批准专项技能 | 保留既有版本、锚点、材料选择和签发边界；本次不重写引擎 |
| 模拟法庭 `court` | 当前为 `material_codec.py` 中 `court-output-v2` 多角色文本 | 持衡 `mock_hearing.py` 的 `create_session/load_session/hearing_progress/append_turn` | 尚无主仓 `integrations/chiheng_adapter.py`。需接既有回合存储；单次多角色回答不能标作持衡已参与运行 |

权限仍由主仓的事项成员、会话所有者、材料版本及调用许可校验负责；技能来源不能授予业务权限。所列版本为静态核对，真实模型质量和律师验收未在本轮执行。

## 来源固定与实际缺项

| 来源 | 固定点 / 证据 | 下一小步 |
| --- | --- | --- |
| 群兴 | `codex/contract-review-v2`，HEAD `15acd84546616f8c44dc394e04bf7753cad72739` 加已备份的 0.6.0 工作树 | 先以阶段 1 证据关闭 S1/S2；不覆盖已暂存内容 |
| 家事 | 本地 `C:/Users/Administrator/Documents/Codex/2026-10-13/new-chat/outputs/songmeng-family-law-skill`；HEAD `65cabd5cf0641997fbed6441da47e63275e85b51`，0.2.0 尚未提交 | 补齐上游仓库/许可原文和已有使用批准记录，再冻结本地树摘要与适配输入输出。不能以旧提交号声称锁定了新工作树 |
| 持衡 | `.local/integrations/chiheng-legal-workbench`，Windows 续建 `8a0d640bb58c82b909409a2e689a6cecd7f06058` | 复用其会话/回合 API，明确群兴 task_id 到持衡 session_id 的映射、角色、回合号、来源与失败状态，不复制法库 |
| 接待资料 | `.local/integrations/legal-reception-plugin` 0.4.0；`reception/knowledge.py` 已有 `KnowledgeStore.catalog/search/page/resolve` | 复用既有导入和哈希校验；`web/reception_assistant.py` 已提供独立知识入口，但 `material_preparation.assemble` 尚未自动调用。统一入口需要实际检索记录与来源引用 |

家事 `THIRD_PARTY_NOTICES.md` 第 6–10 行保留 Stephane Boghossian / AGPL-3.0 标识。只读 GitHub 补查找到公开候选入口，固定提交与缺项见 [来源补查](2026-11-01-family-source-check.md)。用户随后明确提供 `Qiu-Shu/songmeng-family-law-skill`，说明本机版本更新、项目由其研发，并授予全部权限。按最新直接授权，本地运行接入阻断已解除；沿用本机 0.2.0 工作树，保留原作者、来源及许可标识。该授权不改写第三方来源事实，也不表示已完成对外打包分发审查。

持衡 `third-party-notices.md` 记录 Apache-2.0 上游方法归属；该说明不覆盖法库中所有资料的再分发权限。`docs/shared-library-contract.md` 的来源卡、版本、未知效力和 `unverified_mirror` 状态须原样传递，检索命中不等于法律依据已核验。

## 下一阶段验收应取的证据

每项接入先用合成 Skill/材料建立失败测试，再逐项实现适配。证明至少包括固定来源树摘要、实际调用的能力 ID/版本、输入材料版本、读取的知识片段、任务和成果 ID、失败/降级状态。只注册一个名称或在界面显示卡片不能通过验收。缺来源时保留明确阻断，不悄悄回退为通用回答。

本清单不批准真实模型、真实微信、上传资料、安装覆盖、提交或发布。伙伴模型接口协议及数据边界仍待提供，不能宣称完成后续联调。
