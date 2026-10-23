# CH-07C3a 发布文档独立核对

核对时间（UTC）：2026-10-23T09:04:33.769958+00:00
当前本地提交：`1a03d89cd73433e9a1b4de8870be5a4f6f77549a`；本次核对不验证或声称远端已经同步。

结论：**通过，0 项阻断问题；1 项非阻断导航文案问题。** 本次只读取文档与已有证据，不重跑产品测试、不修改产品及冻结证据。原 Standards 产品报告及其输入摘要未重写。

## 数量与证据一致性

- 证据清单含 104 项文件；逐文件复算 bytes/SHA256，104 项全部匹配，无缺失。
- `verification.json` 的 627 项 before/after 完全相同，逐项与当前磁盘一致；Windows report 的 627 项 before/after 亦完全一致且与主验证清单相等。
- 从三份原始 JUnit XML 按 classname::name 去重并以补验结果更新：最终 265 个不同 Python 测试全部通过。历史 190 项通过；根任务初轮 75 项中 62 通过、13 setup error；D 盘独立临时目录复跑相关完整文件 14 项通过，其中 1 项与初轮通过项重叠，因此 190 + 62 + 13 = 265，不能算 266，也不是本轮完整 Python 套件。
- 原始 Node 日志末尾分别为桌面 366、前端 141 passed，failure/cancelled/skipped/todo 均为 0；主验证记录两项 exit 0。四开发门各 exit 0。
- Windows report 有 6 个 checks，status passed；profile POST 1、旧 generation POST 0；main provider 1、judge 0；loopback_calls 1、external_requests 0；档案修订/回执/handler/接待记录各 1。Electron 和自有 backend exit 均为 0。
- 独立 Spec 的 3 Node 与 3 Python 是最终不同用例结果：保留初始 collection/fixture 失败及单项补验，未伪称单次全绿。独立 Standards 的 4 Node/5 Python、555 输入是原独审范围，不与主测试数累计。

## 声明与边界

- README、TODO、TASK_STATUS、实施计划及执行记录准确限定为源码分支普通文字、无技能/附件/选片的单次回答与待核档案/接待保存，以及只读侧栏和历史。旧 plain/context 路径及按用途授权未被描述为自动升级。
- 当前 265 项与历史阶段完整 Python 4,393 项明确分开；C 盘 34,249,146,368 bytes 低于既有 40 GiB 守卫造成的 13 setup errors 及 exit 1 保留，后续仅移动临时目录，没有声称放宽业务保护或无失败首轮。
- CH-07C3b 人工修改/保护/清空及联系方式仍待；附件/技能受控建档、原文跳转、导出、更新安装包仍在后续阶段。
- Profile 路径没有 Jev 调用，许可不扩大至 Jev；真实模型与真实材料外发、阿里云和未下载年份未被声称完成。
- 安装版仍 0.4.1；WIN-PATH-02 仍开放。源码实机及应用缩放不等同安装包、物理 DPI、启动/RSS/包体或法律质量验收。
- 发布文档保留随后生成 GitHub 同步回执的边界；本次没有自行运行推送、远端 SHA 或敏感扫描验证。

## 非阻断导航问题

- `README.md:45` 的“最近已核验的 GitHub 同步记录”仍指向较早的 C2c APPLICATION 回执，而顶部已列较新的 C2d DESKTOP 回执。该处不影响本片产品/验证结论。主任务已确认后续远端核验成功后随本片同步回执，将入口更新至 `GITHUB-PROFILE-UI-20261023.md`；本核对未代改，也未提前认定该动作完成。

## 本次只读核对执行记录

1. PowerShell here-string 经 `.venv/Scripts/python.exe -`：复算 104 证据文件与 627 输入、解析 3 XML 和 Windows report，exit 0。
2. 第二次只读输出检查：Windows/主输入一致，366/141 日志末尾核实；输出较长中文文档时终端 GBK 无法编码 U+2194，exit 1。这是本次审阅输出编码问题，不是产品测试失败或证据损坏。
3. 改用 `.venv/Scripts/python.exe -X utf8 -` 重读相关状态、计划、Spec 最终记录及 backend exit，exit 0。没有重跑产品测试。

## 发布文档快照 SHA256

- `README.md`: `f42d07c9da662940ac8cdc3086b4203cccd09dec9a36e6f64e75f7f51d155d3d`
- `TODO.md`: `adf0590c26b3ce4ec35b950923e4fb3241e15416402597866c7c927ab443d056`
- `docs/TASK_STATUS.md`: `fd66df308bf0d2cfb93f6aa8be7276a8d212c7e85e1d7f03888c8094c50f2b56`
- `docs/plans/2026-10-23-profile-ui.md`: `eb6b448708313ae39eed6f936a03be09994ed6a558b8bfcd65ac392526ac0c52`
- `docs/plans/2026-10-16-chat-first-execution.md`: `4a517feb88a4b138879d017b6b88731ee7f155d544870ecac8732e257ce561d5`
- `docs/testing/profile-ui/20261023/README.md`: `72e09a9adada497a39ffc615e6d41873d837dadee1c776cb2754338017689b15`
- `docs/testing/profile-ui/20261023/evidence-manifest.json`: `2db664845aa7dc64c4b3a861cf5fa77f17d743529444630b6b6e24667257b62c`
- `docs/testing/profile-ui/20261023/final-verification.json`: `31e9aa7bc5a4bc812cc107f8c8e9c38b00a0768b1d332b04de9f10faada693f4`
