# G03 复用与限制

与B包去重；角色/已签未签方法参考，不复制来源不明市场基准。B上传包无随包许可。

- 上游：https://github.com/evolsb/claude-legal-skill
- 固定提交：`bca0d2e9d5ec81298ddfbfde78fa4f38fb4589b0`
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
- market_benchmarks_and_thresholds_not_verified
- uploaded_B_package_not_byte_compared
