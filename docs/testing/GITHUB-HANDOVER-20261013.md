# GitHub 上传与交接核验

日期：2026-10-13（Asia/Shanghai）。范围：接手现有项目、续传私有仓库、生成项目说明及交接文档。业务基线 `6c4a1ad15d3d84431acf15d1fc8efe411fe00c0e`；本次未修改业务源码、数据库或运行权限。

## 实际结果

|检查或命令|退出码|实际结果|
|---|---:|---|
|`gh repo view Qiu-Shu/qx-contract-workbench --json nameWithOwner,isPrivate,defaultBranchRef,description,url`|0|仓库存在，`isPrivate=true`，默认分支 `codex/contract-review-v2`|
|初始 `git ls-remote origin refs/heads/codex/contract-review-v2`|0|远端 `293f133e297286340f2b82f755760f6852644e73`，本地 43 提交、领先 14|
|`git -c http.version=HTTP/1.1 -c http.postBuffer=52428800 push origin HEAD:refs/heads/codex/contract-review-v2`|0|远端从 `293f133` 更新至 `6c4a1ad`，43 个业务历史提交完整续传；非 force push|
|完整可达历史对象路径及模式扫描|0|43 提交、1758 唯一 blob、37,335,926 bytes；0 禁止路径命中，0 未解释的秘密模式命中；27 处为既有独立虚构 localhost 拒绝测试 URL|
|`git check-ignore` 指定本机资料目录|0|`.local/workbench`、私密审查所在 `.audit-local`、`.env`、`.codegraph`、`.venv` 均被忽略；隔离原包规则另在 `.gitignore`|
|目标测试，完整命令见下|0|159 passed，15.40 秒；JUnit 159 项、0 失败、0 错误、0 跳过|
|`.venv/Scripts/python.exe -X utf8 src/cn_contract/mcp/bound_entry.py --check`|0|`BOUND_ENTRY_VERIFIED`，当前源入口绑定通过|
|`.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py --mode development`|0|13 个来源检查通过，13 条未生产批准警告保留|

测试命令：

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/integration/test_local_workbench.py tests/security/test_auth.py tests/security/test_secrets.py tests/unit/test_mcp_bound_entry.py tests/unit/test_sources.py -q --junitxml=.audit-local/github-upload-20261013/targeted.xml
```

可随仓库读取的实际 JUnit：[targeted.xml](github-handover-20261013/targeted.xml)。本机扫描收据位于忽略目录 `.audit-local/github-upload-20261013/history-scan.json`；保留前次上传收据，不覆盖历史。

本次文档提交包含 [PROJECT_OVERVIEW](../PROJECT_OVERVIEW.md)、[HANDOVER](../HANDOVER.md)、README 接手入口、TASK_STATUS 增量、原有未提交的真实使用差距记录及本核验材料。文档提交后的最终远端 SHA、私有属性、文件清单与本机 HEAD 比对另保存在本机上传收据中；查看仓库最新提交可确定文档版本。

## 验证限度

扫描覆盖 Git 可达 blob 及 ZIP 中 XML/文本成员；它是路径与已知秘密模式检查，不是全面敏感信息分类认证。源测试和本机账户测试通过不能证明真实合同已准入、法律准确性或生产可用。

本轮没有重跑完整业务回归、真实 OCR、浏览器或 Word。1695 项全套结果保持 2026-10-11 的历史日期，115 项密码验证保持 2026-10-12 的历史日期。本轮 159 项与历史测试有重叠，不累计。真实模型、QCC、材料外发、正式签发和生产批准均保持原状态。
