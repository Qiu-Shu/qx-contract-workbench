# 全套临时目录路径诊断（独立合成、未改产品）

2026-10-20，针对 `test_40_samples_really_parse_confirm_and_store_engineering_runs` 首个失败进行最小差分诊断。未重复全套、未触碰真实库、未写全套正在使用的临时目录。

## 已证实

1. 只读查询首个失败目录的 `protected-state.db`：`matters`、`audit_events`、`fact_snapshots`、`review_runs` 均0；只有数据库不足以单独判断原因。记录在 `path-diagnosis-initial.json`。
2. 取固定独立合成样本 `sales-dev-1`，调用现有 `create_matter → ingest → candidate_parse → confirm_facts → run_review(MockProvider)`。两个全新D盘诊断目录只改变根目录深度。
3. 短根目录85字符，最终 original.bin 路径182字符：解析完成、确认3项事实、18维mock运行完成。
4. 与失败目录等长的独立深根175字符：`persistence.py:315` 的 `path.parent.mkdir(parents=True,exist_ok=False)` 对259字符路径抛 `FileNotFoundError [WinError 206] 文件名或扩展名太长`。两次独立深目录均复现；失败发生在 ingest，尚未创建原件。
5. `sample_runner.py`、`persistence.py`、`documents/ingest.py` 与基线 `0d53fdf` 字节相同；四个诊断输入源码SHA前后不变。本片没有修改这些路径处理代码。

证据：`path-diagnosis-single.py` / `.json`，命令 `.venv/Scripts/python.exe -X utf8 .local/library-context-20261020/path-diagnosis-single.py`，过程退出码0（诊断捕获预期失败）；JSON保存两组真实状态、trace及SHA。`path-diagnosis-verify.py` 对记录断言短路径完成、深路径WinError206、输入未变，退出0。

## 限定结论与处置

深路径导致既有导入路径在本机产生Windows错误已证实，足以建议停止过深basetemp的全套，保存未完成/失败记录，并将后续目标回归放到D盘更短且唯一的目录。此结论不意味着所有当前F都由同一原因造成，原失败完整trace尚待父任务结束后核对。也不证明实际应用支持任意长路径；这是既有Windows路径限制，不应标为本片已修复。

建议本片按实际相关接口完成回归并如实记录全套中止，不为一个“全绿”标签重复未受影响的40分钟历史测试。若后续需要完整集合，短基目录应在生成最终业务路径后仍留足UUID/文件名空间。

首次诊断脚本在短路径流程已完成后读取不存在的 `parsed.status`，仅记录阶段报 AttributeError；原脚本/结果保留为 `path-diagnosis-fixture-error.*`。修正诊断元数据字段后重跑，未修改产品。

另：Spec审查中的integration测试文件更名已按原记录SHA核对内容一致，并补充到`spec-review.md`，没有重复6项审查探针。
