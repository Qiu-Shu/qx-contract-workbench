# T03 父节点开发集成核验

记录上下文日期 2026-10-03，Asia/Shanghai。以下是来源和依赖集成检查，不替代文档功能测试或生产批准。

| 实际动作/命令 | 退出码 | 结果 |
| --- | ---: | --- |
| 本地 wheel 内 page.py、__init__.py 与 G06 固定提交已读文件字节/hash 比较 | 0 | 2/2 一致，只覆盖两份文件 |
| `.venv/Scripts/python.exe -m pip install --no-build-isolation --no-deps -e .` | 0 | 实际更新可编辑应用安装元数据，加入 PDF/XML 声明；依赖另由 hash 锁安装 |
| 初次 G06 清单片段编辑 | 0 | 编辑脚本运行成功，但随后检查发现截取到嵌套结束行导致 JSON 无效；不计为通过 |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py` 及 `--mode release` 初检 | 1/1 | MANIFEST_INVALID:JSONDecodeError，实际 checked_sources=0 |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_verify_sources.py -q` | 1 | 路径不存在，0 项运行；不是有效 RED |
| 修正片段边界并完整 JSON 比较 | 0 | 保留当前提交原文，仅更改 G06 对象；13 来源，JSON 有效 |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_sources.py -q` | 0 | 28 passed，0 failed |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py` 修正后 | 0 | 13 来源实读；0 errors；13 NOT_PRODUCTION_APPROVED 警告 |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py --mode release` 修正后 | 1 | G06/G10 的 DEPENDENCY_REVIEW_PENDING、PRODUCTION_APPROVAL_MISSING，预期阻断 |
| `.venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=docs/testing/T03-results.xml` 最终父节点 | 0 | 269 passed，1 既有 Starlette/httpx 弃用警告，21.06 秒；200 既有加 69 T03 |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_defaults.py --file config/defaults.json` | 0 | 默认 hash 完全一致 |
| `.venv/Scripts/python.exe -m cn_contract.cli schema --check` | 0 | 与唯一 ReviewRun DTO schema 一致 |
| `.venv/Scripts/python.exe -m pip check` 最终父节点 | 0 | No broken requirements found |
| Git 索引 blob 对两份正式来源/依赖 manifest 中 local_target 的独立 SHA-256 核对 | 0 | 137 个独立被引用文件全部匹配；未经换行转换的原始证据 |
| `git diff --cached --check` 初次 | 1 | 新跟踪测试 helper 尾部多空行；只删多余 EOF 空行，不改可执行内容 |
| `git diff --cached --check` 修正后 | 0 | 0 空白错误；原始许可字节没有修改 |

G06 已如实登记 included_in_runtime=true、仅开发虚构 PDF 解析范围。35 包应用/测试锁的 wheel、许可、安装元数据证据见 docs/reuse/T03-dependencies.md；原生许可、源供应链和使用范围未完成生产批准。没有真实合同、QCC、付费或对外发布。
