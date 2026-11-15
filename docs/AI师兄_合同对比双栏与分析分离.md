> 2026-11-15 发布接续：本文为隔离界面开发历史记录；本轮已把最终补丁迁入完整 Git 源码。原隔离目录的实际 Git HEAD 为 `9dca82b208072d01f9801baa9e785fb34eaf8213`，原文所称 `d91377a` 是产品复制来源，不是该目录 Git HEAD。正式发布的来源、版本与最终验证以 [0.2.19 发布记录](../harness/docs/2026-11-15-0.2.19发布.md) 为准。

# 合同对比：双栏文字与独立法律分析

后续用户要求已收简流程：不再使用本文记录的阅读弹窗、独立分析页及二次确认发送，改为原对话内自动文字对比与单次 AI 动作。本文保留为前一批历史证据，当前实现见 [合同对比少点击](AI师兄_合同对比少点击.md)。

2026-11-15，继续在 `.local/ai-ui-v12`、`codex/ui-v12-first-batch` 上实施。基线 `d91377a865e94330692715cbb95494725889eee5`，保留上一批修改；不替换 F 盘安装版。

## 本轮要求与实现边界

用户要求原稿与修改稿并排、突出具体变更、可返回原对话，并将文字差异与 AI 法律分析拆成两个阶段。参考图用于阅读布局，不替换现有五业务入口。

- 文字阶段复用现有解析索引、段落/字符差异和原文定位。双栏保留未改文字，显示新增、删除、修改；金额、日期/期限、违约责任相关文字提供筛选和逐处定位。数字及单位保留字符串，不作金额运算或责任判断。
- 两列使用同一个滚动容器，行高自动对齐。展开阅读使用浏览器原生对话框以支持键盘焦点和 Escape；收起和返回原对话均保留已有对比。窄屏按原稿/修改稿顺序堆叠。
- AI 阶段独立显示五项分析问题及我方立场。点击准备后，后端重新核验案件、材料归属、文件摘要、可读状态；原输入框为空且当前对话未切换时才放入请求。用户确认发送后沿用原对话模型流程；本轮不实际调用模型或生成法律结论。
- 保留原文、哈希与跨案保护；不新增上传器、解析库、会话或模型端点。完整对照文字只提供给界面，不绕过现有模型工具的分页限制。

## 验证台账

- 文字引擎新增 3 项失败测试，确认缺少完整阅读行、变更分类后实现；目标引擎/API 14 项通过，退出 0。
- 法律分析准备路由先失败后实现；验证空立场拒绝、过期文件拒绝、独立请求及原件摘要。记录 `red-analysis.log` / `green-analysis.log`。
- 浏览器首先在缺少“原稿”标题时失败；第一轮实际 Chrome 验证通过，包含双栏全文、展开/Escape、明确返回、草稿附件往返、分阶段分析请求、TXT/DOCX/PDF、跨案及材料变更恢复。`acceptance/1794726210414/report.json` 页面异常 0，文字对比请求 10 次。
- 最终 Node 回归 83 项通过，0 失败、0 跳过，退出 0；范围包括对比引擎/API/界面状态、案件隔离、业务导航、知识恢复、余额及源代码/安装版测试夹具。`final-tests.log` 保存完整输出。
- 多处变更浏览器补测通过：5 处变更（新增 1、删除 1、修改 3），金额/日期与期限/违约责任筛选、上下文与双栏行高、逐处定位、两个阶段互斥、核验期间新草稿保护、旧版本分析请求拦截。页面异常 0；文字比较请求 11 次，无返回导致的额外比较。
- 最终浏览器证据：`acceptance/1794726634834/report.json`、`purchase-side-by-side.png`、`legal-analysis-separate.png`；`final-ui.log` 退出 0。实测截图修正了继承业务按钮样式造成的选中态悬停文字对比度问题。
- 两项晚到分析响应测试通过：返回原对话或更换文件后，晚到请求不能写入输入框；跨案及准备期间改绑均被后端拒绝。
- 独立审阅发现 1 项 P2：相同数值的格式变化被错误归入金额/日期。`Final: fixed` — `format-only money and date changes remain highlighted without claiming a changed value` RED→GREEN。格式归一化采用精确十进制字符与指数，不经过浮点金额。
- 另补充 10 万位数字文本的超时失败测试，限制分类候选长度后通过，避免新增文字分类阻塞阅读。`red-bounded-facets.log` / `green-bounded-facets.log`。
- 源码语法检查和 Impeccable 检查通过；Git 空白检查允许 Windows CRLF，退出 0。原源码工作树状态为空，未应用补丁。

## 执行命令与范围

命令均在本隔离副本运行；Node 使用安装版已有的 `F:/ai/resources/workbench/runtime/node.exe`，Python 使用主项目已有 `.venv/Scripts/python.exe`。没有安装依赖。

完整回归在 `harness` 目录执行：

```text
node --test --test-isolation=none desktop/integration/contract-compare.test.mjs desktop/integration/contract-compare-api.test.mjs desktop/integration/contract-compare-client.test.mjs desktop/integration/contract-compare-state.test.mjs desktop/integration/contract-compare-scope.test.mjs desktop/integration/business-workflows.test.mjs desktop/business-navigation.test.cjs desktop/integration/knowledge-api.test.mjs desktop/integration/knowledge-runtime.test.mjs tests/contract-compare-fixture.test.cjs plugins/account/test/balance.test.mjs
```

浏览器在副本根目录执行 `python harness/tests/check_contract_compare_ui.py`，设置 `QX_TEST_APP=F:/ai/resources/workbench`、`QX_TEST_PACKAGED=0`，输出到本轮证据目录。浏览器只放行本地测试服务；模型地址为不可用的本地端口，测试没有发送模型分析消息。9 组等效 CSS 尺寸不是原生 Windows DPI 验收。

## Review Focus

- 分类是文字提示而非法律结论；金额与日期数值不变时不错误标为数值变动。
- 双栏对照能重建两份已提取文档，不能漏掉未改变的上下文，也不能把无法解析当作没有变更。
- 准备 AI 分析期间切换对话、案件、文件、页面或编辑器状态不能覆盖草稿或写入错误对话。
- 完整阅读行不能经 `contract_compare` 工具绕过分页进入模型上下文。
- UI 返回/展开/原文定位不应再次比较、自动发送、调用真实模型或修改原件。

## 独立审阅边界裁决

- Final: Ruling: 实际法律分析质量与计费 — 本轮完成独立请求入口及原会话衔接，实际调用与法律输出质量保持待验证；若误把此项当作已验收，会掩盖错误法律判断或费用问题。
- Final: Ruling: Office/PDF 图片、表格结构与版式提取 — 复用原解析器，只保证已提取文字对照并保留范围提示；若误当成原件全部内容，会漏掉未提取信息。

没有遗留的审阅轻微问题。分类标签是文字检索辅助，大写金额的语义等价改写、特殊金额或日期表达仍需查看全部对照。未修改真实合同、未安装发布、未执行真实模型分析，不能称生产或法律样本验收完成。
