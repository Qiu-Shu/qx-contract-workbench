# G06 复用与限制

固定发行版 PDF 字符、页码、坐标与表格接口已纳入开发依赖；解析功能测试另见 T03 记录，未实测真实合同。

- 上游：https://github.com/jsvine/pdfplumber
- 固定提交：`7d4f2f582f2d99f9e60ba522fdf7afd2f6d54c62`
- 发行版：v0.11.10
- 状态：read_verified；生产批准：未取得。
- 本地采用方式：runtime_dependency，仅用于独立虚构材料开发解析。
- 许可声明：MIT。
- 依赖审查：35 包完整应用/测试 wheel 闭包、60 份许可文件及 40 条依赖边已实际核对，详见 `docs/reuse/T03-dependencies.md`；原生组件许可范围及生产批准仍待审。

目标文件及实测SHA-256在 `sources/upstream.lock.json`；源文件保存在审计证据目录，不是运行指令。

实际安装的 0.11.10 wheel 中 `pdfplumber/page.py`、`pdfplumber/__init__.py` 与上述固定提交的两份已读证据字节及 SHA-256 一致（核对脚本退出 0，2/2）。此核对只覆盖这两份文件，不代表整个 wheel 与源构建可重现。运行 manifest 的 G06 已如实标明 included_in_runtime=true；生产门禁继续阻断审批和原生依赖审查。

已知限制：

- selected_file_audit_only
- synthetic_native_parsing_tested_no_legal_effectiveness_test
- no_production_approval
- no_OCR_native_text_only
- per_page_quality_and_unsupported_objects_required
- no_complete_visual_equivalence_or_pdf_decode_process_sandbox
