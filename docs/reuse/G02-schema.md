# G02 复用与限制

目录、schema和fixture组织参考；四类首发类型自有扩展，to_confirm不能作为严重程度。

- 上游：https://github.com/Xigua9xi/ai-legal-review-skillkit
- 固定提交：`4a1e417a3152cef15df2aa410235099d35dee43c`
- 发行版：未使用发行版
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：method。
- 许可声明：MIT。
- 依赖审查：not_runtime_dependency。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- upstream_contract_type_enum_requires_service_lease_nda_extension
- to_confirm_is_not_risk_severity
- legal_rules_require_independent_source_and_lawyer_approval
