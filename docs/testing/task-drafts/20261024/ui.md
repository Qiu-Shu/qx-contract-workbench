# TaskDraft HTTP 与页面验证

日期：2026-10-24。目录：`D:\Documents\ChatGPT\律所项目`。全部测试使用临时数据库、独立合成材料和现有本地运行时；未安装依赖、连接微信、调用真实模型或外发资料。

## 实现范围

- 新建任务 HTTP 路由复用 `actor_in`、CSRF、来源检查和数据库事务。有 JSON 的写操作先鉴权、再读请求体、再在写事务复核身份及对象归属；取消执行无请求体且幂等。
- 对话页独立“模拟合同任务”卡：指令和附件可先后收集、继续补充、暂停／取消／恢复、选择主合同、冻结。未就绪附件保留原收件记录，可更新为已读取版本或填写原因排除。
- 冻结后选择已有空案件，进入原事实确认页，再提交当前事实版本和被冻结的文档哈希运行 Mock 审查。保留原件和现有结果页。
- 两个“审查合同 · 模拟”按钮只导航到任务卡，不改变普通聊天的 skill 或模型请求。
- 桌面上传默认仍为本机人工材料；用途选择器可显式选择已登记合成材料，服务器继续验证固定哈希白名单。上传过程中锁定用途。
- ready 附件可显式更新到当前选定解析版本以解除版本冲突；被排除项可恢复到已读取版本，原排除记录留在审计中。ready 与 pending 项均可记录原因排除。
- 结果页依据已保存 run 的 `manifest.model_provider` 显示“模拟审查”或“离线人工候选”；不改变全局 purpose，也不隐藏现有人工候选表单。
- 网络结果不确定时重试原路径、原请求体和原事件编号；会话切换丢弃过期读响应，当前授权失效清空任务内容。
- 工作区从最近 50 条可见对话投影最多 50 条模拟任务，按更新时间和 ID 稳定排序；另保留最多 50 条后台任务。中文状态、正确的任务卡链接；单项 403/409 由核心列表过滤，401 继续失败。
- 恢复副本仅新增精确匹配的任务列表／草稿／执行 GET 读取许可；写请求及伪装成 GET 的写路径仍由恢复中间件阻断。
- 恢复任务成果链接进入专用历史页 `/recovery/task-executions/{id}`：核验当前任务 owner 与案件 ACL 后，以 `read_run(current=False)`展示备份中的模拟覆盖、原始意见、限制及版本摘要。页面无执行或批准控件，不扩大实时 `current=True` 准入；非恢复应用不注册该路径。

## 实际红绿记录

| 命令 | 阶段 | 退出码 | 实际数量／结果 |
|---|---|---:|---|
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py --tb=short` | 新路由与卡片 RED | 1 | 3 failed；缺路由返回 404，卡片不存在 |
| 同上 | 初次 GREEN | 0 | 3 passed |
| `node --test scripts/test_assistant_tasks.mjs` | 新模块尚不存在 | 1 | 1 module import failure；不是行为测试通过 |
| 同上 | 初次 GREEN | 0 | 4 passed |
| 同上 | 合同按钮入口 RED | 1 | 1 failed、4 passed；未打开模拟任务卡 |
| 同上 | 入口 GREEN | 0 | 5 passed |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py --tb=short` | 取消执行 RED | 1 | 3 failed、4 passed；取消路由 404 |
| 同上 | 取消及两个收件顺序 GREEN | 0 | 7 passed |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py tests/integration/test_assistant_frontend.py --tb=short` | HTTP／页面回归 | 0 | 19 passed；其中 HTTP 8 项、前端集成 11 项 |
| `node --test scripts/test_assistant_tasks.mjs` | 当前撤权清空 RED | 1 | 1 failed、6 passed；已有敏感卡片未清除 |
| 同上 | 最终任务脚本 GREEN | 0 | 7 passed |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py tests/integration/test_assistant_frontend.py tests/integration/test_assistant_pages.py tests/integration/test_intake.py --tb=short` | 入口与工作区关联回归 | 0 | 50 passed，56.94 秒 |
| `node --test scripts/test_assistant_tasks.mjs` | 结果来源标签 RED → GREEN | 1 → 0 | 1 failed、7 passed → 8 passed |
| `node --test scripts/test_assistant_tasks.mjs scripts/test_assistant_material_dom.mjs` | 更新／恢复材料及合成用途 RED → GREEN | 1 → 0 | 3 failed、19 passed → 22 passed |
| `node --test scripts/test_assistant_tasks.mjs` | 会话切换写入锁与只读刷新 RED | 1 | 2 failed、10 passed |
| `node --test scripts/test_assistant_tasks.mjs scripts/test_assistant_material_dom.mjs` | 切换／只读修复及材料回归 GREEN | 0 | 24 passed |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_assistant_frontend.py tests/integration/test_coverage_taxonomy_ui.py --tb=short` | 前端与 18 维来源回归 | 0 | 17 passed，21.63 秒 |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py tests/integration/test_assistant_frontend.py tests/integration/test_coverage_taxonomy_ui.py -k 'not native_task_mock' --tb=short` | 合成独立服务与前端回归 | 0 | 25 passed、2 deselected，37.56 秒 |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py -k 'native_task_mock or recovery_reads' --tb=short` | native 正向／local 反向通过，恢复 GET 有效 RED | 1 | 2 passed、1 failed、8 deselected；唯一失败为恢复副本任务 GET 返回 409 |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py tests/integration/test_assistant_frontend.py tests/integration/test_assistant_pages.py tests/integration/test_coverage_taxonomy_ui.py --tb=short` | 最终 HTTP／页面／18维回归 GREEN | 0 | 46 passed，93.37 秒；含全部 11 项任务 HTTP、native 合成正向／local 反向、恢复只读 |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py -k recovery_history_page --tb=short` | 恢复历史结果页 RED → GREEN | 1 → 0 | 1 failed、11 deselected → 1 passed、11 deselected；初始缺路由 404 |
| `node --test scripts/test_assistant_tasks.mjs` | 恢复成果导航 RED → GREEN | 1 → 0 | 1 failed、13 passed → 14 passed；普通成果路径保持不变 |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q tests/integration/test_task_draft_routes.py tests/integration/test_assistant_frontend.py tests/integration/test_assistant_pages.py --tb=short` | 历史页补丁后 affected 回归 GREEN | 0 | 41 passed，50.62 秒；含 12 项任务 HTTP、11 项前端集成、18 项对话页面回归 |
| `impeccable.cmd detect --json` 加上述变更页面／脚本／样式路径 | 静态界面检测 | 0 | 输出 `[]`，0 个检测项 |
| `git diff --check` | 空白错误检查 | 0 | 无输出 |

补充说明：扩展 HTTP 测试初期在普通 native `assisted_draft` 环境调用 Mock prepare，返回 `BLOCKED_LIVE`（2 failed、5 passed），先以独立 `mock_demo` fixture 验证。随后为完成实际桌面 A＋B，根代理加入持久任务准入，在原 purpose 不变的情况下，仅批准已冻结且仍满足服务端登记与权限条件的合成任务。native 测试使用默认白名单 `assisted-v1` 中的 sales 样本，未修改白名单；Mock 默认 sales 样本不在 native 种子白名单内时，上传被拒绝的结果不计为业务实现失败。Fixture 初次密码选项未对齐造成的 2 个 setup error 已修正，不计为业务 RED。入口测试首次截取了错误的源码片段造成语法错误，修正截取范围后才取得上表有效行为 RED。

HTTP 回归覆盖两个到达顺序、暂停／取消／恢复、冻结及准备、原件不变、跨账户拒绝、无 CSRF 拒绝、请求体读取期间撤销会话后零写入、未就绪媒体阻断及理由排除，以及撤销一个目标案件权限后其他合法任务仍可列出且被撤数据不泄露。

任务 Node 14 项覆盖附件不丢弃、原批次重试、旧会话响应隔离、切换会话期间拒绝写入、只读不写但可刷新、真实按钮绑定、以当前事实版本和冻结哈希提交模拟审查、当前授权失败清空页面、具体结果来源标签、ready 版本更新及 excluded 恢复，以及普通／恢复模式的成果导航。材料 Node 12 项含原有异步／队列回归及默认 local／显式 synthetic 两项。DOM fixture 不替代浏览器布局验证。

历史结果 HTTP 真实 fence 测试验证：未登录 401、其他任务 owner 403、撤销案件成员后 403；完成结果可读取 18 维覆盖、原始 findings、limitations 和 task/run/原件摘要，返回会话与恢复案件链接可见。页面无 form/button，POST 页面及 prepare/review/cancel 全部 409。相同 fence 下 `read_run(current=True)` 仍为 `BLOCKED_LIVE`。历史模板的 Impeccable 静态检测输出 `[]`、退出码 0；未把此项称为新增浏览器视觉验收。

## 浏览器证据与边界

根代理执行的真实 Chromium 报告 `.local/task-drafts-20261024/browser-01/report.json` 已核对：5 组步骤通过；1 个 execution、1 次 Mock review、0 次 assistant run；无页面异常、无外部浏览器请求；840 宽视口无横向溢出。覆盖收集、准备、人工确认合成事实、模拟结果及刷新后恢复。该轮是入口导航补丁前的证据，根代理负责修改后的复验。

native HTTP 已通过真实 `build_local_app` 配置下的默认登记样本正向：上传／解析、收集／冻结、准备、测试显式提交事实确认、模拟审查及结果重读；覆盖 18 个维度，重复提交只有 1 次 review、0 次 assistant run，原件保持一致。相同登记样本使用 `local` policy 时仍拒绝准备；普通 `/reviews` 仍为 409。

此处是源码 FastAPI＋Chromium／HTTP 合成验收，不是已安装 Electron 的验收。不得据此声称真实合同、真实微信或真实模型可运行。
