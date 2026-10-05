# B1a / F04：普通 DOCX 部件与有限样式

日期：2026-10-05。全部输入为本机独立虚构材料；原件、解析快照和原阶段证据保留。

正常 python-docx 办公包的主题、设置、字体、属性等辅助部件按关系、content-type、根元素及有限结构判读。样式默认值、继承和隐藏文字影响可见性时纳入检查；未知内容、异常关系、循环或缺失的已用样式保持质量缺口。使用的自动编号仍 `NUMBERING_NOT_SUPPORTED` / manual，不宣称完整 Word 视觉等价。

独立审阅发现 `[Content_Types].xml` 与两类 `.rels` 的未知 text/tail/嵌套正文被误标 metadata。修复核对 OPC 根、空声明叶及必要/可选属性，12 个正式回归先真实失败，之后同一批字节独立复验闭合。

|实际命令/阶段|exit|数量与结果|
|---|---:|---|
|作者首批普通文件/有限样式 RED|1|先 1 条普通文件失败，再 13 failed/9 passed；后续危险样式反例另存|
|作者初版目标 + T03/事实/审查关联|0|31 目标；189 关联 passed，0 warnings|
|独立 `probe_docx.py` 初次|1|20 组：8 通过、12 未满足；真实产品缺口，未称全通过|
|`pytest test_docx_office_parts.py::test_structural_package_metadata_rejects_undeclared_content`|1|12 failed，0 errors|
|`pytest tests/integration/test_docx_office_parts.py` 修复后|0|43 passed，0 failed/errors/skipped|
|该目标 + document_parts/upload/parsing/facts/review_flow|0|201 passed，0 warnings|
|独立 `probe_docx_recheck.py`，原 20 份相同字节|0|20/20；12 异常均 FILE_UNSUPPORTED；8 控制输出 hash 不变|
|独立最终正式目标|0|43 passed|

详细命令、JUnit、退出码、输入/输出 hash 在本机忽略目录 `.audit-local/audit-b1-docx-20261005`、`audit-b1-docx-review-repair-20261005/repair-evidence.json` 及 `audit-c1-docx-review-20261005/REVIEW.md`。独立审阅的辅助脚本一次误把命令元数据当结果矩阵，修正后另存日志；该次错误未计产品 RED。

这是 F04 的有限工程修复与独立复验。未运行本轮 Word/WPS 应用兼容或完整视觉验收，OCR、复杂编号、生产与真实法律材料均不在本记录的 PASS 范围。根完整回归另记，不把 201 与历史 1030 或其他切片分母相加。
