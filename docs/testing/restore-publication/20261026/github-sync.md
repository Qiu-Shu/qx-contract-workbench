# 自然恢复失败诊断：GitHub 同步

2026-10-26，证据提交 `a02049e7bc98fdf6674594ec4941e97677fffef9` 普通推送到 `origin/codex/contract-review-v2`，push退出0。此提交仅含诊断材料和状态文档，不是产品修复。

随后fetch、ls-remote与HEAD一致，ahead/behind为0/0；树 `797c47dcca7efb7af9006f625d1a8ba3c4b0c97d`，6133条递归条目逐字节一致，列表SHA256 `09f4180b120ddeb60f3cab0129aff3d7359376f93d777e2764d09835243d5259`。`origin/dhb_law`仍为`afb6ab64f81d0167efb309e7f28998e31725450d`。

用户原AGENTS.md仍为唯一未提交项、未暂存，SHA256 `e0fcf27d3a2b5aca6c09d5372c869a312dfc6dba558dcb67581ef9f5ffbe755f`不变。提交前644输入SHA一致，产品零改动；常见凭据模式扫描无命中，未上传临时归档、运行数据库或真实材料。

机器记录见[evidence-sync.json](evidence-sync.json)。本回执随后单独普通提交推送，并再核fetch/ls-remote/递归树；最终HEAD保存在本机 `.audit-local/win-path-02-20261026/final-sync.json`，避免文档自引用提交SHA。WIN-PATH-02及原生AV均保持OPEN，安装版仍0.4.1。
