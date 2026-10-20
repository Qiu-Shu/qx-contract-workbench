# CH-06B1 独立 Spec 复核

基线 `641a6e82575ec7366ed3aea49214f2655b03c33c`；本阶段 commit list 为空。读取 `git diff 641a6e8 -- src tests` 与新增源码/测试，依据 `docs/plans/2026-10-20-library-ledger.md`、`docs/plans/2026-10-20-library-ledger-execution.md`。

## 发现

**[P2，已修复并独立复验] 保存引用未验证其内容身份摘要。** 设计 §最小接口（第17行）明确 `CitationRef.citation_id` 是“内容摘要”；§Schema（第49行）要求验证“规范 JSON/摘要”。初审的 `src/cn_contract/assistant/library_integrity.py:81`、`:96` 只解析 DTO、验证外层 JSON 摘要与重复快照相等；`library_records.py:18` 未复核 `tools/library.py:117` 定义的 `qx-library-citation-v1` 内容摘要。因此存在内部自相矛盾且完全可离线检出的引用仍被接受。

独立合成复现：把已保存引用的 `citation_id` 改成64个0，同时更新 citation/receipt 两份 JSON 和外层 SHA。历史读取返回错误 ID，备份 `_file_references` 不拒绝；同一未修改法库的 `read_original` 却报 `LIBRARY_CITATION_MISMATCH`。建议共享纯引用校验重算内容摘要，使写入、历史读取与归档一致拒绝；无需访问源文件。

证据：`spec-extra/test_spec_checks.py`、`spec-extra/run-3.log`、`results-3.xml`，1个拒绝测试实际失败。另一条新调用采样当前 composer、旧调用拒绝、旧快照仍可读/可备份的独立测试通过（`run-2.log`：1 pass、1 fail）。首次采集因测试导入路径缺失报1 error；补齐仅本次进程 PYTHONPATH 后完成复现，保留 `run.log`，不将其称产品失败。

修复增加共享 `assistant/citation_identity.py`，生成与持久编解码复用；嵌套结果引用一并检查。保留原 RED 脚本 `spec-extra/red-script.py`，调整现用临时用例允许更早正确拒绝：历史读取报 `LIBRARY_RECORD_INVALID`，归档独立报 `ASSISTANT_LIBRARY_INTEGRITY`。修复冻结后独立复跑两项，**2 passed，exit 0，6.23秒**，见 `run-green.log`、`results-green.xml`。原有逐次 composer/历史读取/备份边界仍通过。

其余静态核对未发现额外范围、权限、幂等、8次额度、原子写入及迁移要求缺漏。结论：**1项P2已关闭，待处理发现0项**。本轴未运行全套、Windows安装或外部模型；没有修改产品与测试目录，不将此结论称全量验收通过。
