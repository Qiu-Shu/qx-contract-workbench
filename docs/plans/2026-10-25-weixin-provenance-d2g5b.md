# D2g5b 消息代际来源与存档完整性 Implementation Plan

> **For agentic workers:** 已授权无人值守实施与常规推送；TDD逐项验证，独立代理仅写自己测试/fixture。实际workspace为D:/Documents/ChatGPT/律所项目，用户AGENTS不纳入提交。

**Goal:** 持久记录首次接受消息当时的非零代目标，使未来代际poll来源可独立校验、备份和恢复；本片仍不开运行。

**Architecture:** schema18只追加weixin_descriptor_generations及不可变触发器。现有descriptor/poll/generation行不改；只非零代accepted original有sidecar，零代从原mapping/grant推导。纯历史解析按poll因果位置选当时generation，完整存档校验而非当前latest重定向。旧原始数据与32旧指纹不改，新增冻结34前驱（含17版两种native形态）。

**Tech Stack:** 现有Python/Pydantic/SQLite/SQLAlchemy/pytest与两类备份，无依赖/HTTP/UI变化。

**Spec:** sources/specification-v2.0.md与D2f—D2g5a的当前权限、不可变历史、合成数据和暂停guard约束。当前用户持续实施授权优先，不重复访谈。

## 接口和不变量

- schema CURRENT_VERSION=`weixin-target-provenance-v1`；原weixin-generations-v1成为完整第17前驱。新增表7字段，descriptor_id为PK/FK，generation_id和task_binding_id为FK；update/delete不可变。
- domain.py集中新增冻结WeixinDescriptorGeneration：descriptor_id、generation_id、generation_sha256、task_binding_id、scope_sha256、payload_sha256、provenance_sha256；最后摘要覆盖其余六字段。不复制正文、scope、时间、account或peer，通过已存在不可变父记录校验。
- provenance_integrity._targets(db)只返回非零accepted descriptor对应历史generation。校descriptor原始状态、poll/account/root/peer关系、generation在poll之前且checkpoint严格属于此前缀、当时最新generation、sidecar摘要/目标binding/scope摘要/载荷摘要。额外、缺失、blocked、duplicate、零代sidecar均拒绝。
- 公共validate_descriptor_generations(db,allow_provenance=False)返回无文件引用；非空来源仅完整native备份可接受。ops.backup._file_references注册，两种恢复保持现inbox/dispatch/generation隔离位false，不增加启用许可。
- 新v18的generation校验允许后代poll，generation.checkpoint须对应完整poll前缀；旧v17规则原样保持。时间使用解析UTC，不靠字符串排序。后代grant/dispatch仍拒绝；原_account/_has_generations/ingress/dispatch运行guard不动。
- inbox用持久来源决定scope，已知accepted reply跨目标拒绝；source_event_id保持账号/peer/message全局命名。旧消息、blocked和duplicate不会通过新sidecar改派或复活。
- 所有旧attachment/model/judge/library/profile/task/inbox/dispatch/grant/generation版本gate接入18，防止新版本提前return[]而漏检旧记录。generations._schema同时接受17/18，原schema对象严格识别，不静默修补。

## 本片范围

只支持存档语义和独立SQL合成样本证明，不提供公开后代poll/dispatch写API，不解除暂停。未来真实合成接收必须在一个事务持久保存descriptor/sidecar/checkpoint；预览不能充当授权令牌。下一片才接公开接收，分发需要另做旧任务/跨代来源边界。

## 文件与步骤

产品：domain.py，新增provenance_schema.py/provenance_integrity.py；storage_schema/schema_migrations/storage_bootstrap、ops/backup和旧family版本gate；inbox/generation/dispatch完整性与generations._schema。测试：独立schema/34冻结fixture，主DTO/来源完整性/备份与独立合成seed。历史schema测试仅在实跑暴露“当前版本=17”预期后调整到当前tip，保留其旧family/前驱/故障验证，不改旧冻结fixture。

- [x] 编写集中DTO、正向非零来源/缺失/错配/跨代reply等失败测试；独立schema先RED。
- [x] 最小schema/版本gate/纯历史来源校验；先GREEN后运行关联旧完整性/升级/备份回归。
- [x] 独立冻结复核并根复验；正向两代真实qxbak、cnbak拒绝、恢复隔离、旧运行仍拒绝；未跑标NOT_RUN。
- [ ] 记录命令/退出码/去重数量/散列与失败分类，更新状态，扫描授权文本，fetch后正常commit/push核SHA/tree；不提交用户AGENTS或.local。
- [x] 上轮本聊天HumanLayer pending已于2026-10-25T08:41:13Z回读恢复。本轮推送后按AGENTS三端收尾，具体成功以最终回执为准；超时保留待同步，不唤醒其他聊天/不恢复五分钟任务。

## Review Focus

重算摘要也不能改变目标因果边界；空poll/其他peer消息也参与账号checkpoint前缀；同一UTC刻度不同文本表示不可绕过比较；恢复只读与旧消息归属不可借schema升级绕过；直接单family校验及完整备份都不能漏查新旧来源。测试里的SQL seed仅构造独立存储样本，不能称产品运行入口已可用。

实测见[阶段证据](../testing/weixin-provenance/20261025/README.md)：33模块1094不同Python，1093PASS/1基线长路径FAIL，142新增全PASS；233 Node与四门exit0。本片来源存档验收通过，旧长路径SQLite失败经冻结9c04b4d单例复现，作为独立OPEN保留；既有WinError5/WIN-PATH-02与原生崩溃不关闭。下一片为按代际原子接收/分发，真实账号模型仍关闭。
