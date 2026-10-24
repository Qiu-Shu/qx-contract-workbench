# D2b 原子合成收件：GitHub 同步回执

2026-10-24，`codex/contract-review-v2`，远端 `https://github.com/Qiu-Shu/qx-contract-workbench.git`。本轮依用户无人值守/逐轮推送授权，获取远端后正常快进提交和推送，无强推、空提交或可见性变更。

产品提交 [`f161660343d43734a35863cc782f175b36650769`](https://github.com/Qiu-Shu/qx-contract-workbench/commit/f161660343d43734a35863cc782f175b36650769) 已核验：

| 核验 | 实际结果 |
| --- | --- |
| 本地 / ls-remote / fetch 后提交 | 同为 `f161660343d43734a35863cc782f175b36650769` |
| 本地 / 远端 tree | `28bae9d97388277bb4a3823fac7bc01d15f1726a` |
| 递归受控条目 | 5,029 项逐字一致，ahead/behind 0/0 |
| 提交扫描 | 12 文件、448,329 字节；禁止路径和已知密钥模式均 0，368 个本地文档链接有效 |
| 验证绑定 | 3 份关键产品摘要与最终实测/独审冻结摘要一致，暂存文件换行规范化后均与实查字节一致 |
| 已有用户改动 | AGENTS.md 保留未提交，未覆盖或混入本片 |

本机回执为 `.local/weixin-ingress-20261024/github/{scan,remote-product}.json`；临时库、完整日志和本机同步文件未上传。有限模式扫描不能证明不存在所有敏感内容。

[实测](README.md)：9 文件、444 个不同相关 Python 用例通过，0失败/错误/跳过、1条有意伪造输入序列化warning，四开发门 exit0。实际 public 合成服务通过故障回滚、commit后丢回执查询恢复、双Session竞争、新进程找回及真实qxbak恢复隔离；独立冻结复核无遗留可证实发现。产品仍无真实微信认证/transport/轮询、TaskDraft分发、下载解密、发送或模型调用。

下一片 D2c 安全分发 accepted_pending_dispatch 至共享任务，并持久保存分发回执/恢复；过期映射刷新当前明确阻断。真实微信/模型、E有限期许可、安装包和生产验收仍 NOT_RUN。安装版 0.4.1、原生长进程崩溃、WIN-PATH-02 保持开放。

本同步回执及三份导航随后独立提交，新增条目和该文档提交 SHA 不混入以上产品记录。沿用既有开发heartbeat，HumanLayer五分钟轮询保持暂停，工程摘要按轮自行同步。
