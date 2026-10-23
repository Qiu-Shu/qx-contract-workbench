# CH-07C2b1 实施合同独立复核

基线：e133d5c39475388c6f8763d488cbbf3808e6855e。
范围：只读核对 docs/plans/2026-10-23-profile-model-schema.md 及现有迁移、初始化、完整性、备份调用位置。产品源码正在由其他代理实现，本报告不是最终源码审阅；未执行测试、联网、真实材料或桌面操作。

## 结论

0项必须阻断的合同矛盾。作为不开放发送与保存路径的结构前置切片可行。第9行明确拒绝新格式attempt和任意新handler，第10行排除registry/native/runner/HTTP，足以将本片与C2b2启用分开；不能因DDL允许新格式就宣称新记录已可备份或自动建档已完成。

## 实现与后续Spec必须逐项核对

1. **旧结构确实冻结。** storage_schema.py当前11个版本；native/普通各一组原始及规范化签名共22组/44摘要。前代签名必须来自固定基线，不能按改动后的schema_rows动态生成“期望”。历史DDL和旧行所有列保持不变；模型表重建尤其保留input_format、round_no、唯一约束及不可变trigger。
2. **三条路径与首次/重复初始化。** storage_bootstrap.initialize_storage；schema_migrations.upgrade_database（cnbak隔离恢复使用）；web.workspace_upgrade.upgrade（native及qxbak隔离恢复使用）。新模块须加入statements_for和requires_foreign_keys_off共享决策。FK关闭在BEGIN之前、成功和失败最终恢复ON；sqlite foreign_key_check在提交前执行。model/context/rounds/rounds_v2初始化器须认可已完成的新结构，不能幂等重开时拒绝；不以改变旧期望结构规避。
3. **不能漏旧完整性。** attachment_integrity.file_references、model_integrity.validate_model_records、judge_integrity.validate_judge_records、library_integrity.validate_library_records、profile_integrity.validate_profile_records均须识别新版本；模型仍走context_schema和rounds=v2路径。尤其profile_integrity当前在非assistant-profiles-v1直接return，library_integrity在不认识版本且无工具事件时return，这两处不能延续到新版本。补验新版本下各旧数据族的有效记录和篡改拒绝，不只测空库。
4. **封闭检查顺序。** profile-text-v1或非空assistant_profile_handlers应在“无模型记录直接return”之前明确拒绝。需有仅handler存在、无attempt/输出的负例，避免单靠模型记录遍历触发阻断；来源格式校验不能隐式降级plain-text-v1。allowed=False的旧cnbak限制保持。
5. **备份不是只有DDL。** ops.backup._file_references是既有五族校验的汇聚入口；workspace_backup._references也复用它。qxbak创建/解包验证与恢复发布前应拒绝未支持记录，cnbak继续拒绝assistant业务资料；失败不能留下可发布归档/恢复目录。qxbak解包验证不能自动迁移，只有验证后的隔离副本通过workspace_upgrade升级。
6. **固定回执约束。** 本片任何新handler行均不允许进入已验收历史，因此跨记录语义完整证明留C2b2；但DDL应已保证固定handler/version、主键唯一、attempt/output唯一、事件及档案回执FK、成功/无变更有具体回执且无错误、阻断无成功回执且错误白名单、不可更新/删除。
7. **故障验收。** 覆盖表重建每步中断回滚；native SQLite提交后workspace marker写入前中断及pending_matches恢复；旧记录逐列保留；空新表幂等重开；旧备份恢复后旧session撤销/隔离状态保持。WIN-PATH-02原有最终rename WinError5仍开放，不能因短目录测试通过关闭。

## C2b2前应明确的设计语义（不阻断本次封闭DDL）

- v2.1第7.1节原文指assistant_handler_receipts，本合同改为专用assistant_profile_handlers。当前旧表CHECK只允许两种法库handler，独立固定表能避免假泛化；后续记录这是保持相同事件去重与原子成功语义的具体实现选择。
- 失败handler也不可变且每attempt/output唯一，意味着version_conflict/save_failed是该事件的终态；若以后希望同一事件“失败后重试成功”，需先重新设计收据语义，不能换event_id/handler_version绕过去重。原许可及旧基线不能在恢复时自动刷新。

只读结论；未运行测试，不把静态可行性标为运行通过。待实现者宣布源码冻结后再做Spec及必要小范围独立探针。
