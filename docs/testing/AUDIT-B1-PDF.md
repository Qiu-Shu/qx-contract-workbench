# B1b / F05：PDF 可见性疑点与事实来源资格

2026-10-05，独立虚构数据，复用当前 PDF 解析与后端事实、计算、审查入口。没有新增运行依赖或 OCR。

文字层锚点保留，但白字、透明、遮盖、边界、裁剪及未支持绘制效果等疑点页标为 manual。后端重新核对当前原件和可信解析；未核对来源不能确认、更正为确定事实、参与计算/付款基数、进入审查引用或补丁。拒绝该事实仍可操作。安全页的明确事实可继续使用，全局完整审查仍为 false。

|实际执行|exit|结果|
|---|---:|---|
|作者首轮目标 RED|1|14 failed / 11 passed；之后背景/粗线遮盖再 2 failed|
|作者初版目标及关联|0|27 目标、210 关联 passed，0 warnings|
|独立首轮文字/渲染反例|1|18 份中 15 分流正确、3 漏标；三处均经实际后端确认/计算/审查/草案复现|
|修复新增正式测试 RED|1|23 条中 18 failed / 5 passed，0 errors；3 个真实 DB 反例可错误消费来源|
|修复后目标 / 关联|0|50 / 233 passed，0 warnings|
|独立修复目标|0|50 passed，0 failures/errors/skipped|
|独立相同字节及新增控制输入|0|24 PDF / 24 渲染 / 24 分流一致；原 18 输入和渲染 hash 不变|
|独立后端案例|0|7/7；三处原反例确认/更正均 SOURCE_VISUAL_CONFIRMATION_REQUIRED；拒绝后 0 eligible/citation/findings，18 insufficient|
|独立来源/历史入口|0|4 组伪造、权限、历史 read/export/patch 阻断；ExportRow/Record 无半写|

三处修复为：使用未实现的 ExtGState 绘制属性转人工；曲线描边不尝试不完整几何判断；按文字当前填充/描边模式检查实际颜色与背景。普通填充文字、先白底、直线边框及高对比描边仍可读。上述转人工具有保守性，不能称任意 PDF 的全面视觉等价。

详细命令、JUnit、输入/渲染/原件 hash 在 `.audit-local/audit-b1-pdf-20261005`、`audit-b1-pdf-review-repair-20261005`、`audit-pdf-review-20261005` 和 `audit-pdf-review-repair-20261005/repair-review.md`。原开放问题及失败证据未覆盖，7 份摄取原件最终读取 hash 不变，独审源码/test/schema 前后零漂移。

未运行本阶段全套、OCR、原页确认界面、真实法律材料、供应商、宿主或生产。根完整回归另记，各分母不相加。
