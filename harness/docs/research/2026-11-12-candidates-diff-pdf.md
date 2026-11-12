# jsdiff 与 PDF.js 加入条件核验

核验日期：2026-11-12（Asia/Shanghai）；实际工作树 `C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`，基线 `5e01b065`。本轮没有构建安装包、安装依赖或修改产品；复用现有源码与已解包程序资源，仅读取固定依赖并在独立目录运行合成测试。

**结论：jsdiff 9.0.0 已正确接入，应保留；PDF.js 6.3.289 已内置在 Harness 预览器中，应复用，不再引入第二份依赖。** 上游 PDF.js 当前稳定版更新不等于本项目自动升级通过。OCR 精确框叠加、裁切/旋转坐标对齐仍是额外待验范围。

## jsdiff：现有直接依赖符合当前用途

官方 [v9.0.0 tag](https://api.github.com/repos/kpdecker/jsdiff/git/ref/tags/v9.0.0) 指向 `ed13aca03aa25735fafc0645d1185e7a1c68fd8c`。本轮重新读取该版本的 [package.json](https://github.com/kpdecker/jsdiff/blob/ed13aca03aa25735fafc0645d1185e7a1c68fd8c/package.json) 和 [LICENSE](https://github.com/kpdecker/jsdiff/blob/ed13aca03aa25735fafc0645d1185e7a1c68fd8c/LICENSE)：BSD-3-Clause，无运行时依赖声明。默认分支 package.json 当时也为 9.0.0；不以其替代固定 tag。仓库 `releases/latest` 请求为 404，不能据此断言没有版本，实际 tag 与包版本已成功核验。

现有 `harness/package.json` 已明确直接声明 `diff: 9.0.0`，包内版本一致；LICENSE 与固定上游全文归一化比对一致。它用于已授权材料的段落/Unicode 字符比较，现有实现限制读取大小、总比较时限及字符细化时限，不自动应用模糊 patch 或改原件。法律影响、Word 样式和复杂表格完整差异不属于该能力的承诺。当前用途与投入明确，无需引入另一个比较框架。

## PDF.js：候选其实已在现有渲染器内

源码工作区的 pnpm 顶层锁未出现独立 PDF.js 条目，不能据此断定产品没有它。实际 `@deepseek-ai/dsh-client-ui-sidebar-documentpreview@0.2.2-alpha.2` 的 package.json 声明构建依赖 `pdfjs-dist: 6.3.289`；其发行 `lib/client.pdf.js` 已内联 PDF.js，包含同版 `apiVersion`、页渲染、文本层及 `data-pdf-page` 节点。文件为 **7,108,803 字节**，SHA-256 `ba16081d7a3d9bb41a0a10eb9b9789b9891c40738d7428a2e06ebfbac0eb542c`，不是本轮新下载或新加入的体积。

该固定版 [v6.3.289 tag](https://api.github.com/repos/mozilla/pdf.js/git/ref/tags/v6.3.289) 指向 `1c8020a7d4e43668ac287a3ecf9a8dbea17e4c56`；[Apache-2.0 LICENSE](https://github.com/mozilla/pdf.js/blob/1c8020a7d4e43668ac287a3ecf9a8dbea17e4c56/LICENSE) blob 为 `f433b1a53f5b830a205fd2df78e2b34974656c7b`。现有 bundle 开头保留许可与第三方 notices，本轮将其中完整 Apache 文本与上游全文归一化比对通过。这不替代所有嵌入字体/解码器的完整再分发审计。

本项目引用导航已沿现有 `sidebarRight.openResource` 打开原件，在后端核验会话、工作区、原件 hash 和引用后，匹配同一完整资源 URL 的页节点跳页。渲染器会创建可选文字层和固定比例 viewport；当前适配没有公开页码导航 API，所以使用受控页节点定位。CodeGraph 定位源码 `desktop/integration/contract-compare-client.js` 与 `attachment-preview.mjs`，包内供应商构建文件另外按实际字节核对。

本轮读取官方 [latest Release](https://github.com/mozilla/pdf.js/releases/tag/v6.5.438)，观察到 6.5.438，发布于 2026-11-01。该版本官方 zip 约 6.54 MB，[package.json](https://github.com/mozilla/pdf.js/blob/v6.5.438/package.json) 声明 Node `>=22.22.3 || >=24.15.0 || >=26.0`。这些只是上游元数据，**没有下载、执行、升级或构建它**，不把现有渲染器成功当作 6.5.438 兼容性证明。若未来需要更新，应连同 Harness 适配、worker/解码资源和许可 notices 整体核验，不能只替换版本号。

## 本轮实测

证据根：`D:/CodexChecks/AI-Shixiong-candidate-admission-20261112`；复用现有候选的 `resources/workbench` 仅作为只读依赖，测试写入新的独立工作区。没有重新构建或启动正式安装。

| 命令/检查 | 实际结果与证据 |
| --- | --- |
| `node --test` 五个现有合同对比/预览文件 | **20/20，exit 0**；`logs/diff-preview-tests.log`。包括 Unicode、预算、来源版本、越界路径、解析状态、真实 SQLite 交错提交和增长文件限额 |
| `python harness/tests/check_contract_compare_ui.py`，`QX_TEST_PACKAGED=1` | **exit 0，页面错误 0**；`preview-ui/1794470849682/report.json`。真实现有渲染器显示 PDF 第 2 页，DOCX 对比、上传、旧引用拒绝、草稿保留和 1440/768/390 宽度通过，原件保持 |
| [只读来源探针](../../experiments/candidate-admission/verify-existing-diff-pdf.cjs) | **exit 0**；`diff-pdf-provenance-v2.json`。核对已用版本、两份许可、PDF 内联标记与页/文本层节点；它不是渲染执行测试。初次结果保留为 `diff-pdf-provenance.json`；复核仅将“本探针未安装新版”的字段改得更明确，没有扩展检查范围 |

五个 Node 测试文件是 `desktop/integration/contract-compare.test.mjs`、`contract-compare-api.test.mjs`、`contract-compare-client.test.mjs`、`attachment-preview.test.mjs` 以及 `desktop/attachment-preview-ui.test.cjs`。实际运行使用已有 `.local/audit-0216/build/test-env.ps1` 的依赖，Chrome 对 localhost 以外请求阻断；无模型请求。

可复跑来源探针（输出文件须使用新名称）：

```powershell
node harness/experiments/candidate-admission/verify-existing-diff-pdf.cjs `
  'C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目/harness' `
  'D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/candidate-final-extracted/application/resources/workbench' `
  'D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/pdf-diff-upstream.json' `
  'D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/diff-pdf-provenance-v2.json'
```

上游原始读取文本与 URL/blob 存在 `pdf-diff-upstream.json`。本轮不是全面漏洞扫描、全格式/字体/恶意 PDF 审计，也未验证 OCR 框随缩放、旋转和裁切后的精确定位；这些限制不能用已有跳页成功掩盖。
