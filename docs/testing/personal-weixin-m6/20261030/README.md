# 本人微信 M6 最终修复与前端整合

源码基线 `cb39e3c178f987b81840ab2a53a2ecd9d9ba55f6`，修复提交 `e8e317f9abedbc33df3c58db1c1c66e40bd6b350`。用户指定采用的同伴温情工作台及双视图保持不变；[前端合并验收](../../frontend-integration/20261030/README.md)单独记录。

## 四项修复

1. 明确表示“还有附件，稍等”后，通过现有 TaskDraft 暂停状态保存等待意图；后续材料继续归集，重新连接和选择主合同不会擅自开始。明确继续或桌面恢复后再执行。识别只针对有界用户消息，不读取附件内容作为指令。
2. 个人微信任务开放现有主合同选择、暂停/继续和同绑定待分配材料归属操作，后端仍核对登录、权限及版本。草稿中的选择保留，原件与来源不改写，不开放合成执行按钮。
3. 暂停任务纳入同一任务恢复；多个可能对象时保持待分配并澄清，不按最近时间猜测。原合成任务暂停后的编辑限制保持不变。
4. 排队的传输在线程真正开始调用前重新核对登录、到期、授权、绑定、恢复状态和连接代际。失效时不发送，关闭被捕获的旧连接；未知发送记录不重试，也不关闭新连接。网络等待不占数据库写事务。

命名主合同的自然语言解释仍不支持，桌面选择提供实际可完成的恢复路径。既有内部非合成冻结行为保持兼容，manifest 仍为 `synthetic=false`，mock bridge 继续拒绝；没有额外任务数据库、模型识别调用或静默计时器。

## 实际验证

使用项目 Python 3.12.14、`PYTHONUTF8=1`、独立虚构材料和短 D 盘临时目录。HTTP 为 MockTransport，模型为进程内测试 provider；以下没有真实微信或模型请求。

| 检查 | 实际结果 | 源码时点及证据 |
| --- | --- | --- |
| 运行时、TaskDraft、PDF、bridge、generation guards、reauthorization 六文件回归 | exit 0，159 passed，304.30秒 | 第一轮绿色源码；运行进程导入后才把暂停编辑收窄至个人任务并扩展歧义夹具。不能称最终全部源码回归。[原始输出](fix-regression-python.log) |
| 最终运行时专项 `explicit_hold or desktop_main_selection or ambiguous_paused or queued_reply` | exit 0，15 passed / 47 deselected，66.96秒 | 最终产品源码；5种等待、同会话主合同完成、2种歧义及7种排队撤权。[原始输出](fix-final-python.log) |
| 最终 `synthetic_paused` 专项 | exit 0，2 passed / 62 deselected，4.45秒 | 最终源码；合成暂停任务编辑和分配仍拒绝，原记录保持。[原始输出](fix-final-synthetic.log) |
| `node --test scripts/test_assistant_tasks.mjs scripts/test_assistant_weixin_personal.mjs scripts/test_assistant_task_media_selection.mjs` | exit 0，106 passed | 最终界面源码，含选择保护与个人任务恢复。[原始输出](fix-green-node.log) |
| `node scripts/test_assistant_state.mjs` | 实现代理报告 exit 0，28 checks passed | 未保留可供本轮独立核对的原始日志，不计入独立核验数量。 |
| `git diff --cached --check` | exit 0 | 五个自有文件提交；其他前端备份和工作区改动未纳入。 |

Python 完整命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_weixin_personal_runtime.py tests/integration/test_task_drafts.py tests/integration/test_task_drafts_pdf.py tests/integration/test_task_drafts_bridge.py tests/integration/test_weixin_generation_guards.py tests/integration/test_weixin_reauthorization_atomic.py --basetemp D:/bt-m6-final-reg1 -q --tb=short
.venv/Scripts/python.exe -m pytest tests/integration/test_weixin_personal_runtime.py -k 'explicit_hold or desktop_main_selection or ambiguous_paused or queued_reply' --basetemp D:/bt-m6-final-code -q --tb=short
.venv/Scripts/python.exe -m pytest tests/integration/test_weixin_personal_runtime.py -k synthetic_paused --basetemp D:/bt-m6-final-synthetic -q --tb=short
```

初始失败分别保留在本机修复日志：Python 首轮14失败中12项为行为反例，另2项为测试假设/夹具修正；修正后的未改产品基线仍复现排队发送。前端3项缺失操作的失败在修复后通过。未用失败总数冒充全部产品缺陷。

排队测试实际占用唯一执行线程，在发送预占后改变授权，再释放线程，断言没有发送请求。覆盖注销、到期、对端撤权、恢复、会话绑定改变、模型配置改变和连接代际替换；注销情形重新连接后也不会重发未知记录。

## 复核与验收边界

一次针对四项最终发现的[独立复核](scoped-review.md)已完成：四项均 ADDRESSED，Spec / Standards 均 PASS，没有新增 Critical / Important；没有重复运行整套测试。复核直接读取最终17项 Python、106项 Node 和较早159项原始日志，28项控制器仅保留为实现代理报告。随后0.5.2已完成构建、隔离验证和本机原地升级，见[安装实测](desktop-052.md)。产品内本人扫码与真实微信业务仍待，不由离线测试代替。

此前2026-10-28文档转述的7381全仓通过为接续方报告，本轮未找到可核对的最终原始日志，不作为当前提交的已独立核验全仓证据。本轮也未重跑完整全仓。真实收件、模型分析、用户手机收到、律师质量及生产批准均独立于上述模拟验证，仍按[产品验收清单](../20261028/README.md)逐项完成。
