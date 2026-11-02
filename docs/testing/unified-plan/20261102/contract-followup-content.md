# 合同同任务补件：工程与内容证据

2026-11-02，按 `docs/plans/2026-11-02-contract-followup-content.md` 实施。材料为独立作者新编的主服务合同、保密协议及待签署补充协议，共763汉字；不是客户材料。原件经实际DOCX上传和解析，两组分别使用隔离SQLite。C4为既有 `SYSTEM + METHOD`，对照当前 `contract-review-v2`，不是合同v1对v2。

## 已修复的实际缺陷

当前用户说“请站在乙方供应方立场”或“仍代表乙方供应方”，后端立场校验曾拒收明确的供应方结果。根因为 `_roles` 的起始匹配不支持明确方称及接续词。WorkBuddy按限定范围只修改这一匹配，保留角色词要求、当前用户原话引文及否定/假设/他人陈述/冲突拒绝；合同方法提示词、DTO、默认方法和旧版本均不改。

WorkBuddy实施任务 `wb-bg-5648fb5f9070` 的 requested/actual 均为 `deepseek-v4.1-flash`，桥接核验成功，worker释放，仅对授权产品文件执行Edit。其先前只读审阅把C4与新合同版本概念混淆，统筹据实际 `material_codec.system_for` 和旧请求测试纠正，没有采用该建议。

## 本轮工程验证

证据根：`.audit-local/contract-followup-content-20261102/`。以下为本轮实际执行，不累计历史测试。

| 检查 | 命令及实际结果 |
| --- | --- |
| 新增立场反例RED | `python -m pytest tests/unit/test_contract_stance_followup.py -q`：5失败、7通过，退出1；XML及日志保留 |
| 修复后关联集合 | 上述文件、`test_contract_review_method.py`、`test_contract_review_codec.py`、`test_contract_review_quality.py`、`test_contract_live_method.py`、集成`test_contract_review_pipeline.py`和`test_material_followup_history.py`：114通过，退出0 |
| 独立审查目标检查 | 27通过，退出0；包含于114项，不重复累计 |
| 四开发门 | schema、defaults、sources development、runtime dependencies development分别退出0；原始命令和回执见`development-checks.json` |

独立审查发现匿名评审包仍含宿主方法来源页尾，已在生成前修正；删去确定的元信息并保留全部实质成果及未修改原答。立场修复及实验构造审查通过；随后实际运行另发现下文所述历史容量缺口，该产品问题尚未修复。评审样式仍可能暴露方法差异，不视为严格实验双盲。

最终完整性核对：7094个原有文件无丢失；原暂存摘要保持，334份前轮证据未变；冻结输入、552份源码快照、三个原答及运行结果、C4第二轮生成前摘要、匿名评审输入均保持。两份有效评分及Flash终态原回执收到后摘要一致；`integrity.json`与`score-provenance.json`分别记录。产品文件仅立场匹配一处改变，另新增目标测试及本轮文档；未覆盖已有混合修改。

## 内容验证边界

初始输入、两轮问题和每轮6项检查、生成程序与评分协议在生成前冻结；第二轮请求须在本组第一轮实际入库后构造，再单独冻结。第一轮仅两份原草稿，第二轮补件是拟议待签署稿，必须区分条件性改善与原风险，不能把历史回答当事实。各组原答仅生成一次，无效保留，不重试。

内容由Codex生成代理产出；工作台只调用本机loopback，把这些原答交给真实解码、账本、保存、回读流程。loopback固定42 Token及估算费用为测试数据；实际内容生成模型修订、Token和费用未知，不能称真实伙伴模型验收。未加载知识注册器，未验证知识检索。

实际获得3/4份原答：C4两轮及v2首轮，三份均通过实际解码、保存、回读，v2首轮13条逐字引文通过；C4的7/11个来源标识通过绑定校验，不将这种校验说成逐字引文核验。C4第二轮同任务、材料2→3、版本递增、历史全文一致，旧成果保持。实验共3次loopback请求。

v2首轮渲染正文13,823字符/33,997 UTF-8字节，完整历史问答34,565字节，超过32,768上限1,797字节。`material_history.select_history`整对break并返回空历史；任务、actor及固定作用域均一致，材料版本4→6，输入版本1<2<3，非关联失效。实验脚本的history断言失败并中止后续生成，退出1；**产品预览本身未报错，仍有静默丢失上下文的问题**。保留原DB、原答和原日志，另存`history-diagnostic.json`的实际重建结果。v2只有1个模型attempt/output，没有第二次模型发送。

因此本轮完整续办比较未通过，第二对不进行虚构配对评分；评分只描述已完成第一对，完整分母及分歧见[本轮内容报告](../../legal-method-ab/contract-followup-review.md)。下一片按[历史容量计划](../../../plans/2026-11-02-contract-history-capacity.md)先消除静默遗漏，再设计有版本的兼容承接；不能直接全局扩容，因为旧记录验证会按规则重建并比较历史。

一次案例两轮不构成独立重复统计，不能宣布稳定提升、技能正式采用或生产完成。桌面未改，沿用前轮结果但不计作本轮验证；未提交、推送、安装、调用真实工作台模型/QCC/微信或外发函件。
