# 案件材料容量：旧回归前提与两道拒绝边界

2026-11-02。本片仅修正一份测试文件，产品源码、预算和法律方法均未改动。20个不同关联用例通过，原失败记录保留；不代表完整回归或内容采用通过。

## 原因与改动

原完整回归中的 `test_oversize_persisted_input_rejects_before_ledger_or_transport_and_rolls_back_message` 定点复现为1失败、exit1。失败在preview调用prepare时发生，尚未执行入队或回滚断言。此前[历史容量实施](contract-history-capacity.md)已明确增加预览的完整封装检查；原测试仍假定预览可以放行超限输入，前提过时。

原8段、每段970次重复的纯虚构材料保持。实测网络请求134359字节，完整保存封装264755字节；两者各自上限262144。网络请求合法并不意味着包含重复manifest及转义wire的保存封装也合法。

测试分成两条：正常后端预览及原审批辅助函数均提前拒绝，未调用保存消息或模型；原失败函数名保留，明确标注内部直接调用边界，使用assemble/build_basis构造输入及真实registry授权，再进入实际enqueue。该内部路径是测试构造，不是正常用户预览流程，也不是一条真实旧批准记录的回放。

入队用例的透明观察器调用真实save_message，看到消息/任务/事件暂增，六表计数从[2,1,3,0,0,0]变成[3,2,4,0,0,0]，input_revision从1到2；随后实际prepare超限抛错。调用者事务内捕获异常，验证六表和完整会话已恢复，外层事务正常结束后再读仍一致，loopback请求为0。没有mock权限或prepare、提高预算、缩小材料、删除原容量/回滚断言。

## 实际验证与独审

| 批次 | 实际结果 | 退出码 |
| --- | --- | --- |
| case-input-original-red | 原单项1失败 | 1 |
| case-input-boundary-probe | 独立边界诊断1通过，另计 | 0 |
| case-input-target-green | 修正后的2项通过，含于下批 | 0 |
| case-input-related | 20通过：修改模块16、prepared精确边界3、合同预览哨兵1 | 0 |

最后一批41.40秒，保留一条既有record_property/xunit2兼容提示。诊断探针及重复目标通过不叠加到20。仅改测试，本片未重复桌面或四开发门，也不挪用前片103、237等历史结果作为本片数量。

Spec与Standards独立核对固定单文件及985份摘要，未发现本片需再修改的问题；两者均未重跑测试。读取命令和退出码按各自报告记录。作者终稿v1曾误称合同哨兵经过HTTP，v2逐行纠正且保留v1；本片实际验证后端预览函数，没有新增HTTP、桌面或真实模型验收。

回滚证据范围为上述六表和完整会话。尚未验证跨进程恢复，也未额外注入调用者事务中的其他待提交写入来证明其保留；不扩大本片结论。

命名检查汇总快照为8条，退出码分布{'0': 7, '1': 1}；这是当时的包装命令数，不含后续收口、独审及直接读取。原始失败日志、探针、旧源码和全部历史封印保留。

## 当前状态与接续

隔离副本 `trademark-regression-repair/律所项目` 的985份执行清单仅一份测试变化；上一片Q113、前片H346证据及N983源码保持。主仓只同步文档，未合入、提交、推送或安装。

原完整回归90073仍运行：2026-11-02T06:38:24.304763+00:00观察3180个结果标记、16个失败，8642只是收集数。已定位的案件容量项按本片处理，原N失败不重写；其他后续失败仍须逐栈归因，不并发第二全套。WIN-PATH-02最终rename间歇错误、超长新建initialize=True及junction仍开放。

商标v5/v6正式内容仍0/4原答、0/8评分，准备文件不重做，工程状态核清后再建正式基线。合同补发待既有确认，不重复询问或重发；伙伴接口待办。没有工作台真实付费模型、微信、QCC、外发或签发。

本机证据目录：`C:/Users/Administrator/.codex/worktrees/trademark-regression-repair/律所项目/.audit-local/case-persisted-input-regression-20261102`。

关键文件：`baseline.json`、`author-review-input.json`、`author-review.diff`、`review/`、`probe-input-boundary-result.json`、四批命令/日志/XML、`author-final-summary-v2.json`、`checks-summary.json`、`spec-final-review.json`、`standards-final-review.json`及`handoff-verification.json`。985份新摘要在`source-snapshot.json`；旧Q/H摘要不覆盖。
