# G09 复用与限制

复杂布局解析暂缓；同样本比较证明适合且许可、依赖审查后才采用。

- 上游：https://github.com/docling-project/docling
- 固定提交：`a25aa1dedccf74572df0385cde0cf02fb059b92c`
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
- deferred_pending_same_sample_benchmark
- model_download_dependency_and_license_reviews_pending
