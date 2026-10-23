# CH-07C2b2b-B 历史与恢复完整性实现记录

基线：`9a0d2df3767dc8252f1530be4f949583fd250af2`。仅写获分配的四个产品/测试文件与本目录；无提交、推送、真实模型、真实材料或全套测试。

## 实现

- 公共模型校验保留旧格式、费用/共同 policy 计数、轮次和混格式 run 限制，显式分派 `profile-text-v1`。
- 新 `profile_model_integrity.py` 验证本次用户文本、完整 basis、规范 wire、原保存请求摘要、历史档案/接待基线、单次用途许可和候选来源；通过现有 `profile_integrity` 重放实际保存语义。
- 空账本提前返回前验证全局 handler、response.ready 和 profile.* 事件。每个采用的 profile output 恰有一个固定 handler，严格绑定 ready/result/finished 的先后、payload 类型、候选与固定保存 request、实际保存回执。
- 拒绝有固定 profile 保存回执而无采用 output 的半提交。blocked 不能携带已保存回执；合法 unchanged 不强制产生档案 revision。
- 不扩大历史换绑能力；旧共同 scope 规则原样保留。后续接待编辑、正规转案、会话撤权通过历史验收。接待历史创建时间使用 revision 1 的 saved_at（表本身没有 created_at）。

## 命令及结果

所有 pytest 使用本项目 `.venv/Scripts/python.exe -X utf8 -m pytest`、`-q --tb=short`、本目录唯一 basetemp 和 XML；日志与 XML 同前缀。执行命令的目标、选择器如下：

| 日志 | 测试目标 / 选择器 | 实际结果 | 退出码 |
| --- | --- | --- | --- |
| red | test_assistant_profile_model_integrity.py -k profile_events_without | 6 failed，全部 DID NOT RAISE；真正产品 RED | 1 |
| green | 同上 | 6 passed，7 deselected | 0 |
| history | test_assistant_profile_model_integrity.py | 13 passed，36 fixture 装配失败（合成 loopback 缺路径） | 1 |
| positive | 同文件 -k "preserves_state or without_profile_revision" | 7 fixture 装配失败（registry.resolve 需要运行中的 event loop），42 deselected | 1 |
| positive2 | 同上，修复测试装配 | 7 passed，42 deselected | 0 |
| target | test_assistant_profile_model_integrity.py + test_assistant_profile_execution_backup.py | 58 passed，58.02 秒 | 0 |
| atomic-red | integrity 文件 -k "partial_commit or sequence_boolean" | 2 failed，均 DID NOT RAISE；半提交与 bool/int payload 混同真实 RED | 1 |
| atomic-green | integrity 文件 -k "partial_commit or sequence_boolean or legitimate_later" | 4 passed；1 fixture enum 拼写错误；49 deselected | 1 |
| final | integrity + execution_backup 两文件 | 62 passed；1 fixture 缺 Database rules-storage flag；59.78 秒 | 1 |
| later | integrity 文件 -k legitimate_later，正规标记已有 storage flags 后 | 3 passed，51 deselected；2.71 秒 | 0 |

最后的 63 项并非单次全绿：保留 `final.log` 初次失败及 `later.log` 补验。父代理将在冻结后的整体输入上执行一次关联回归。两处 fixture 错误均未据此修改产品行为。

`git diff --check -- <四个拥有文件>` 退出 0。

## 覆盖与边界

历史测试总计 54 项：原七项空结构/假格式/孤立 handler/认证备份篡改用例保留；新增全局孤立事件、五种 attempt 状态、applied/unchanged/blocked、重新计算摘要后的来源/回执/档案篡改、完整 basis/原请求/许可/费用篡改、半提交及 payload 类型、正规后续修改。

备份专用测试 9 项：七种场景真实 qxbak 创建、恢复、再次备份恢复；恢复后 reserved→failed_before_send、sending→sent_unknown，不创建 handler，不续发，保留原 immutable 行和原库字节。两种认证但语义篡改的备份在发布和恢复阶段均拒绝，目标不留下可用恢复目录。

合成回复经实际 profile codec 和 ledger/store 结算，没有连接 socket。runtime 只配置固定 loopback，未调用外部模型。旧格式受影响回归及联合冻结后的输入稳定性由父代理统一执行，本子任务不重复该组测试。

## 冻结输入

四文件 SHA256 已存 `frozen-inputs.json`。`owned-inputs.json` 是最后两文件运行结束附近的快照；其后仅修改测试的 storage flag 装配一行，再运行三个对应完整参数用例。产品文件在这些验证期间没有再次改变。

- model_integrity.py：3ACBA310648056BFEC2A094E7CA7BAAEE0D49CF086BD8C4F198841F5CEA22159
- profile_model_integrity.py：747A44EB031C4809A5E21BA864D89B5321EF3646FEB514D94FD920C105C2AE87
- test_assistant_profile_model_integrity.py：4DE7131FA75A46AD46BE088CF4ED062480C88AD2B7D87CF1B902E87807252AC0
- test_assistant_profile_execution_backup.py：C0774416AA488381A75DF9D1D188C5865C48309A014CEFDAA45F6C64C404D842

这不是独立审查报告，也不代表真实供应商、原生入口、HTTP、UI、安装版或法律质量验收。
