# 统一聊天 MVP 源码验证记录

起点：`be26d12fd993b20d096a5562809aad21ce096d03`，本轮工作区改动。全部为独立虚构材料；真实模型、真实微信、安装版及法律质量不在以下通过结论内。

## 本机阶段

统一聊天已连接现有运行事件、接待档案、事实底稿和 TaskDraft。DOCX/PDF 上传后在本地读取；同一聊天内可建合成审查档案、逐项确认事实、运行既有模拟审查并查看风险和建议。结果保存来源；旧审查结果固定当次事实快照。微信仍沿既有离线接入；未接真实账号。

| 检查 | 实际结果 |
|---|---|
| 新业务入口首次失败验证 | 接口未注册：2 failed，退出 1；新增分次材料/来源/重审后：3 failed、2 passed，退出 1 |
| 路由与来源反例 | 已有销售任务后多意图误归属、旧事实无版本：2 failed、7 passed，退出 1；修复后 9 passed |
| 取消/恢复、会话来源、qxbak 往返、明确重审 | `pytest tests/integration/test_assistant_business.py -q --tb=short`：12 passed，12.55 秒，退出 0 |
| 同窗上下文与旧事实版本 | `pytest tests/integration/test_task_chat_context.py -q --tb=short`：先失败历史事实变动反例，修复后 2 passed，4.82 秒，退出 0 |
| 关联后端回归 | 下方十文件批次：172 passed，164.36 秒，退出 0；该批次早于最后两项补充回归，不能冒充最终材料模型验收 |
| 前端统一聊天回归 | `node --test` 全部 `scripts/test_assistant*.mjs`：Node 报告 379 passed，退出 0；旧自定义 harness 按文件计数，不与内部检查数相加 |
| 原生 qxbak | 新业务记录实际创建加密备份并恢复，回执一致、历史可读、写入被拒；包含在上述 Python 中 |
| Chromium 同窗闭环 | `scripts/validate_unified_business_browser.py --output .local/unified-mvp/browser-04`：退出 0，四场景步骤通过；零页面错误、零外部请求；390px 无横向溢出 |
| 本机开发门 | schema --check、verify_defaults、verify_sources --mode development、verify_runtime_dependencies --mode development 均退出 0；13 上游来源仍为 NOT_PRODUCTION_APPROVED，native_build_verified=false |
| 界面机械检测 | Impeccable detect：退出 0、空发现列表；另人工查看 Chromium 截图并折叠手动补录/微信设置 |

关联后端命令（使用项目 `.venv/Scripts/python.exe`）：

```text
-m pytest tests/integration/test_assistant_business.py tests/integration/test_task_chat_context.py tests/integration/test_assistant_generation.py tests/integration/test_native_model_control.py tests/integration/test_task_draft_routes.py tests/integration/test_task_drafts_bridge.py tests/integration/test_task_drafts_bridge_review.py tests/integration/test_task_drafts_completed_backup.py tests/integration/test_assistant_attachment_routes.py tests/integration/test_evidence_worksheet.py -q --tb=short
```

浏览器最终数据库统计：1 个 TaskDraft、1 次 execution、1 份模拟 ReviewRun、1 份附件、0 次模型尝试。证明本机闭环，**不证明真实 AI 分析**。早期 browser-01 卡在表单可访问名称，已为下拉框添加明确标签；browser-02 使用了错误的测试选择器 `#thread`，修正为现有 `#history` 后 browser-03/04 通过。没有把早期失败写成通过。

独立复核已发现并修复：普通聊天被续办吞掉、多意图误归属、事实底稿来源版本遗漏、执行会话归属未核、任务归属无选择路径、重审后仍回旧任务、换能力被当撤权、历史事实快照漂移。最后一项“业务回执未知时刷新制造冲突”已交由拥有 state 文件的材料 AI 实施子任务修复，待最终集成回归。

## 材料 AI 接续收尾

材料 AI 已沿现有模型账本、后台运行器和 DeepSeek transport 接入 `material-business-v1`，没有新建第二套模型服务。每次发送由原生确认绑定问题、完整材料清单、接收方、模型、预算和精确 basis；发送前最后复查授权、配置、数据库材料版本及原件摘要。候选只作为带来源的内部待核草稿。

| 检查 | 实际结果 |
|---|---|
| 授权竞态 RED → GREEN | 配置原地变化和授权自然到期先各失败 1 项；修复后通过。补 claim 后材料选择变化反例，先实际发送并失败断言，修复后 `failed_before_send`、0 次 HTTP |
| 材料生成、路由与 C4 | 14 项材料生成、4 项 HTTP、6 项 C4 均通过；含四种 workflow、实际并发 claim 一次 HTTP、真实材料成果 qxbak 往返和恢复 POST 409 |
| 最终目标 Python | 九个材料/备份/恢复/前端集成测试文件：153 passed，150.77 秒，退出 0 |
| 前端 | 全部 `scripts/test_assistant*.mjs`：385 passed、0 failed；新增 5 项材料取消、双击、输入变化、unknown 找回和迟到授权检查 |
| 桌面 | 全部 `desktop/tests/*.test.cjs`：373 passed、0 failed；新增 3 项材料原生确认和打包依赖检查 |
| Chromium 复验 | `.local/unified-mvp/browser-workbuddy-01`：PASS；四场景、零页面错误、零外部请求、390px 无横向溢出 |
| 开发门 | schema、verify_defaults、verify_sources development、verify_runtime_dependencies development 均退出 0；55 个运行包和 1 个构建包，网络调用 0 |
| 独立复核 | Spec 初审发现传输竞态、真实 qxbak 和实际并发缺口；修复后复审确认三项全部闭环。Standards 仅指出 registry 换行噪声，已恢复 LF，实质 diff 收敛 |

真实 DeepSeek 远端账号尚未联调；以上 DeepSeek 证据为 loopback/合成 provider，不产生真实费用。真实微信下载解密、安装版及律师法律质量仍未验收。既有 Windows 恢复发布拒绝和原生崩溃问题不因这些测试通过而关闭。

## Windows 打包版接续验收

冻结后端与安装器已生成。最终修复版 `dist/desktop/Qunxing-Workbench-0.5.0-Setup.exe` 为 146,012,159 bytes，SHA-256 `911f00c0db1fb22f8086b2b535830869e4a35fe12ded72ffe8a77e07216858f0`；早期 145,947,030 bytes / `eb00fa10…` 包已被后续修复取代。`app.asar` 已核对包含 material-approval、material-basis、model-approval、model-session、preload 等入口。

- 关联后端十二文件：`291 passed in 224.87s`，退出 0。
- electron-builder 26.15.3 / Electron 44.8.0 / Windows x64 NSIS 构建退出 0。默认构建两次被环境的批量删除确认保护阻断（旧产物 578 文件及语言清理）；未强制删除。旧目录移动到 `.local/unified-mvp/pre-build-0.5.0/` 留底，并仅在 `.local/unified-mvp/electron-44.8.0-pruned/` 制作保留 zh-CN、zh-TW、en-US 的 Electron 副本，以 `--config.electronDist=...` 完成打包。产品语言列表未改。
- 首次 Electron 自动化失败是宿主继承 `ELECTRON_RUN_AS_NODE=1`；日志明确为 Node 拒绝 `--remote-debugging-port=0`。仅对验收进程移除该变量和宿主 NODE_OPTIONS 后，应用正常启动。没有改系统环境或产品代码。
- `desktop/tests/acceptance.cjs` 在合成账号创建、登录后等待旧“合同审查/合同工作台”独立链接而超时；该旧入口已被统一聊天替代，所以不据此判产品失败，也不把此脚本列为通过。
- `desktop/tests/assistant.cjs` 已适配现行首页：材料入口可用，Shift+Enter 只验证草稿换行，不再要求已取消的“尚未接入”提示。对打包版实际验收输出在 `.local/unified-mvp/packaged-acceptance-02/assistant-report.json`：PASS，6 组检查、100%/125%/150% 窗口缩放、重载及真实应用重启均通过，0 脚本错误、0 外部请求、0 模型提交。

本段只证明 **win-unpacked 打包应用** 的合成账号/聊天/草稿闭环。NSIS 安装、覆盖升级、卸载、真实用户数据、真实 DeepSeek 和真实微信仍未验收。

## 打包版统一合同闭环与冻结资源修复

新增 `desktop/tests/unified-business.cjs`，使用独立合成账号、已登记虚构 DOCX 和真实 Electron/冻结后端，覆盖统一聊天建任务、显式合成用途上传、补充材料、建案、逐项事实确认、模拟审查和真实应用重启。最终报告 `.local/unified-mvp/packaged-contract-final/unified-business-report.json`：PASS，6 组检查，0 页面错误、0 外部请求、0 模型提交。

- 首次实际建案返回 HTTP 500。临时诊断构建取得冻结异常：`acceptance.registry.safe_file` 抛 `FIXTURE_PATH_INVALID`。根因是 `desktop/backend.spec` 只带 assisted-v1 和另一组 synthetic，漏带 `_registered_hashes()` 所需的 `tests/fixtures/acceptance` 与 `tests/acceptance/cases.json`。
- 修复为在 spec 显式携带上述只读登记资源，不放宽路径、摘要、固定来源或数量校验。`desktop/tests/model-packaging.test.cjs` 新增回归，修复前 1 项实际失败，修复后通过。临时日志开关及 stderr 捕获均未留在产品源码或最终包；`desktop_entry.py` 已恢复无差异。
- 修复后默认本机材料上传仍按设计返回 409 `DATA_POLICY_UNAPPROVED`，不能进入模拟任务；测试必须在桌面端显式选择 `material-purpose=synthetic`。该 409 是测试未选择合成用途，不是放宽安全策略的理由。最终显式合成用途完整流程通过。
- 全量桌面逻辑与打包回归：374/374 passed，0 failed。最终 NSIS 构建退出 0，冻结资源 `acceptance-provenance.json` 和 `cases.json` 已核验存在，最终安装器摘要见上节。

NSIS 隔离实测未执行：本机已有同 appId 正式安装，安全策略禁止用于备份注册表的 `reg.exe`。没有绕过限制、没有运行会改写原安装位置的安装器、没有修改原安装注册表。需要在干净 Windows/沙盒，或具备安全注册表备份恢复条件后，再验证首次安装、覆盖升级、卸载和资料保留。真实模型、真实微信、真实案件与法律质量不在本次通过范围。

## 完整回归与提交前兼容性收尾

- 原生控制兼容旧受信 Main 组件：缺少材料授权方法时初始化不再崩溃，材料授权调用 fail closed。普通控制帧继续保持 32 KiB 早期拒绝边界，仅明确的材料授权帧可读取至 512 KiB；相关原生控制、进程、协议及材料生成组合回归 52 passed。
- 新模型材料迁移改变了 `assistant_model_attempts` 的 CHECK。历史升级测试改用 `tests/helpers/legacy_material_model.py` 精确恢复迁移前模型表结构，并补齐后期表清理和 `CURRENT_VERSION` 断言；没有改写历史迁移定义或放宽生产迁移、权限及完整性校验。历史模式后续批次 325 passed，微信历史与服务批次 217 passed。
- 完整套件第一次有效汇总为 51 failed、6895 passed、4 skipped、24 errors；上述兼容性与合法历史夹具修复后，收尾复跑为 1 failed、6969 passed、4 skipped、1 warning。唯一失败是下述硬链接环境假设，不能将前两次运行写成全绿。
- pytest 临时目录必须使用 D 盘项目内短路径 `.local/t`。C 盘余量低于 40 GiB 资料库保护门会产生 `LIBRARY_DISK_BUDGET`，过长临时目录会使恢复路径达到 260 字符；这两类环境失败均未通过修改安全门解决。
- Windows 长路径硬链接用例中，宿主的 `unlink()` 会把第二链接保留到 `$RECYCLE.BIN`，`fsutil hardlink list` 仍列出原件和回收站链接，因此 `st_nlink=2` 且产品继续拒绝备份是正确行为。测试保留“硬链接不得归档”的实际拒绝断言，仅在删除后第二链接仍被宿主保留时明确 skip 最后的单链接恢复断言，不宣称该平台恢复路径已通过；其他环境仍执行原断言。
- 最终未排除任何用例的完整命令 `python -m pytest tests -q --tb=short` 退出 0：**6969 passed、5 skipped、1 warning，6129.82 秒**。跳过包括上述 1 项宿主回收站环境断言和套件原有的 4 项；警告来自一项故意伪造布尔账号输入的 Pydantic 序列化检查。该结果覆盖源码测试，不替代安装器、真实外部服务或法律质量验收。
