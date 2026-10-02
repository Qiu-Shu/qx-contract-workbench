# G06 复用与限制

固定发行版PDF字符、页码、坐标与表格接口候选；扫描页必须显式识别，尚未实测合同。

- 上游：https://github.com/jsvine/pdfplumber
- 固定提交：`7d4f2f582f2d99f9e60ba522fdf7afd2f6d54c62`
- 发行版：v0.11.10
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：runtime_candidate。
- 许可声明：MIT。
- 依赖审查：direct_metadata_reviewed_transitive_lock_pending。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- no_OCR_native_text_only
- per_page_quality_and_unsupported_objects_required
