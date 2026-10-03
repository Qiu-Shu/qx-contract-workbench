# T04 父节点最终核验

记录日期：2026-10-03，Asia/Shanghai。T00–T03 保留原实现；业务 DTO、schema、defaults 未改。仅独立虚构材料，模型/QCC关闭，未安装新包或对外发送。

| 实际命令 | 退出码 | 实际结果 |
| --- | ---: | --- |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T04-results.xml` | 0 | 345 passed，1 条既有 Starlette/httpx 弃用警告，32.59 秒；269 既有加 76 T04 |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_defaults.py --file config/defaults.json` | 0 | 规范默认 hash 完全一致 |
| `.venv/Scripts/python.exe -X utf8 -m cn_contract.cli schema --check` | 0 | 唯一 ReviewRun DTO 生成 schema 与已存一致 |
| `.venv/Scripts/python.exe -m pip check` | 0 | No broken requirements found |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py` | 0 | 13 来源；0 errors；13 NOT_PRODUCTION_APPROVED 警告 |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py --mode release` | 1 | G06/G10 的 DEPENDENCY_REVIEW_PENDING、PRODUCTION_APPROVAL_MISSING，预期阻断 |
| `git diff --check` | 0 | 跟踪变更无空白错误；未跟踪文件须暂存后另核对 |
| `git diff --cached --check` 暂存所有T04新文件后 | 0 | 新代码、测试和文档无空白错误；T07候选文件未暂存 |

功能 RED/GREEN 与实现限制在 T04.md；独立 P2 原文信任根污染及其复验在 T04-review.md。不能把 DTO/存储快照存在当作原文来源已验证；T04 新 trusted_parse 只读不可变原件重算完整解析，既有 T02/T03 原件与记录不重写。

用户本轮更新的 AGENTS.md 已保存本地 Obsidian 自动工作流约束。实际读取 00_Core 三入口；只读中文 memory_search("合同审查") 无命中，本地项目状态检索无命中。当前没有 obsidian_auto.memory_record 工具，已通过授权 obsidian_local 新增项目摘要与 Index，并向原 Projects.md 追加链接后读回核对成功；未宣称结构化 API 调用成功或索引缓存已同步。知识库目录在 D:/Documents/Obsidian Vault/Codex_Memory/10_Projects/contract-review-workbench-local，实际 workspace 是本项目目录。私人法律谈话和源笔记没有进入仓库或运行目录。

仍未完成法律规则核验/批准、四类审查业务闭环、真实外部收据、正式签发、律师金标准和生产批准。T05/T06细化计划及T07只读依赖候选不是已实现功能。
