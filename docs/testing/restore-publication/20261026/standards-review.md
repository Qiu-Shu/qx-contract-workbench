# Standards 复核

基线 498c0c978ee58f2856d741a2e62e9025bcbee73f；审阅 git diff --cached 498c0c9。依据 AGENTS.md、CONTRIBUTING.md 及所提供 smell baseline。

硬性违规 0；有害 smell 0。归档探针未进入产品或默认测试；新目录守卫、猴补丁 finally 恢复、只读 PID/RM 查询与隔离子进程校准均符合本轮边界。独立实验保留差异比强行抽象更利于定位。

核对本机 JUnit 为 1/74/76，按用例 ID 去重 76；六组原路径恢复 136 次（131 成功、5 失败），立即重试实验 80 返回成功且 1 首次失败，合计 6 首次自然失败。九份 JSON 与原实验语义一致；九对脚本原本/随仓 SHA 及 644 输入 SHA 全匹配；AGENTS 原 SHA 未变。文档保留 OPEN、未运行项及原生 AV 独立状态，未夸称修复。

未重新执行循环或系统 API；本复核不证明失败瞬间无占用，也不定位根因。
