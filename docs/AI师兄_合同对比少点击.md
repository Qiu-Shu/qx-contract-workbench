> 2026-11-15 发布接续：本文为隔离界面开发历史记录；本轮已把最终补丁迁入完整 Git 源码。原隔离目录的实际 Git HEAD 为 `9dca82b208072d01f9801baa9e785fb34eaf8213`，原文所称 `d91377a` 是产品复制来源，不是该目录 Git HEAD。正式发布的来源、版本与最终验证以 [0.2.19 发布记录](../harness/docs/2026-11-15-0.2.19发布.md) 为准。

# 合同对比：同一对话，减少点击和输入

2026-11-15，在 `.local/ai-ui-v12`、`codex/ui-v12-first-batch` 继续实现。用户最新要求是“尽量减少用户点击、不另作工作台、减少用户输入”。本记录替代前版中“展开弹窗、独立分析页、重复填写立场、准备草稿后再发送”的设计；双栏文字对照与法律判断分离的要求继续保留。

## 已实现的操作

- 从原件预览点击“对比版本”，沿用当前原稿，只选择另一版本，选齐即自动进行本地文字对比；合同业务入口没有明确原稿时才选择两份文件。不根据附件顺序猜测版本。
- 原稿和修改稿在现有对话或原件预览内并排显示。保留上下文、具体增删、金额/日期期限/违约责任文字筛选与原文定位；移除阅读弹窗、阶段切换和额外分析表单。
- “更换文件”只展开一次，修改两份文件期间保持选择器；返回、重开、同值选择不重复比较。原件变动或失败时保留手动重新对比。切到不同原稿预览时清空旧搭档，只预填当前原件，避免错误配对。
- 一个明确的“AI分析修改影响”动作核对版本并把请求交给原对话发送链。沿用已保存的我方立场；没有保存值时，请求要求先从原对话中沿用用户明确确认的立场，仅缺少时在原对话补问，不推测身份。
- AI 按钮与本地文字结果分区，说明按原对话规则计费。文字比较、打开、返回和筛选均不调用模型；分析判断仍在原对话显示。按钮使用原有发送流程，无新模型接口。
- 准备前后均检查原对话、运行状态、草稿、附件；核验期间改立场、切换对话、换文件或返回均阻止过期操作。后端继续核验案件/材料归属、原件摘要和可读状态。不清除或覆盖已有草稿附件。

## 验证与证据

证据目录：`.evidence/ui-v12-fewer-clicks/`。使用独立虚构材料，未启动真实模型。

- `red-actions.log`：新增单次 AI 动作和无重复立场输入要求，先运行失败，退出 1；实现后目标动作/API 共 9 项通过，退出 0。
- `final-tests.log`：92 项代码回归通过，0 失败、0 跳过，退出 0。包含原输入动作只提交一次、核验期间草稿/附件/会话/立场/运行状态变化保护、未知立场不臆测、自动比较和缓存、跨案隔离、原文版本、文件解析与业务导航。
- Chrome 验证使用真实 Harness 页面、现有解析器和本地后端。文字比较选择即启动、无额外弹窗/分析表单、两次文件替换只展开一次、返回结果复用、稿件附件保留、旧文件拒绝、DOCX/PDF 原件定位、跨案与核验期间改绑均纳入验证。最终目录见本证据目录的 `delivery.json`。
- 最终浏览器输出 `acceptance/1794727442405/report.json`，退出 0、页面异常 0，整个验收场景共 16 次文字比较请求（含更换文件和显式失败重试）。首次选齐仅 1 次，返回/同值选择不增加请求。AI 按钮及计费说明在阅读区底部可见，无需另开页面；截图 `side-by-side-inline.png` 已人工检查。
- 成功 AI 操作在浏览器中替换“提交”桥接器，仅验证一次点击调用真实版本核验接口并交还正确原对话；Node 使用假的原输入动作检查真实桥接器的单次提交行为。实际模型调用、法律输出和计费未验证，不能称完整真实模型验收。
- 独立只读审阅完成：相关回归 56 项通过，最终边界调整后重点复跑 18 项通过；当前源码无阻断问题。核对原发送器发现 `submit()` 返回 void，底层异步提交，故提示使用“分析请求已交给原对话”，不宣称服务端或模型已成功。
- 9 组等效 CSS 尺寸与 1440/768/390 宽度继续验证；它们不是原生 Windows DPI 验收。
- 两个客户端 `node --check` 退出 0；`impeccable detect --json` 检查这两个客户端退出 0、结果 `[]`。Git 空白检查允许 CRLF，退出 0。独立审阅输出保存为 `independent-review.md`。

完整代码回归在 `harness` 目录执行：

```text
node --test --test-isolation=none desktop/integration/contract-compare.test.mjs desktop/integration/contract-compare-api.test.mjs desktop/integration/contract-compare-client.test.mjs desktop/integration/contract-compare-state.test.mjs desktop/integration/contract-compare-actions.test.mjs desktop/integration/contract-compare-scope.test.mjs desktop/integration/business-workflows.test.mjs desktop/business-navigation.test.cjs desktop/integration/knowledge-api.test.mjs desktop/integration/knowledge-runtime.test.mjs tests/contract-compare-fixture.test.cjs plugins/account/test/balance.test.mjs
```

浏览器命令：`python harness/tests/check_contract_compare_ui.py`，设置 `QX_TEST_APP=F:/ai/resources/workbench`、`QX_TEST_PACKAGED=0`、输出到本轮证据目录。Node 复用安装版 runtime；Python 复用主项目 `.venv`，没有安装新依赖。浏览器只放行本地测试服务，模型地址指向不可用的本地端口。

## 当前交付范围

开发版实现与本地专项验证完成；保留前两批证据。补丁包含本隔离分支相对基线的累计改动，摘要与只读应用检查另存 `delivery.json` 和 `patch-sha256.txt`。未修改原源码工作树、F 盘安装版或真实合同，未合并、未发布。

下一步仍是构建候选安装包及安装包业务验收；实际模型法律质量/计费、原生 Windows DPI 保持待验证。缓存与未发送附件保留限于当前页面生命周期，不承诺重启恢复。图片、表格结构与版式仍需核对原件。
