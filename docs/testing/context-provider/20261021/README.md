# CH-06B2b2a：资料回答适配基础及共享传输实测

本机 Windows，基线 `aa77af6903fd324bc3fd7cc4f5fb5b78a99a3aa9`；2026-10-21 北京时间实施。只用独立合成数据及 127.0.0.1 回环 HTTP，没有真实模型调用或真实资料处理。

## 已完成范围

- 新 `library-context-v1` 输入与模板身份：保存问题、完整来源摘要、有序引用、批准前范围及登记后确定版本；重建既有预览的精确 UTF-8 字节，超预算不截断。原文支持与适用性继续为待核。
- 独立 codec 验证完整 CitationRef 身份与来源范围；严格候选只接受本次选定的 UUID/原文摘要。候选被拒但合法 usage 已收到时保留费用估算。
- 原 DeepSeek HTTP 与响应封套抽出共用，main.py 从 242 行到 53 行；保留旧接口别名、请求、错误和取消语义。不是删除同等功能，也不是包体或 RSS 降幅结论。
- 新 adapter 默认拒绝；可信预检在密钥读取前后都必须严格返回 True。basis 只是输入描述，不能授予权限。当前应用 registry、runner、HTTP、原生控制均未接入它；预览的 sending_enabled 仍为 false。

## 验证结果

| 检查 | 本轮实际结果 | 原始证据 |
| --- | --- | --- |
| 最终关联 Python | **542 passed，0 failures/errors/skipped，exit 0**；22 个测试文件，包含本片新增 75 项；pytest 202.57 秒 | [目标清单](target-nodeids.txt)、[日志](target.log)、[XML](target.xml) |
| 固定输入 | 500 项 src/config/tests/scripts/项目锁定输入前后相同；全新 D 盘临时目录 | [命令、退出码与 SHA](target-verification.json) |
| 四项工程门禁 | schema、默认开关、开发来源、运行依赖均 exit 0；依赖 55+1 build，native_build_verified=false | [门禁1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |
| 旧 V1 兼容 | 4 组 wire、25 组响应 JSON 逐字相同；原 builder AST 和系统文本不变 | [对照结果](transport-compat.json)、[提取记录](transport-summary.json) |
| 独立 Spec | 6 项独立合成探针通过，无必须修复项；旧 domain 类 AST、隐藏来源身份、伪造 DTO、引用配对、预检关闭 | [复核报告](spec-review.md)、[执行证据](spec-context-probes.json) |
| 独立 Standards | 6 项通过，无必须修复项；其中2项独立探针、4项复用定向测试；取消/日志恢复、默认拒绝及截断费用未知 | [复核报告](standards-review.md)、[输入摘要](standards-evidence.json) |
| 冷进程导入 | 两个 provider 成功导入，httpx2/duckdb 均未导入 | [结果](cold-import.json) |
| WorkBuddy | 本轮实际连接并完成 `wb-c11f6dc1285f`，成功只读3文件；未做产品测试 | [实际返回](workbuddy.json)、[条件疑问核对](workbuddy-disposition.json) |

542 是相关范围回归，不是完整工程全套。独审、早期178和最终542有重叠，不累计成“总通过数”。实际回环 HTTP 覆盖精确发送、默认零请求、密钥后撤销、非法候选保留用量、截断未知且不重试；不称真实供应商验收。

## 失败与修正记录

- 最初 codec 缺失测试 1 failed，属有效 RED；实现后1 passed，扩展后40 passed。两个测试访问 Pydantic 实例 model_fields 的弃用警告已改为类访问。
- 新 provider 首轮15 passed/6 failed：测试把 `MainReceipt.state` 与 `cost_status` 混用；仅修正断言，产品未因此更改，随后61项通过。[初始记录](root-initial-results.json)是当时工具输出摘要，没有伪造早期 XML。
- 公共传输缺失的有效 RED 原日志保留。提取后一次 `-W error` 与既有 Jev `record_property`/xunit2 设置冲突，177 passed/1 setup error；改运行报告参数为 xunit1 后178通过。最终542也用 xunit1。[原始失败](transport-targeted.log)、[修正后的178](transport-final.log)。
- WorkBuddy 未读 domain.py，提出“quote hash/ID 是否存在”的条件疑问。统筹检查确认 quote_sha256 必需、无混淆 id 字段，完整来源摘要本机保存，不把不完整阅读当成已证实缺陷。

## 复现与边界

正式测试可用项目 `.venv/Scripts/python.exe -X utf8 -m pytest` 加目标清单中22个文件运行；选择新的短 D 盘 basetemp，设置 `-o junit_family=xunit1`。本目录保存原运行脚本/命令用于溯源；其中 `.local` 路径是当时执行位置，重新运行应使用新的输出位置，不能覆盖本证据。需要原试点解释器的测试继续使用既有独立环境，不重新导入数据。

没有新增依赖、schema、队列或费用账本；未重建 GUI/Electron/冻结安装器，安装版仍0.4.1。没有总体启动时间、包体或占用的同能力对照验收。真实资料、F盘库、网盘未下载年份及阿里云没有变化。

下一片按[存储与接线设计](../../../plans/2026-10-20-context-send-storage.md)，一次完成输入格式列、有序来源关系、原生具体许可、同 attempt 执行/撤销/费用及升级恢复后，才开启应用资料发送。当前完整来源验证仍需可信服务在发送时重核；纯 codec 不提供访问授权。

[本片执行计划](../../../plans/2026-10-21-context-provider.md)。47份原始证据的字节摘要见 [evidence-manifest.json](evidence-manifest.json)；README与manifest本身不作自引用。GitHub同步结果以独立回执为准。
