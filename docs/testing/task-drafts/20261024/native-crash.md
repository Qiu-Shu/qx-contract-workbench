# Windows 长进程回归崩溃记录

日期：2026-10-24。仅独立合成测试，工作区 `D:\Documents\ChatGPT\律所项目`。这是未关闭的稳定性观察，不把短进程通过表述为原生崩溃已修复。

## 实际现象

根任务执行 18 文件功能关联回归，原始文件列表位于 `.local/task-drafts-20261024/verification/functional-files.json`。约完成 245 个测试回执后，日志出现 `Windows fatal exception: access violation`，外层执行实际退出 1，没有生成最终 JUnit 和完整统计。此前日志中另有一个前端 `F`，具体失败详情未在崩溃前输出，不能推断其根因；最终稳定源码的前端 11 项及 Node 161 项独立重跑均通过。

原生栈：GC → Python `xml.etree.ElementTree._start/feed` → `defusedxml.common.fromstring` → `documents.docx_adapter._xml/read_package/parse_docx` → `documents.ingest.parse_document` → `web.services.candidate_parse` → `web.jobs.run_next_job` → `test_assisted_review.parsed_case/ready_case/submit_proposal` → `test_assisted_confirmation.test_assistant_and_cross_case_cannot_confirm`。另一线程处于 AnyIO TestClient 的 Windows asyncio 事件轮询。

环境实际记录：Python 3.12.14，MSC v.1944，AMD64；defusedxml 0.7.1、python-docx 1.2.0、lxml 6.1.3、pytest 9.0.3。源码与 HEAD 摘要对比确认 docx_adapter、ingest、jobs、两份 assisted 测试及 pyproject 未被本片修改；candidate_parse 新参数默认 False，既有 jobs 调用继续走原 assisted 路径。这些事实不足以证明崩溃与本片无关。

## 本轮调查与重跑

- 已阅读 systematic-debugging / diagnosing-bugs，先保留日志、检查变更并构建最小复现，不猜测修复 GC/XML，也没有改解析器或安装依赖。
- 精确命令：`.venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/integration/test_assisted_confirmation.py::test_assistant_and_cross_case_cannot_confirm`（另指定临时目录和 JUnit）。实际 1 passed，10.84 秒，退出 0；`crash-exact-test.log/.xml/.exit` 可核对。没有复现访问冲突，不能据此确认根因或宣称修复。
- 随后整模块及 19 文件分模块重跑在会话/工具中断后无存活进程，部分临时回执不完整；未取得退出码的运行不计 PASS。产品文件摘要未变化，交付源码、测试及文档扫描无 NUL 字节。
- 后续改为每组最多 8 个现有测试节点、独立 Python 进程，并原子保存每组退出码和 JUnit；已完成模块不重复计数。最终结果由本目录 README 汇总。这是验证执行方式，不是产品崩溃修复，不关闭长进程稳定性问题。

原始证据均在 `.local/task-drafts-20261024/verification/`，包括 `functional.log`、`crash-environment.json` 和 `crash-exact-test.*`，不纳入 Git。完整单进程回归、已安装 Electron 长时间运行、真实合同和生产验收仍未完成。

最终短组及完整模块回执按节点去重为382项全部通过（包括原confirmation模块的19个用例），0失败/错误/跳过；没有复现原生访问冲突。此结果仅证明这些独立进程验证通过，长进程问题仍未关闭。
