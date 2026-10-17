# CH-04A 模型表与升级链独立复核

2026-10-17。结论：**本次限定范围内明确问题 0 项**。这是源码复核结论，不是新的运行通过记录。

范围：`assistant/model_schema.py`、`assistant_attachment_schema_baseline.py`、`storage_schema.py`、`schema_migrations.py`、`storage_bootstrap.py`、`tests/integration/test_assistant_model_schema.py`，以及关联升级测试改动。参考基线 `114a1ab` 与当前工作树；依据 v2.1 的增量迁移/原件与历史保持边界及 `docs/plans/2026-10-17-main-model-execution.md` 的“追加结构与兼容”。已通过 CodeGraph 查升级、初始化和测试调用关系，再读取源码与差异。

## Standards

明确问题 0 项。新 DDL 独立于页面、供应商和 runner；bootstrap 只增加既有初始化序列中的一项，未扩写 app。业务 JSON 结构仍由集中 domain DTO 和应用/完整性层处理，没有在 schema 文件重复创建业务模型。部分模型结构存在时逐项比对 sqlite_master 后拒绝缺失/变更结构，没有悄悄修补损坏的旧表。

## Spec

明确问题 0 项。

- 历史 attachments-v1 改用固定快照；旧 assistant/intake 基线未修改。新增 model-v1 只追加模型对象，旧结构仍独立可识别。
- 原生升级继续复用逐版本备份、receipt、精确前后摘要、DDL事务和 marker 中断恢复；数据库独立恢复迁移仍先识别旧结构，再在一笔事务中完成缺失步骤。新增分支没有绕过这些公共规则。
- attempt 输入、配置、政策、预占、归属和创建时间不可更新；已存在 claim 不可替换/清除；回执与成果不可更新，三表均不可删除。run/attempt/output 的唯一约束与首片“单次生成”范围一致；状态列保留恢复时需要的变更能力。
- 阅读的测试覆盖固定历史摘要、未来 initializer 不影响历史识别、迁移失败回滚、不可变输入、单次 claim、只读历史、去重、部分结构拒绝，以及新版本的原生 marker/DDL/损坏恢复分支；没有发现为通过新版本而删除旧场景的改动。

未重复执行已有 65 项目标测试，未修改源码或测试；没有把正在由其他代理完成的 model_integrity/ops 对接、完整回归或冻结验证计作本次缺陷或通过。跨表业务归属、收费结算和恢复内容完整性需由其对应审阅与目标实测另行确认，不以本次 schema 静态复核代替。
