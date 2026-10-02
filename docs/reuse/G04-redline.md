# G04 复用与限制

正文段落修订候选；表格/文本框/图片/嵌套列表默认manual_required；关闭受限PDF路径。

- 上游：https://github.com/evolsb/legal-redline-tools
- 固定提交：`1dbc70ddfdf594fc4699c31b9077d15e74be56a0`
- 发行版：未使用发行版
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：runtime_candidate。
- 许可声明：MIT。
- 依赖审查：direct_metadata_reviewed_transitive_lock_pending。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- table_textbox_image_nested_list_targeting_not_supported
- disable_upstream_Latin1_PDF_export
- upstream_normalized_text_matching_requires_unique_structural_anchor_adapter
- PyPI_package_not_found_installation_route_requires_explicit_commit_build
