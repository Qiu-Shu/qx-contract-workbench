# 持久合同任务 A＋B GitHub 同步回执

日期：2026-10-24。产品源码与合成验收证据提交 [`0178859b19457ff67543af66bb20c1863148b404`](https://github.com/Qiu-Shu/qx-contract-workbench/commit/0178859b19457ff67543af66bb20c1863148b404) 已同步至 `codex/contract-review-v2`。远端为 `https://github.com/Qiu-Shu/qx-contract-workbench.git`。

| 核验项 | 实际结果 | 本机原始回执 |
| --- | --- | --- |
| 提交身份 | 本地与远端均为 `0178859b19457ff67543af66bb20c1863148b404` | `.local/task-drafts-20261024/github-ab/remote-product.json` |
| 文件树 | 本地与远端 tree 均为 `a2693e8e65ef471d561968a2a279c4f1252fe92d`；递归 4,992 个受控条目完全一致 | 同上，`equal=true` |
| 提交范围扫描 | 59 个提交文件、1,074,034 字节；禁止路径 0、已知密钥模式命中 0 | `.local/task-drafts-20261024/github-ab/scan.json` |
| 产品验证字节 | 33 份产品文件摘要匹配实际验证快照 | 同上，`product_snapshot_matches=33` |
| 暂存字节 | 59 份文件均在换行规范化后相同，其中 58 份原始字节相同 | `.local/task-drafts-20261024/github-ab/staged-check.json` |

已知模式扫描不能证明不存在全部敏感内容。本次同步范围为源码、文档及经检查的合成证据；临时数据库、截图、原始终端日志和崩溃转储保留本机。上述回执文件位于本机 `.local`，未纳入产品提交。

本回执核验的是指定产品提交；回执本身及导航更新由随后独立文档提交保存，不把后续文档提交的 SHA 或条目数量混入上述产品记录。未重复运行 A＋B 测试，实际测试及其范围见[验收记录](README.md)。

源码同步不代表安装版更新。Windows 长进程原生崩溃根因仍未定位，见[诊断记录](native-crash.md)；真实微信、真实合同模型、安装包及生产验收继续保持各自未完成或 NOT_RUN 状态。
