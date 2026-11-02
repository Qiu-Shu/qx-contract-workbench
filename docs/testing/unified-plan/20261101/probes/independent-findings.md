# 阶段 1 独立审阅：2026-11-01 候选第一轮

审阅范围为相对 `.local/unified-plan-20261101/baseline/files/` 的本轮 S1/S2 增量。只写本 review 目录的探针和报告，未改产品源码、Git/index、数据库配置。运行使用既有 `world(tmp_path)` 合成数据库及 `httpx.MockTransport`，未访问生产库、微信或真实模型。

## 阻断发现

1. **P1：全局控制保护仍漏掉常用指令。** `assistant/business.py:34–48` 与 `web/static/assistant-business.mjs:11–27` 的新增控制模式要求停止词后必须有特定宾语，且通用否定只覆盖少数词。合成微信运行中，`新事项：请审查合同\n停止`、`…\n暂不处理`、`…\n不要继续处理` 均主模型实际调用 1 次，批次 `completed/contract`。`…\n取消\n可以开始`、`…\n暂停\n可以开始` 也调用 1 次。桌面控制器中 `…\n暂停` / `…\n取消` / `…\n停止` 均进入 Jev → business → authorize → model。应把全局暂停/取消/停止/撤回和能力否定分开处理，并统一前后端判定；取消后只确认材料齐备不足以恢复业务执行。

2. **P1：桌面已识别的只接收指令仍先发辅助模型。** `web/static/assistant-state.mjs:347–360` 在 `business.send` 的阻断检查前调用 `api.assistJudge`。合成控制器探针的 `只接收材料` 及 `新事项：暂时不审查合同，只接收材料` 均调用 Jev 1 次，随后才被 business 阻断。当前 JS 测试只断言 business/authorize/model，不计辅助模型，无法证明“模型调用 0”。需要在自动辅助判断前执行同一否定门，并断言辅助与主模型均 0。

3. **P1：未见过的旧重启消息迟到会解除较新停止。** 新 `execution_hold` 根据接收行顺序解除 held；`service_records.events:42` 按 rowid 读取，入库并未保存可信源时序。合成探针先接收 seq=1/create_time_ms=1000 的整理请求和 seq=3/time=3000 的停止，确认 0 次调用；再接收先前未见的 seq=2/time=2000 `现在请整理材料`，实际触发 1 次主模型。重复已接收事件对照通过，仍 0。不能把该通过结果外推为所有迟到旧消息均安全，也不能假定 message_id 为可比较序号；需明确可信源顺序契约或保守的重启确认边界。这是本轮期望的“旧消息不得恢复已停止任务”的真实未关闭缺口。

## 其他发现与建议

- 不同能力的明确重启运行探针通过：合同请求 → 停止处理 → 现在请整理材料，只整理证据，最后只执行 case 1 次。
- 条件/转述与后续另一能力的组合仍有语义残留：`如果材料齐全，请审查合同\n现在请整理材料`、`客户说请审查合同\n现在请整理材料` 的 `classify` 均 `ambiguous`，`rejected(...,'contract')` False。解除全局 held 后，历史条件/转述又参与全部能力匹配。微信最后显式事件覆盖可能掩盖该问题，桌面普通自动路由会澄清。建议加入同一共享反例集合，要求只有 case 被授权。
- 新增补件关联规则范围小，保留多候选时 clarify；但本审阅没有独立重跑全部 S2、权限、未知不重发和账本回归，不能代替主代理的回归证据。

## 实际运行

1. `.venv/Scripts/python.exe -X utf8 -m pytest .local/unified-plan-20261101/review/test_independent_controls.py -q -s --tb=short -p no:cacheprovider --basetemp=.local/unified-plan-20261101/review/pytest-data`：当时 6 项，5 failed、1 passed，13.32 秒，exit 1。
2. 同脚本增加迟到与重复对照后，`... --basetemp=.local/unified-plan-20261101/review/pytest-order -k "unseen or seen_duplicate"`：1 failed、1 passed、6 deselected，4.63 秒，exit 1。
3. `node .local/unified-plan-20261101/review/desktop-probe.mjs`：exit 0；5 条控制器轨迹打印（诊断输出，不是通过断言）。前两条 calls=[Jev]，后三条 calls=[Jev,business,authorize,model]。

审阅时文件 SHA-256：
- business.py: `b10ecb3cdcd28dbd3e003fd3d0a8a39a207c83fee8aa72ca0b8f56bd093fe8c9`
- assistant-business.mjs: `ab2975cdcf00cdf481d56cc945032a74a761c9f2492436058e2ba78241bb3517`
- service_routing.py: `7818f0d2c5e6172346e7dd36a0297748a25a144c3380738ed161a30455260730`

这些是修复前红测证据，后续修复需要独立复跑，不得改标历史结果。
