# 接待记录与工具

以下是 MCP 工具短名，运行时前缀为 `mcp__qx_legal__`。按实际提供的 schema 传参；工具暂不可用时保留正文，说明记录未落盘，不另造“已保存”回执。

| 工具 | 本流程用法 |
|---|---|
| `list_cases(query, offset, limit)` | 用户没给 ID 且需要找既有事项时，按用户明确名称检索；同名需分清。 |
| `create_case(title, our_role, request_id)` | 持续接待或明确保存而当前无案件 ID 时自动建立题名清楚的工作案件，记住返回的 `case_id`。不臆造我方角色。 |
| `get_case(case_id, offset, limit, include_history)` | 读当前记录与材料版本。看更正链时用历史选项；长文摘要不等于全文。 |
| `read_case_note(case_id, note_id, start, limit)` | 按返回续读位置取得长记录。 |
| `link_case_materials(case_id, paths)` | 仅绑定用户明确属于该案件的工作区文件。先用 `qx_materials.import_material/parse_material` 处理这些路径。 |
| `read_case_material(case_id, path, start, limit, page)` / `search_case_materials(case_id, query, offset, limit)` | 在已绑定的案件材料中找原话，保留页码/位置/摘要；按返回续读，不跨案件搜索替代。 |
| `record_case_note(case_id, kind, content, source, supersedes, citations, request_id)` | `consultation` 保存原话；`client_reply` 保存客户正文；`internal_note` 保存内部提醒；`todo` 保存跟进。更正的 `supersedes` 是原记录 ID。 |
| `export_case(case_id, filename, audience, note_ids)` | 客户版 `audience="client"` 仅选 `client_reply`，默认最新一条；内部版默认当前记录带来源。 |

`citations` 可以是 `[{"path":"inbox/材料.txt","quote":"实际逐字原文","sha256":"工具返回的文件摘要","chunk":0}]`。这里只示字段形状，不把示例当真实材料；使用实际返回的摘要和片段号，不自行计算 `start/end`。引用不匹配时记录会带待核警示；不能将该警示改称已核实。

`search_case_materials` 也可能命中笔记，先看返回的 `kind`。笔记只是陈述或分析的线索，不能当作材料原文；需要据此引用时再回读对应原始材料。

每次材料回读关注 `changed/missing` 等状态。旧记录仍指向旧版本，重新导入、解析和绑定后另记变化；不覆盖原话、旧材料或旧成果。只有用户明确更正旧记录时才填 `supersedes`；新进展另行追加。重复同一落档动作使用原 `request_id`，不同正文使用新 ID。
