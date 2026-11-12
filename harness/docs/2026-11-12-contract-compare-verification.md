# 合同文字对比验证记录（2026-11-12）

本次为 `2026-11-12-audit-followups.md` Task 3 的工程实现与合成材料验证。实际工作目录为 `C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`，分支 `codex/audit-0216-fixes`；未提交或推送，未改动原 D: 工作区的业务材料。

## 已实现的范围

- 沿用现有附件预览和右侧原件查看器；在当前对话输入区增加“合同对比”。从当前工作区文件夹或已有材料索引中的上传别名选择两份文件，按提取段落对齐、按 Unicode 字符显示增删。`contract_compare` 只读工具复用相同实现，返回分页摘录与来源引用。
- `.txt` / `.md` 使用严格 UTF-8 解码，文件句柄最多读取 800001 字节，超过 800000 字节即给出不可比较提示。Office/PDF 只读取已有解析索引，要求索引的 SHA-256 与当前原件一致；DOCX 要求明确的 `original` 修订视图。未解析、不可读、部分解析和截断结果不会被称为全文相同。
- 来源引用绑定会话、规范化工作区、文件路径、原件 SHA-256、提取段、chunk、offset、页/行及摘录 SHA-256。点击时重新检查权限、文件摘要和来源位置；拒绝旧引用、跨会话/工作区引用、越界路径、符号链接和目录联接。
- 当前工作目录来自已有 `workingDirectory` 服务；持久会话按已有工作目录变更事件解析，操作完成时再次检查工作目录。后台解析的状态、警告和段落在同一 SQLite 只读事务中读取，防止混用不同轮解析。
- PDF 定位只匹配所选原件的完整资源地址和已有渲染器的页节点。新定位会取消旧定位观察器。文本沿用原件查看器的行定位；Word 展示精确来源段与上下文，并打开原件，不编造 Word 页码。
- 重新对比时清除旧结果；等待期间不能使用旧定位按钮。段落 diff 最多 1000ms，整次段落及字符细化共享 1500ms 预算，字符细化每次至多 100ms；预算用尽保留整段增删并提示。字符预算不会随段落数量无限累计。
- “准备批注说明”将带原件摘要的说明放入原输入框，默认另存批注版、保留原件，不发送消息、不自动修改正文。已有草稿或附件时不覆盖输入内容。

## 依赖来源与接口核对

使用仓库锁文件中已有的 `diff@9.0.0`，仅增加直接依赖声明，没有新增安装或另一套 PDF 渲染器。已通过 GitHub 连接器读取上游固定标签的 README 与 LICENSE：

- 官方项目：[kpdecker/jsdiff v9.0.0 README](https://github.com/kpdecker/jsdiff/blob/v9.0.0/README.md)，标签对应 commit `ed13aca03aa25735fafc0645d1185e7a1c68fd8c`。核对 `diffArrays` 的数组比较、`diffChars` 的 Unicode code point 行为，以及 `timeout` / `maxEditLength` 超限返回 `undefined`。
- [固定标签 LICENSE](https://github.com/kpdecker/jsdiff/blob/v9.0.0/LICENSE)：BSD-3-Clause；Git blob SHA `2d48b19fcc2e6269d8903b5716e51333df19f250`。
- 本机复用包 `package.json` 确认为版本 `9.0.0`、许可 `BSD-3-Clause`；该文件 SHA-256 为 `1c625fe9bba43722c8d8fbd8c2b70edcab5473d75f8d66a862f9800b415aa014`。
- 锁文件既有包 integrity：`sha512-svtcdpS8CgJyqAjEQIXdb3OjhFVVYjzGAPO8WGCmRbrml64SPw/jJD4GoE98aR7r25A0XcgrK3F02yw9R/vhQw==`。

已检查现有 `attachment-preview.mjs`、工作区文件服务、会话工作目录服务、右侧资源打开入口、文本与 PDF 预览节点，以及现有材料 store/reader 接口。CodeGraph 使用本仓库 `harness/.codegraph` 查询定位，最终以当前源码和真实工作台烟测核验。

## 失败测试与修复证据

独立审阅提出的边界均已纳入验证：

1. 等待新对比时旧定位仍可操作：真实浏览器先复现旧按钮仍存在；修复为开始对比即清除旧结果，等待结束后按钮恢复可用。
2. 每段字符细化分别计时：改为一次对比共享截止时间，测试预算耗尽后输出原始整段增删并标记未完成字符细化。
3. 会话工作目录变更：API 测试保持 `header.cwd` 不变而切换权威服务的目录；旧引用返回 409，新对比读取新目录的 300 元条款。
4. 多次 PDF 定位：测试第二次定位会取消第一次尚未完成的观察器，并保持精确资源匹配。
5. SQLite 并发解析：真实 WAL 数据库、第二写连接在 metadata 与 chunks 查询之间提交，将两份材料从 ready 改为 partial 并删除不同的第二页。旧代码的新增测试为 **8 通过 / 1 失败**、退出码 1，错误地得到 `equal=true`。加只读事务后，同一测试仍读到完整旧快照的 100/200 元差异，不误判相同。
6. 文件在权限检查后增大：合成文本在 authorize 回调中从 1 字节变成 4000000 字节。旧代码的新增测试为 **9 通过 / 1 失败**、退出码 1，读取后才返回 partial。改为硬上限文件句柄读取后，结果为 unavailable，原件保持不变。

开发烟测还发现并修复了两处验证相关问题：材料表的纳秒 mtime 超出 JS 安全整数，改为只查询实际需要的 sha256/status/warnings；上传文本夹具在 Windows 默认换行转换后多出真实 CRLF 差异，改为固定字节写入夹具，保留产品对原始换行的精确比较。

## 最终命令与结果

以下命令从上述实际工作目录执行，复用 `.local/audit-0216/build/test-env.ps1` 的本机已装运行时与依赖。

```powershell
. 'harness/.local/audit-0216/build/test-env.ps1'
node --test harness/desktop/integration/contract-compare.test.mjs harness/desktop/integration/contract-compare-api.test.mjs harness/desktop/integration/contract-compare-client.test.mjs harness/desktop/integration/attachment-preview.test.mjs harness/desktop/attachment-preview-ui.test.cjs
```

最终结果：**20 测试、20 通过、0 失败、0 跳过，退出码 0**。覆盖中文/emoji/补充平面字符、相同和空文本、纯增删、原件保持不变、旧摘要与伪造摘录、跨会话/工作区、越界与目录联接、不可读及未解析文件、解析页码和 partial 状态、真实 SQLite 交错提交、增长文件硬上限、现有附件预览回归、HTTP/tool 和原件定位。

```powershell
. 'harness/.local/audit-0216/build/test-env.ps1'
$env:PYTHONIOENCODING='utf-8'
& $env:QX_TEST_PYTHON harness/tests/check_contract_compare_ui.py
```

最终真实 Harness + Chrome 浏览器烟测：**退出码 0**。使用独立临时工作区、七份合成原件，调用现有 DOCX/PDF 解析器，无真实模型请求；模型地址禁用，浏览器外部网络被阻断，余额接口仅做 UI mock。最终证据目录：

`harness/.local/audit-contract-compare/1794467240177/`

`report.json` 实际结果：

```json
{
  "pendingComparisonCannotUseOldLocation": true,
  "textComparisonAndOriginalNavigation": true,
  "draftPreservedWithoutSending": true,
  "indexedUploadSelectable": true,
  "docxOriginalParserComparison": true,
  "pdfOriginalPage2": true,
  "staleCitationRejected": true,
  "widths": [1440, 768, 390],
  "otherFiveOriginalsUnchanged": true,
  "uploadedOriginalUnchanged": true,
  "pageErrors": []
}
```

`comparison-1440.png`、`comparison-768.png`、`comparison-390.png` 为界面证据；各宽度检查对比区无横向溢出，人工检查 390px 截图可读。`desktop.png` 为原文字段核验，`pdf-page-2.png` 为正确原件第 2 页定位。用于陈旧引用测试的一个文本文件由测试主动改写；其余六份原件前后 SHA-256 一致。烟测结束关闭独立宿主进程。

开发烟测脚本存放于 `harness/tests/`，宿主脚本为 `contract-compare-smoke.cjs`，浏览器脚本为 `check_contract_compare_ui.py`。迁移后从上述新路径重新完成全部烟测，避免 `desktop/integration` 的运行包 overlay 将开发脚本带入产品。三个新增运行模块的 `node --check` 与 `git diff --check` 均退出 0。

## 适用边界

这是只读文字差异与来源核验功能，不构成法律审查结论或生产试点验收。Office/PDF 需要先由现有材料工具解析；扫描件、复杂表格、图像、版式以及修订显示仍需人工对照原件。Word 页码随排版变化，当前只提供原件打开及精确提取段的上下文，未实现 Word 版式坐标跳转。比较上限为 200000 个 JS 字符单位和 4000 个提取段，超出明确显示部分结果；所有“相同”表述均指已比较文字。

引用在点击时核验，原件查看器随后仍读取原文件，不创建原件的冻结副本。依赖、UI、解析器和服务的当前连接已由上述合成烟测确认；未运行真实案件、在线法律检索、付费服务或 live 模型。全仓库集成测试与最终提交由主任务统一处理。
