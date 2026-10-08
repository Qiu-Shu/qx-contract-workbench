# 本机聊天元数据兼容修复：独立审阅

日期：2026-10-09。范围：HEAD f8513f7 至当前工作树的 src/cn_contract/mcp/offline_server.py、tests/integration/test_mcp_chat_envelope.py、tests/unit/test_mcp_chat_metadata.py、plugins/qx-contract-offline-codex/runtime-binding.json。没有编辑产品、绑定或无关文件。

## 结论

Critical 0；Important 0；Minor 1（持久回归覆盖，见下）。在所审范围内可继续集成。本审阅不证明当前聊天实际原生工具调用恢复，该项需父会话实际调用确认。

新增白名单只扩大 tools/call 的宿主相关字段，以及 tools/list 的 W3C 追踪字段。低层 callback 只传递 name/arguments，传输 metadata 不传入业务 handler；既有 exact 参数校验、固定工具名、虚构 fixture 枚举和统一错误继续生效。嵌套元数据虽允许不解释的键，其形状和序列化大小均受限，未用作权限、身份或批准。OTel/request-state 默认中间件仍被替换。runtime-binding 仅变动该产品文件摘要及相应 build_id，运行入口实际核验通过。

## Minor：精确预算限制缺少持久回归

位置：tests/integration/test_mcp_chat_envelope.py 的 test_malformed_chat_metadata_is_sanitized_and_session_recovers；tests/unit/test_mcp_chat_metadata.py。

当前 raw 字符串 8193 字符已先触发单字符串 2048 上限，列表 257 元素已先触发单列表 64 上限；因此这些断言不能检测删除整体 8192 UTF-8 bytes 或 256 节点守卫的退化。独立探针证明目前实现正确，但建议将恰好 8192/8193 bytes、256/257 节点、4/5 层用例纳入正式单元回归。构造方法见同目录 independent_probe.py，所有子字符串/子列表均保持单项预算内。

## 实际验证

| 命令/动作 | 退出码 | 结果 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_mcp_chat_metadata.py tests/integration/test_mcp_chat_envelope.py -q` | 0 | 8 passed，5.55 秒；包含两种元数据组合与两个工具、未知业务工具/参数拒绝、错误脱敏/会话恢复 |
| `.venv/Scripts/python.exe .audit-local/plugin-host-fix-20261009/independent_probe.py` | 0 | 18 个精确边界断言通过：depth4/5、dict64/65、list64/65、str2048/2049、nodes256/257、bytes8192/8193、int64上下限与双侧越界、控制字符、非空 associated_remote_urls |
| `.venv/Scripts/python.exe -I -X utf8 D:/Documents/ChatGPT/律所项目/src/cn_contract/mcp/bound_entry.py --check` | 0 | BOUND_ENTRY_VERIFIED；build_id qx-offline-source-0.1.3-ad69c2feda27542e4bad2e373436eb7e |
| CodeGraph `_finite_tool_metadata _bounded_turn_metadata _finite_call_envelope`，实际 projectPath，maxFiles 2 | 工具成功 | 复用现有索引，定位 5 个调用点及 callback 丢弃边界；后续以当前源码核对 |
| Obsidian memory_search，实际 workspace，关键词“群兴 离线 MCP 元数据 宿主调用” | 工具成功 | 2 项历史线索；无需要补读的当前缺陷证据 |
| 两次最初 rg 使用 Windows 不展开的路径通配符 | 1 | 查询用法错误，无产品执行；随后改为目录加 -g '*.rs' 成功 |

## 固定宿主证据核对

- host-mcp-tool-call.rs:1320 附近 build_mcp_tool_call_request_meta 加入 callId、x-codex-turn-metadata、plugin_id。codex_apps_meta 和 confirmation_policies 为特定连接器条件，不要求本离线服务开放。
- turn_metadata.rs:271-288 在 MCP 投影中明确清除 tool_namespaces_info，并移除 agent_name、parent_turn_id、root_turn_id。没有把包含完整工具清单的 Responses API 投影误用于本测试。
- responses_metadata.rs:187-193 工作区下 associated_remote_urls 是字符串映射；独立补验非空 origin，恰好符合当前深度4限制。
- rmcp-client-src-trace_context.rs:18-42 说明 request trace 与 pagination 传播；rollout-trace-src-mcp.rs:10/49 说明 codex_bridge_mcp_call_id 的可选传播。

## 限制

未重跑全仓测试，父会话负责关联回归；未重复当前聊天原生工具调用或确认宿主已载入新进程。未启用真实 DeepSeek/QCC、上传真实材料、修改宿主缓存、评定法律质量或生产就绪。完整帧大小/OS资源隔离仍属于既有未完成范围，本轮递归预算不等同于解析前帧限额。

## 补充：独审会话实际原生宿主调用（2026-10-09）

父会话按 Minor 新增了整体预算边界回归，独审重新执行 `.venv/Scripts/python.exe -m pytest tests/unit/test_mcp_chat_metadata.py -q`：6 passed，exit 0。原 Minor 已闭合；最终所审 Critical 0 / Important 0 / Minor 0。

按父会话要求，在此独审会话直接发现并调用已注册 `mcp__qx_contract_offline` 原生工具，不通过自建STDIO探针，不改源、不启动真实模型：

1. `workbench_status({})`：实际 isError=false；synthetic=true、status=OFFLINE_ONLY、real_models_enabled=false、qcc_enabled=false、production_status=PRODUCTION_BLOCKED、chatgpt_connection_verified=false。
2. `deepseek_offline_example({fixture: "nda", operation: "review_chunk", model: "deepseek-flash"})`：实际 isError=false；fixture_sha256=c3b27a05b60cf656053af95e74d908f0d90038b58247bd5ea7fba9a742789e0c；reply.request_id=manual-synthetic-offline-example、status=OFFLINE_ONLY、validation_scope=protocol_only；response_origin=manually_constructed_not_supplier、cost=null、legal_opinion=false。

这证明本独审会话当前宿主实际调用已可穿过修复边界；不是SDK模拟通过。父会话报告其自身当前活动turn仍返回-32602，且插件开关后旧bound_entry进程仍在。本次结果支持会话/进程加载差异为后续排查方向，但没有直接核验父进程内存源码或证明其已加载新字节，不能把父会话故障标为已恢复。网页ChatGPT连接、真实模型/QCC、法律及生产状态不变。
