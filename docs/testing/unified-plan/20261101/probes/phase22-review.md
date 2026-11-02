# 阶段 2.2 独立复核

日期：2026-11-01。只读产品代码，仅在本 review 目录编写并运行独立合成探针。未访问生产数据库、真实模型、微信或外部账户。

## 结论

本轮发现的一个 P2 身份识别缺陷已修复并独立复跑通过。当前审阅范围内未再发现可复现阻断问题。此结论只覆盖阶段 2.2 候选，不代表阶段 2 总体验收或生产完成。

原反例为“我是原告吗？请模拟法庭。”和“代表原告的不是我，请模拟法庭。”。旧的行首前缀匹配错误地产生 plaintiff 上下文；当前完整肯定分句匹配及疑问/否定检查均返回 HEARING_ROLE_REQUIRED。

## 本轮实际验证

独立探针：`test_phase22_independent.py`。

最终命令：`.venv/Scripts/python.exe -X utf8 -m pytest .local/unified-plan-20261101/review/test_phase22_independent.py -q -p no:cacheprovider --basetemp=.local/unified-plan-20261101/review/pytest-phase22-final --junitxml=.local/unified-plan-20261101/review/phase22-independent-final.xml`。

结果：退出码 0，**5 passed in 8.44s**。

- 疑问身份和后置否定身份各一例均在 preview 阶段阻断。
- 模型发送期间通过正式 cancel_run 取消，模型返回后不保存演练成果；保留费用回执，账本校验通过。
- 同一 attempt 并发执行只调用模型一次，只保存首次阶段的 3 个回合。
- 移除当前登记配置后历史成果仍可回读和校验；重新登记相同固定来源后同任务进入 evidence 阶段，保留前一成果 ID。

早期 `phase22-independent-first.xml` 为 3 failed / 1 passed，其中两个为上述实证身份缺陷；另一个是审阅探针在持衡记录事务内同步开启第二写事务导致 BEGIN IMMEDIATE 锁等待失败，并不能证明产品取消绕过。该探针已改为正常发送期间取消。修订后 `phase22-independent-stable.xml` 记录 3 passed / 2 deselected，最终 XML 为全 5 项通过。

## 已审阅边界

阅读持衡 source hash 登记、捕获源码后私有模块执行、临时私有材料、上游 create_session/append_turn/load_session/hearing_progress 接口、历史 DTO 校验、同任务阶段选择与材料/方法变更重开、材料发送与结算接口。上游是明确批准的本地可执行代码，并非沙箱；历史回读不执行当前安装目录代码。完成状态仍为结构完成、待律师核对。

未重跑全套，未进行真实模型、真实材料或真实微信验收；未独立进行本阶段备份恢复演练、操作系统 ACL 穿透测试或前端可用性验收。缺少登记配置时沿用旧兼容模式是作者明确保留的行为，不应据此宣称默认启动已接入四项能力。可信配置检查和后续知识检索仍须列入后续阶段门。

## 补充：原生桌面入口

只读检查 `desktop/material-basis.cjs`、`desktop/model-approval.cjs`、`desktop/model-session.cjs` 的本轮增量，并核对未修改的 material-approval / model-control 调用链与新增测试。未发现新增实证缺陷。

- `node --test desktop/tests/material-approval.test.cjs`：退出码 0，22 项通过，209.4657ms；含本轮方法/演练快照接入、方法变更阻断、固定 409 码与私密文本丢弃。
- 独立 `export_native_fixtures.py` 只以 SQLite `mode=ro` 读取本审阅已生成的合成测试数据库，导出 6 份实际 Python 账本 basis。其种类为 local_skill / local_adapter，演练阶段含 issues / evidence。
- `node .local/unified-plan-20261101/review/native-material-probe.cjs`：退出码 0；6 份 basis 均通过 JS 原生校验与真实 ModelControl 请求序列化，传递内容逐字段相等；额外的 capability.root 和错误阶段角色均被拒绝。此探针未使用 Electron GUI、真实后端服务或模型。

确认二次 snapshot 的完整 JSON 精确比较仍在审批之前；渲染进程仍只能提交选择信息，不能提交根路径、方法正文或任意 basis。新增业务错误保留固定码，错误文本不返回调用端。历史回合的完整摘要及阶段重建仍由后端负责，不把桌面结构校验当成授权来源。
