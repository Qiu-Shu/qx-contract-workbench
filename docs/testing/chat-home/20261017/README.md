# CH-02A：对话首页与本机草稿实测

2026-10-17；基线 e46ce3c，沿用现有 Electron、FastAPI、Jinja2 和静态页面。首页草稿切片已完成实现、独立复核及完整回归，尚不是模型聊天或整个程序交付。[数值汇总与原始证据摘要](summary.json)。

## 实际实现

原生工作台登录后按服务器返回的 home_url 进入对话首页，其他角色与恢复副本仍进入适用页面。四张技能卡、左侧常用能力／最近记录／旧业务入口、字号与窄窗口菜单已连接；无输入时不创建空记录。能力选择保留原文字，不立即发送。现有生成器和聊天附件尚未连接，发送和添加材料明确禁用，Enter 不登记假任务；Shift+Enter 换行并保护中文组合输入。

草稿自动保存，保存中继续输入不会被较旧回执覆盖。未知创建结果保留原请求身份；未知写入先读取对账，再决定同版本重试或显示冲突。两份文字都保留，须明确选择。切换对话先保存；迟到读取和列表结果受当前页面代号限制。发现 401/403 时清除历史、输入与记录列表，即使正在组合输入也不能残留。刷新／关闭提示未完成保存，无浏览器持久正文缓存。

历史默认 50 条并支持向前读取，显示真实任务状态和受控取消。本片不订阅生成流、不输出模型回复、不生成客户档案；已有历史以纯文本呈现，不把 Markdown 实验称为产品接入。

新增后端页面模块独立于 app 装配；前端分为请求、状态、输入、呈现与装配五个原生 ES 模块。复用现有服务、认证、作用域、CSRF、版本及备份，不增加运行依赖、构建框架或数据库表。方案见[实施计划](../../../plans/2026-10-17-assistant-home-drafts.md)与[操作界面约束](../../../design/assistant-surface.md)。

新增五份 JS、CSS 和 HTML 源文件合计 50,622 字节，约 49.44 KiB；这是源文件资源量，不是安装器增量或内存测量。

## 验证证据

原始证据目录为 `.local/chat-home-20261017/`，仅独立合成数据。目标测试与完整回归包含关系按身份去重，不将反复复验相加。

本机执行入口：项目 `.venv/Scripts/python.exe -m pytest` 分别运行 `tests/integration/test_assistant_pages.py`、`tests/integration/test_local_workbench.py tests/integration/test_assistant_routes.py`、`tests/integration/test_assistant_frontend.py`；前端包装实际调用现有 Node 的 `--test scripts/test_assistant_state.mjs` 与 `--test scripts/test_assistant_transport_input.mjs`。目标与完整执行均保存 JUnit、日志及退出码。完整命令为项目 Python 的 `-u -X utf8 -m pytest -q --tb=short --junitxml=.local/chat-home-20261017/full.xml`；`QX_PILOT_PYTHON` 指向已有 `D:/Documents/裁判文书数据库试点2025/.venv/Scripts/python.exe`，只供测试建立合成 DuckDB 数据。

桌面入口使用已有 Node／Playwright 执行 `desktop/tests/acceptance.cjs`、新增 `assistant.cjs`、`backup.cjs`，共用隔离输出 `electron-legacy`；`intake.cjs` 最终使用独立 `electron-intake-new`。补充恢复页面探针为 `electron_readonly.cjs`，只选择已生成的合成恢复副本，关闭后还原该测试工作区设置。四个开发门为 `-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`；均由项目 Python 执行。没有安装或更新依赖。

| 检查 | 已取得结果 |
|---|---|
| Python 页面目标 | 18 通过；页面／角色／身份／恢复／静态资源白名单 |
| Python 旧入口关联 | 40 通过；原工作台及对话 HTTP |
| Python 前端执行包装 | 2 通过；实际执行 Node 状态 28 项及网络／输入 4 项断言组 |
| 真实浏览器 | 11 组通过；原话保存、网络未知结果、二处编辑冲突、101 条历史、纯文本 XSS、窄屏、撤权、无外部请求 |
| 独立复核修复探针 | 4 组由 RED 转 GREEN；详见 review.md |
| 新冻结 Windows 后端 | 构建成功，5 组实际 EXE 检查通过；首页及 6 份静态资源字节与源码一致、分页、重启、加密备份、恢复读禁写 |
| 实际 Electron 首页 | 6 组通过；默认页、草稿重开、技能／键盘、窗口缩放、关闭自有后台、无生成提交／外部请求／脚本错误 |
| 实际 Electron 原合同流程 | 14 项通过；导入合成 DOCX、原文、候选与处置、Word 下载、重启保留 |
| 实际 Electron 新建接待 | 10 项通过；受众分离、资料／跟进／版本、转案、重启保留 |
| 实际 Electron 备份恢复 | 10 项通过；密码加密、拒绝覆盖、错误口令、独立只读恢复、原件／历史 Word、返回原工作区 |
| 实际 Electron 恢复草稿 | 补充 1 组通过；既有合成 qxbak 恢复副本读回原草稿，全部编辑操作禁用，HTTP 写入 409 |
| 开发门 | schema、defaults、来源、依赖均 exit 0 |
| 完整回归 | 单次 2,094 通过，0 失败／错误／跳过，exit 0；pytest 1,743.82 秒，JUnit 1,743.613 秒；收集清单与 2,094 个不同 JUnit 身份完全一致 |

Electron 使用当前开发壳和本项目 Python，`packaged=false`；独立冻结 EXE 检查另列，不能拼称新安装器已实装。实际窗口在 760×760、网页缩放 1／1.25／1.5 下检查，无文档横向溢出；此结果不代表系统 DPI 或物理中文输入法候选窗验收。根代理查看实际窗口草稿截图，保持当前已批准的简洁操作界面，未进行新一轮风格变更。

四份旧桌面脚本的登录落点兼容 `/assistant` 和旧 `/workspace`；接待／合同仍点击原业务入口。它们在 Python 全套启动后修改，另新增 assistant.cjs，均不由 pytest 调用。最终 397 文件初始快照中 393 份未变，4 份变化恰为这些旧 CJS；新增文件恰为 assistant.cjs。产品源码、配置、Python 测试及其实际调用的 Node 行为脚本在完整执行期间均未变，不声称整份快照完全未变。初始及最终摘要分别保留于 [full-source-hashes.json](full-source-hashes.json) 和 [final-source-hashes.json](final-source-hashes.json)。新旧手工脚本另经独立静态复核，0 项残余问题；法库生命周期脚本本次仅适配入口并检查语法，不重复连接真实法库运行。

完整回归 session 84247 已结束，不再等待或重跑本批。目标检查 60 个不同 Python 用例全部包含于 2,094 项中；Node 28＋4 断言组由其中两个包装用例实际执行，不另加到 Python 总数。上一切片 2,042 的结果仅为历史，当前全套有独立日志、退出码、JUnit 和收集清单。

摘要记录本机执行时的原始文件字节；Git 可能规范化文本换行。运行期文件摘要不能被解释为所有检出环境的文本副本都逐字节一致。

## 失败与局限保留

- 初始页面目标缺路由而失败，修复后 18 项通过；状态保存竞态与撤权接口各有有效 RED，再补齐实现。
- 网络测试第一版把测试 mock 的断言异常映射为网络异常，得到 4 个通过，不能算有效 RED。修正测试后得到 1 失败／3 通过，再补 AbortController 获得 4 通过。
- 浏览器首轮 11 个行为检查均通过，但探针误期望 12 组，报告 exit_code=1；修复汇总计数后再执行得到 11 组、报告及进程 exit 0。原失败证据保留，不当作产品缺陷或直接改为通过。
- 接待首轮误把刚创建的现行工作区当作旧版本迁移输入，缺 `upgrade-intake-v1.json`，在该前置断言失败。改用独立全新目录执行新建接待，10 项通过，原迁移断言未删除；本轮未重跑旧安装版升级。
- 恢复草稿首次截图捕获在界面重绘之前，DOM 断言已通过但画面仍为读取状态；原图保留为 before-paint，补齐列表完成和两帧等待后再次核对实际窗口原话与禁用状态。
- 生成、附件、Jev、自动建档、物理输入法、系统 DPI、新安装器和真实法律质量尚未由此片验证。已安装 0.4.1 和真实数据未替换。

下一切片先补建案前材料所有权与不可变原件接口，再连接主模型／Jev／档案草稿；保持无案件咨询不暗建合同案件。[CH-03 准备记录](../../../plans/2026-10-17-conversation-materials-readiness.md)已独立复核并修正两处计划问题：上传重放先查原回执，再对新请求查版本／配额；原生附件完整恢复走 qxbak，cnbak 另需明确身份与 schema 契约。该记录是实施准备，附件仍未实现。
