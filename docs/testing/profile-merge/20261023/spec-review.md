# CH-07A Spec 独立复核

基线 `a6d20edf8663222ce6469bae80edfc92c02627b2`，目标当前未提交工作树。依据本片计划、档案就绪设计及 v2.1 第5/10节。只读产品；独立合成 DTO，无数据库、模型、外网或桌面。

## 最终复核：两项已关闭，剩余 0 项

2026-10-23 本机时间，主代理完成修复并通知冻结后，原样复跑下列命令：**6 passed、exit 0、0.41秒，4输入摘要前后一致**。`spec-command.json` 绑定最终 domain SHA256 `f868f368348ec3837148d94992a77fcae3fe5d6e396733c877c2d1c7d0347ac4`、profiles SHA256 `dc2fa65bb194d3cd97a80cb77a0f0ca9466ff2f5895cbcf7b10402bbc9c565b4`；日志/XML 为 `spec-probes.log/.xml`。

已知 contact 不论模型声称哪种 origin 均拒绝，unknown 可保留；本片只有受信人工输入可写实际 contact，未宣称自动本地身份识别。ProfileFieldState 校验与合并复用同一核验状态派生规则，伪造旧状态在入口复验时拒绝。另只读检查了新增历史引用会话/版本约束、锚点归属及 origin/kind 约束；其专项运行结论由 Standards 轴报告，未冒计为本6项。

以下保留首次发现；原失败命令/hash/日志/XML 已复制为 `spec-initial-command.json`、`spec-initial.log/.xml`，不覆盖或删除。

## 首次需修 2 项（已关闭）

1. **P2：模型可补造联系方式并进入接待投影。** v2.1 §5.2/§5.3 要求实名/联系方式本地明确识别，不能由模型补电话号码。`ProfileProposal.model_may_only_propose` 与 `profiles._check_sources` 只查 source ref 是否精确，不限制 contact 来自可信本地输入。反例以“没有联系信息”的真实合成引用配 `origin=model_inference`、`contact=合成联系人，电话 00000000000`，merge 正常接受并投影。建议 contact 的模型提案只允许 unknown；实体值走已有受信本地/人工编辑，或补严格本地映射核验，不能仅靠提示词。

2. **P2：无变化分支返回未经一致性验证的旧字段核验状态。** 设计要求入口重验 model_copy 与 unknown/冲突一致。`merge_profile` 129–153 行先 `_field` 规范化旧候选得到 before，但 after==before 时直接返回原 previous；`ProfileFieldState` 未校验 verification 与 candidates/protected_value 的派生关系。已知候选的 verification 改为 unknown 后空 patch 被接受，返回 profile 仍称 unknown。实际投影却按规范化后的字段选值，两者不一致。应拒绝不一致旧快照，或明确规范化并返回一致状态；人工保护仍独立于事实确认。

## 首次实测（历史）

命令：`.venv/Scripts/python.exe -X utf8 .local/profile-merge-20261023/spec-run.py`。

**2 failed、4 passed、exit 1，0.53秒，4输入摘要稳定。** 完整子命令/hash 在 `spec-initial-command.json`；首次日志/XML 为 `spec-initial.log/.xml`，原样反例为 `spec-probes.py`。其余4项证明旧人工空字段不丢、人工null压过冲突且提案顺序确定、错位置/跨工作区拒绝、错解析版本拒绝及精确锚点保留。

没有发现新增权限/schema/持久化入口；未运行全套或真实材料。第一项的摘录匹配不证明值的语义真实性，禁止模型联系方式投影是可机械核验的最小边界。最终 Spec 通过仅指本片纯内核及已测范围，不是自动建档持久化或模型接线完成。
