# G07 复用与限制

OCR按页按需；本轮未下载模型/安装，模型与依赖许可另核，不支持时显式unsupported。

- 上游：https://github.com/PaddlePaddle/PaddleOCR
- 固定提交：`dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf`
- 发行版：未使用发行版
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：reference_only。
- 许可声明：Apache-2.0。
- 依赖审查：not_runtime_dependency。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

已知限制：

- selected_file_audit_only
- no_runtime_or_legal_effectiveness_test
- no_production_approval
- OCR_deferred_no_model_download
- model_licenses_and_Paddle_dependency_tree_pending
- OCR_unavailable_must_be_explicit_unsupported
