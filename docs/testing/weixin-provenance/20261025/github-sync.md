# D2g5b GitHub 产品同步回执

- 分支`codex/contract-review-v2`，产品与合成证据：[提交](https://github.com/Qiu-Shu/qx-contract-workbench/commit/0738989f0a3da287e0a80f37fab7db4a73e1f32d) `0738989f0a3da287e0a80f37fab7db4a73e1f32d`。
- 本地HEAD、ls-remote、正常fetch后的FETCH_HEAD及tracking SHA一致，ahead/behind=0/0。
- 本地/远端tree均`f69dcad5ef4c693ab9185e4057c6c33261e6bbec`；递归`ls-tree -r --full-tree`的5,385条目逐字节一致，SHA256 `b078aeb01db2643d39e35a3d0d91425d0f2dffa43bb85feb71f324a0d6a07bc6`。
- UTC核验`2026-10-25T09:42:44.510517+00:00`。正常提交/推送，不强推或空提交。用户AGENTS.md改动未暂存/提交，哈希保持不变。
- 发布前109个授权文本文件已扫描：已知密钥0、禁止路径0、失效链接0，444个相对链接有效，28个Python文件内存编译通过；数据库/qxbak/zip/私有临时目录均未入Git。
- [实测](README.md)：33模块1094不同Python=1093PASS/1基线长路径FAIL，142新增全部PASS；233 Node及四开发门exit0，同一独立审查者两轴确认本片0遗留，但完整回归不是全绿。
- 基线9c04b4d同一旧测试复现二次备份SQLite长路径打开失败，[归因](baseline-attribution.json)保持OPEN；与既有WinError5/WIN-PATH-02和原生崩溃分别保留。本片不恢复按代际运行，不更新安装版或连接真实微信/模型。
- [换行核验](git-normalization.json)：仅JSON fixture由工作区CRLF规范存储为Git LF，JSON/34前驱内容相同；验证SHA描述实际工作区输入，其余授权字节均匹配。

本文件和状态同步为随后独立文档回执提交，不能把文档提交SHA冒充产品SHA。文档推送后再次核完整远端SHA/tree，最终核验保存于本机并纳入本轮脱敏摘要。
