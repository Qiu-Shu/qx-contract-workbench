# Parser Task 独立审查

## SPEC：PASS

审查固定范围为 `934689a..32db1bb`，仅四个文件；依据 `task-parser-brief.md`、`task-parser-report.md` 和 `task-parser-diff.txt`。未参与本任务实现，未读取实际合同，未修改产品、测试或索引，也未重新运行测试。

- 有限分隔符识别满足要求：`src/cn_contract/documents/docx_adapter.py:64` 仅允许两条不同的 separator / continuationSeparator，校验数值 ID、对应标记、单段/单 run、有限 spacing 属性与枚举；非空正文、额外元素/属性和模糊身份继续拒绝。
- WPS 配置边界准确：`src/cn_contract/documents/docx_adapter.py:102` 仅接受 AlternateContent → Choice(Requires=wpsCustomData) → 指定命名空间的直接 typoFeatureVersion 叶节点、无命名空间 val=0；多余包装、Fallback、可见文本、额外属性与其他版本不被忽略。settings 的接入限制在根设置下（`:146`）；font altName 为 font 下的非空 val 叶节点（`:163`）。
- 新增 footnotes/endnotes 分类仍绑定原生 relationship、content type、document source 和精确 root（`src/cn_contract/documents/docx_adapter.py:230`；既有匹配门 `:276`）。未采用按文件名跳过部件的规则。
- 提示区分真实缺件与已收但未完整读取：`src/cn_contract/assistant/business_preparation.py:97` 仅对存在 media blocker 的任务调整主合同提示；空任务的“请上传主合同”保留（`:92`）。`tests/integration/test_assistant_business.py:242` 验证真实上传的虚构 partial 文件提示正确，且 freeze 仍返回 409。
- ⚠️ 此差异只能证明新解析分类及业务提示；实际原件的历史 revision 保留、升级后的新 revision 选择和完整执行接续属于跨任务验收。报告中的原件 105 anchors 结果为 root 提供的离线证据，不算本审查亲自验证。

## QUALITY：Approved

实现将有限结构识别隔离为两个局部 helper，现有包关系门与文本提取路径保持原有职责。测试直接构造独立虚构 DOCX 并经过解析或业务 API，覆盖正例及正文、关系、外链、根、命名空间、版本、包装、属性、分隔符身份等反例（`tests/integration/test_docx_office_parts.py:391`、`:402`、`:424`、`:450`、`:460`），没有以 mock 返回值代替行为验证。

Critical / Important / Minor：均未发现需要报告的问题。

## 有界补充检查与证据

- 具体风险“辅助部件误判绕过 relationship/source/root 校验”：补看固定提交中 `_classify_auxiliaries` 的对应匹配上下文（`:217–292`）；新增 role 仍走同一校验链。为定位引用也展开过固定提交的相关源码上下文，未检查其他功能。
- 具体风险“提示修正顺带把 partial 材料当成可执行”：仅检查 `src/cn_contract/task_drafts/service.py:130` 的 `_manifest` 与 `:483` 的 freeze 条件；partial 产生 media_not_readable、不能成为 ready 主合同，freeze 再计算 blockers 后拒绝。不修改该文件。
- 已读取 `parser-commit.log`：最终目标门 **48 passed / 58 deselected / 10.65s**；`parser-reparse.log`：既有 revision 保留检查 **1 passed / 13 deselected / 2.68s**。两份日志无 warning 输出，报告记录退出码均为 0。未重跑。
- 报告已明确较早 163 项和 103 项检查早于最终结构收紧；本审查未把它们冒充最终提交全量验证，也未把重叠数量相加。
