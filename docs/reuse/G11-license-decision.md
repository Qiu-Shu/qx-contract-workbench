# G11 复用与限制

上传A包声明AGPL且无完整许可。当前上游根CC-BY-NC-ND-4.0与目标Skill许可分开；无批准禁止复制/加载。

- 上游：https://github.com/lawve-ai/awesome-legal-skills
- 固定提交：`180fd1582cc56fb0fc122a8e734ff3a1a666b87a`
- 发行版：未使用发行版
- 状态：candidate；生产批准：未取得。
- 本地采用方式：reference_only。
- 许可声明：AGPL-3.0 (declaration per supplied specification; exact target declaration unverified)。
- 依赖审查：not_runtime_dependency。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- AGPL_skill_not_copied_or_loaded
- license_approval_required_before_any_use
- uploaded_A_package_not_byte_compared
- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- root_CC_BY_NC_ND_is_not_target_AGPL_license
- target_Skill_license_header_not_fetched
- exact_AGPL_version_and_or_later_option_unverified
