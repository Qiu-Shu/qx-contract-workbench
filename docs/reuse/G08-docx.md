# G08 复用与限制

固定发行版新报告与OOXML访问候选；不承诺所有Word对象读取与修订。

- 上游：https://github.com/python-openxml/python-docx
- 固定提交：`e45454602b53e8e572b179ccf1c91093ec9f4ed7`
- 发行版：v1.2.0
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：runtime_candidate。
- 许可声明：MIT。
- 依赖审查：direct_metadata_reviewed_transitive_lock_pending。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- not_full_OOXML_coverage
- paragraph_list_excludes_revision_marks_and_tables_require_separate_traversal
- native_revision_support_requires_separate_adapter
