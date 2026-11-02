# 阶段 3 独立审阅

日期：2026-11-01。产品代码只读，所有探针和数据仅在本 review 目录；没有接触真实客户材料、模型、微信、生产数据库或外部账户，也未读取、摘抄本轮实际九份私有接待资料。

## 结论与已修复问题

发现的一个 P2 已由作者修复，独立复跑通过；当前所审范围无新增实证阻断。此结论不是阶段 3 全体验收或生产完成。

P2：`integrations/knowledge.py` 的 `reception()` 验证 manifest.json 摘要后丢弃已验证字节，重新交给 `KnowledgeStore.catalog/search/document` 读取同一路径。若该文件在首次摘要校验后替换，检索来源可能已是另一个 manifest，但 KnowledgePassage.index_sha256 仍标记原批准摘要。

独立合成反例 `test_reception_never_labels_a_reopened_manifest_with_old_pin`：仅在首次 pinned 返回后替换合成 manifest 中的来源标题；retrieve 返回了替换后未批准的标题，却仍声明旧索引摘要。原件内容、文档摘要与目录均没有伪造。建议从已校验的 catalog 快照检索，document 对来源的选择也使用同一快照；或保证每一次 catalog 读取都与批准摘要一致。

`phase3-independent-first.xml`：退出码 1，1 failed / 2 passed，1.51s。该失败是实证来源版本错配，并非已证明有生产信息外泄。

作者修复：`reception()` 将 pinned 返回的原始字节传给 `KnowledgeStore(manifest_bytes=...)`，后者 catalog/document 统一从该不可变字节快照取得来源记录，正文及原件仍逐一验证摘要。独立原反例现已通过。

## 已通过的独立验证

`test_phase3_independent.py -k 'not reception'`：退出码 0，4 passed / 1 deselected，6.94s，记录在 `phase3-independent-stable.xml`。

最终完整窄集：`.venv/Scripts/python.exe -X utf8 -m pytest .local/unified-plan-20261101/review/test_phase3_independent.py -q -p no:cacheprovider --basetemp=.local/unified-plan-20261101/review/pytest-phase3-final --junitxml=.local/unified-plan-20261101/review/phase3-independent-final.xml`；退出码 0，**5 passed in 6.43s**。

- 修改 public adapter 文件而不更换批准摘要，在执行前返回 KNOWLEDGE_UNAVAILABLE；合成执行标记文件没有产生。
- 阶段 2 已保存的 6 份实际合成输入仍可用当前 DTO 与 codec 按原字节重建，原演练输出仍可校验。
- 更新可信配置的法库内容摘要后，同任务继续进入 evidence：旧回合保留旧版本来源卡，新回合记录新摘要；所有卡片仍未核验。移除当前配置后全账本历史可验证。
- 模型把案件材料 ID 放入 knowledge_ids，被拒绝为知识来源卡，成果为空但费用回执保留。

原生兼容探针重新读取本审阅 9 份实际 Python 合成 basis（含阶段 3 的知识字段、旧回合来源卡），全部通过 JS validator 与 ModelControl 精确传递，额外根路径与错误角色仍被拒绝。命令 `node .local/unified-plan-20261101/review/native-material-probe.cjs`，退出码 0。

## 审阅范围与未验项

已读知识 DTO、检索/登记、材料自动检索、模型输入及引用校验、历史回放、持衡来源卡装配、Word 投影和聊天渲染及原生结构校验。家事片段为固定原文 SHA 与 1200 字符定位，法库片段保留 corpus、原条文和摘录摘要；来源文本与 URL 仅作为参考数据；渲染使用文本节点。当前审批和版本重建仍由后端核验。

未跑全套、未验真实模型或真实微信、未对真实接待资料进行内容审计；没有把参考材料标为现行有效法或已批准对外使用。本轮 P2 来源追溯缺陷已关闭，阶段总门仍应按作者完整验证记录判定。
