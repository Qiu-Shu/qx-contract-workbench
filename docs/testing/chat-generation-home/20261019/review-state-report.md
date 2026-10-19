# CH-04C 状态与入口独立复核

审查范围：`assistant-generation.mjs`、`assistant-state.mjs`、`assistant.mjs`。对照 `docs/plans/2026-10-19-generation-home-execution.md`、CH-04B 后端能力/登记/查回契约和历史绑定规则；未审查本人编写的 renderer、CSS、模板。未修改产品文件；主代理授权后仅新增 `scripts/test_assistant_generation_entry.mjs`。

## 已关闭的问题

1. **P2：能力失效但入口去重键仍有效，撤回编辑后发送按钮不恢复。** 已 ready 的已保存输入 A 改为 B 后又回到 A，或选择技能后在调度前取消，会清空 capability，但入口 key 回到原值而不再查询。两个独立反例初始均失败：capability 读取仍仅 1 次、dirty=false、canSend=false。主代理修复为在 idle/tracking 且 capability 为空时失效入口去重键。
2. **该修复引出的额外读取已关闭。** refresh 在 run 的即时通知阶段仍是 idle，刚设置的去重键又被清空；能力读取失败时额外发起第 2 次读取。新反例实际观察 2 != 1。主代理将 refresh 在无 work/pending 时先同步设为 checking，最终读取失败仅 1 次，未形成自动重试。

## 最终验证

命令：`node --test scripts/test_assistant_generation_entry.mjs scripts/test_assistant_generation_state.mjs`

退出码 0。Node 报告 8 个顶层条目通过，其中 7 个是独立入口探针，另 1 个条目包装既有 27 组生成状态检查；应表述为 **7 项独立探针 + 27 组状态检查**，不能把包装条目与其内部检查重复相加。

独立探针覆盖：撤回编辑后的能力重查、取消技能选择后的重查、未知发送只查原请求且总 POST=1、跨对话迟到能力结果丢弃、历史绑定不符拒绝、撤权后迟到历史错误不复活状态、能力读取失败只尝试一次。现有 27 组另覆盖保存并发、固定请求身份、迟到提交、内容/作用域/版本摘要校验、分页与后续发送、取消和读取失败恢复。目标测试文件的 `git diff --check` 退出 0。

证据：`review-state-red-final.txt`（原 6 项：4 通过/2 失败），`review-state-entry-red.txt`（补强后 7 项：6 通过/1 失败），`review-state-final.txt`（最终通过），`review-state-final-input-hashes.json`（最终三份产品源码摘要）。初次 retest 的前置 ready 偶发失败来自测试没有等待异步摘要完成；harness 已显式等待自身发起的异步读取，后续报告不将其计为产品缺陷。

## 边界

当前审查范围没有未关闭的可复现发现。入口探针抽取真实 `coordinateGeneration` 函数，并使用真实 controller 与独立合成 API/计时器，不运行 DOM 或布局；真实浏览器、Electron、物理输入法和后端 HTTP 验证由主代理负责。本复核没有真实模型调用、材料访问、费用或外发，也不代表生产/法律质量验收。
