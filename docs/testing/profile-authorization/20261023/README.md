# CH-07C2b2b-A：档案用途许可内核

基线 `60eb041536dc36dfd4133f0d09b909681146500c`。2026-10-23 Windows本机源码与合成回环验证。

CH-07C2b2b-A完成档案用途许可内核：完整保存计划绑定许可，普通聊天/资料回答/档案用途互相隔离，发送前后检查到期、撤权及配置变化，晚到候选丢弃而保留已收到用量。一次13文件379项关联通过（新增文件58项已包含），四开发门通过，546份工作区输入稳定。只修改现有registry，应用自动归档仍关闭；持久调用消费、费用和原子保存/历史恢复继续接线。

## 实现与验证

复用既有MainModelRegistry的登录会话、许可身份、配置失效机制及profile_preparation/供应商接口。新许可绑定完整basis摘要，要求单次上限和明确档案接口；检查实际提交与prepared内全部保存计划及当前出站字节。普通、上下文、多轮入口显式拒绝档案许可；档案也不接受旧用途许可。传输预检及返回后再次核验，已收到的usage/request id不会因迟到撤权而丢失。无新DTO、schema、依赖或额外模型调用。

- [实施合同](../../../plans/2026-10-23-profile-authorization.md)、[计划复核](plan-review.md)。
- 最终一次13文件 **379 passed，0失败/错误/跳过**，新增文件58已包含，测试身份无重复。[日志](target.log)、[JUnit](target.xml)、[命令/退出码/输入摘要](target-verification.json)。wrapper耗时133.937秒。
- schema、默认配置、来源、运行依赖四开发门均exit0；全部546份输入前后稳定。具体命令/时长见verification及gate日志。
- 开发RED/GREEN与首轮开发结果见[开发记录](development-report.md)，仅最终关联运行作为当前通过数量；独立复核见[双轴报告](review-summary.md)，探针不与主回归累加。

## 仍未完成

registry不读数据库、不消耗持久调用次数、不预留费用也不写档案。max_calls=1只约束许可形状，不等于本片已具备一次性claim或供应商收费上限。调用方仍须使用C2b2a核对当前权限/版本，并在同一执行链中完成登记、claim、费用、固定事件原子保存和语义历史/恢复后才能激活。

native、HTTP、runner、attempts和新格式封闭检查均未开放；本次不是桌面窗口、冻结后端、安装器或真实模型验收。安装版仍0.4.1；WIN-PATH-02恢复目录偶发WinError5仍开放。WorkBuddy本次native_unavailable未派发，使用子智能体复核；真实资料、法库和云端未操作。
