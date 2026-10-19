# CH-05A Spec 预审发现

基线 `7dd5abb`，当前未提交 DTO/路由；2026-10-20 本地。仅合成数据，不读真实密钥、不发网络。

## P2：内部结果复验未保持固定问题语义和绝对截止

`JudgeResult.result_evidence` 只核验总体状态，未将 question ID 与答案类型、完整 criteria 集合绑定。`primary_intent` 配单个 `client_reply:1` 概率的结果，或超过 2,000ms 的 `ok` 结果仍可构造；`choose_workflow` 的二次复验会采用前两者。这使路由入口在 `model_copy` 或持久化重建等旁路下无法保持“只有符合协议、及时的判断可采用”的契约。

复现使用完整有效模型版本/作用域和合成请求 ID，不依赖不受信任字典被直接当 DTO。建议在问题包装处核验固定 ID 对应类型与完整选项，在 `ok` 包装处拒绝大于全局最大截止的耗时；更低的配置截止仍由提供器执行。通用 `JudgeChoice` 无需变成只支持一种问题。

## P2：RouteDecision 三字段可以表达互相矛盾的状态

例如 `workflow='contract_review', source='current', reason_code='no_suggestion'` 当前可构造。下游可能分别解释 workflow 和 source/reason，从而出现宣称继续现有流程、却实际带新工作流的状态。纯函数当前正常分支输出一致，但新业务 DTO 的契约应拒绝这类构造及序列化重建。

建议将 explicit + explicit_skill + 非空 workflow、jev + jev_suggestion + 非空 workflow、current + 三个保留原因 + 空 workflow 固定为合法组合。

## 独立复现

`PYTHONPATH=src;.`，执行 `python -m pytest .local/jev-adapter-20261020/review-spec/probe_contract.py -q --junitxml=.local/jev-adapter-20261020/review-spec/contract-red.xml`：exit 1，12 failed / 2 passed。12 个失败是上述两类缺口的边界变体，不是 12 个独立缺陷。正常显式优先、拒绝不可选技能、合法 Choice/Noul 不扩大路由的两项独立探针通过。

作用域/配置摘要与当前任务是否匹配由未来调用方负责；三参数纯函数没有当前任务参数，此处不把缺少该验证误报为本片缺陷。完整原请求保留也未因 DTO 内没有冗余布尔值而误报。
