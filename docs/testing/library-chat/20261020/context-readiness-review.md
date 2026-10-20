# CH-06B2b 接续准备独立审查

2026-10-20；只读审查，产品保持冻结。审查对象 `docs/plans/2026-10-20-library-context-readiness.md`，SHA256 `99dc5e3a0384aaa0e8e2ea237a7f0b074809afcff27891cd2516767f25b08da0`。这是下一切片方案审查，不表示 B2b 已实现、测试通过或获准外发资料。

方案的单次回答、独立新运行、完整预览、版本隔离及实际费用保留均有现有接口可承接。建议实施前补明以下四处，未发现需要推翻路线的问题：

1. **格式分派覆盖完整链路，缺失上下文不得回退 V1。** 第 34—41 行只点出 `main.py` 和存储；实际严格 V1 入口还包括 `MainModelRegistry.grant`（`registry.py:80`）、`_RuntimeLease.check_execution`（`:177`）、`_LeaseProvider.generate`（`:202`），以及 `attempts.read_attempt/enqueue_generation/_current/settle`、`policy.prepare`、`model_integrity._validate`（`:134`）。选择新 schema 时仍需明确每条 attempt 的不可变格式标识，原子登记 run/attempt/清单/来源；归档验证缺行、孤立关系或格式矛盾时拒绝，不靠“有清单就是 V2、没有就是 V1”分类。普通 V1 字节保持原样。

2. **后继版本与来源权限是新增校验。** 第 29 行方向正确，但当前 `attempts._current`（`:120—135`）只检查 scope、配置、许可等，不检查 composer_revision 或选片集合。上下文分支须保存登记后确定的 composer/input 状态，在 claim 和 settlement 重新核对来源权限及批准清单。复用 `settle` 时保留 `:217—235` 的实际费用回执与“授权审计可能提交事务后重新检查 fence/claim”顺序；不能因引用撤权直接丢弃已发生费用。

3. **“不接 Jev”必须落实在调度层。** `GenerationTasks.submit`（`task_manager.py:85`）会为新主模型运行调用 `_reserve_judge`，`_execute`（`:151—156`）会执行已有辅助许可。仅取消原生窗口的勾选并不足够。上下文路径应明确跳过预留和执行，继续共享容量/退出清理；补一个“既有有效 Jev grant 仍产生零辅助调用”的合成验收，普通文字行为不变。

4. **“同请求回读”区分登记重放与恢复读取。** `enqueue_generation`（`attempts.py:71—83`）在查旧请求前先检查当前 runtime 和许可；registry grant 也按工作区/用户/会话替换 nonce。不能假设重启或新授权后旧 POST 必然成功。未知结果应通过不重新授权、不派发的已有运行/历史查询确认；若要扩大 POST 的只读回放语义，必须另定范围检查，不能为读历史自动授予新许可。

另保留现有历史边界：`providers.history.read_history` 和 `model_integrity._validate` 均要求当前 binding_revision；方案当前绑定内选片与之相符，不应顺带放宽普通模型历史。第 19 行的“伪造核验状态”应落实为禁止模型控制结构化状态、原文和引用身份，不能声称任意自然语言错误都可自动识别。

验证：先用 CodeGraph 定位，再逐段核对上述源码、`native_model_control.py`、`domain.py`、`model_schema.py` 与原生确认实现。未执行测试、调用外部 API、使用真实资料或修改产品；本审查不替代后续 schema 决策与合成验收。

统筹处理：上述四点已补入下一片方案的数据/许可、完整分派和合成验收段；仍为未实施的设计，不改变本片冻结代码。引用状态限制已明确为结构化约束，不承诺自动识别任意自然语言错误。报告内方案摘要保留原审查时点，不冒称后续文案已独立复审。
