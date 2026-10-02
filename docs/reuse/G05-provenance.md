# G05 复用与限制

仅备选传输；官方指南命名npm qcc-agent-cli但发布gitHead与候选仓库未闭合，不安装、不真实调用。

- 上游：https://github.com/duhu2000/qcc-agent-cli
- 固定提交：`30194cceeb315bde0d42ffe1e7ec0c6addd69548`
- 发行版：未使用发行版
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：reference_only。
- 许可声明：MIT。
- 依赖审查：not_runtime_dependency。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- QCC_off_real_endpoints_not_called
- npm_package_missing_repository_and_homepage_metadata
- npm_1.0.10_vs_GitHub_package_1.0.9_source_chain_requires_followup
- paid_retry_and_budget_controls_are_project_responsibility
- Node_chain_not_installed
