# G12 复用与限制

来源核验、安装/许可与治理结构参考，不整套引入外国法律规则。

- 上游：https://github.com/anthropics/claude-for-legal
- 固定提交：`4a6c651889c97cc9140580363c73e0eb17379c2b`
- 发行版：未使用发行版
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：method。
- 许可声明：Apache-2.0。
- 依赖审查：not_runtime_dependency。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- governance_reference_only_not_foreign_law_rule_source
